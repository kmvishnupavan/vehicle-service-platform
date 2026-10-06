"""
Vehicle Service Platform - FastAPI Application Entrypoint.

Initializes the FastAPI application with:
- Structured logging and request tracking middleware
- Strict CORS configuration from environment variables
- Centralized, sanitized JSON exception handlers
- Health check and database connectivity endpoints
- Versioned API v1 routers
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
import uuid
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.api import (
    addresses,
    admin_operations,
    admin_settlements,
    auth,
    bookings,
    chat,
    mechanic_dashboard,
    mechanics,
    payments,
    payout_accounts,
    payouts,
    reviews,
    services,
    uploads,
    users,
    vehicles,
    matching,
    service_operations,
    operational_automation,
)
from app.core.config import get_settings
from app.core.logging import (
    StructuredLoggingMiddleware,
    configure_logging,
    get_current_request_id,
    get_logger,
)
from app.db.supabase import check_database_connection
from app.schemas.common import (
    DatabaseHealthResponse,
    ErrorResponse,
    HealthResponse,
    LivenessResponse,
    ReadinessResponse,
)

logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager: runs startup and shutdown routines."""
    settings = get_settings()
    configure_logging()

    # Enforce authoritative environment configuration validation
    from app.core.safety import validate_environment_configuration
    cfg_validation = validate_environment_configuration(settings)
    if not cfg_validation.get("valid"):
        err_msg = "; ".join(cfg_validation.get("errors", []))
        logger.error(
            "environment_configuration_invalid",
            environment=settings.ENVIRONMENT,
            errors=cfg_validation.get("errors"),
        )
        if settings.is_production or settings.is_staging:
            raise RuntimeError(f"Critical {settings.ENVIRONMENT} configuration failure: {err_msg}")

    logger.info(
        "server_startup",
        project_name=settings.PROJECT_NAME,
        environment=settings.ENVIRONMENT,
        debug=settings.DEBUG,
    )
    yield
    logger.info("server_shutdown")


def create_application() -> FastAPI:
    """Factory creating and configuring the FastAPI app instance."""
    settings = get_settings()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="1.0.0",
        description="On-Demand Bike & Car Doorstep Service Platform Backend API",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # 1. Security Headers Middleware
    from app.core.rate_limit import RateLimitMiddleware, SecurityHeadersMiddleware
    app.add_middleware(SecurityHeadersMiddleware)

    # 2. CORS Middleware - Production Hardening
    # Explicitly filter out wildcard '*' to eliminate reflect-all-origin vulnerability
    sanitized_cors_origins = [
        origin.strip()
        for origin in settings.CORS_ORIGINS
        if origin.strip() and origin.strip() != "*"
    ]
    prod_frontend = "https://vehicle-care-frontend.onrender.com"
    if prod_frontend not in sanitized_cors_origins:
        sanitized_cors_origins.append(prod_frontend)
    if (
        settings.FRONTEND_URL
        and settings.FRONTEND_URL != "*"
        and settings.FRONTEND_URL not in sanitized_cors_origins
    ):
        sanitized_cors_origins.append(settings.FRONTEND_URL)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=sanitized_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
    )

    # 3. Rate Limiting Middleware
    app.add_middleware(RateLimitMiddleware)

    # 4. Structured Request Logging Middleware
    app.add_middleware(StructuredLoggingMiddleware)

    # 3. Centralized Exception Handlers (Sanitized, zero sensitive leakage)
    STATUS_CODE_MAP = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
        500: "INTERNAL_SERVER_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }

    async def _handle_http_exception(
        request: Request, exc: HTTPException | StarletteHTTPException
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None) or get_current_request_id() or f"req_{uuid.uuid4().hex[:16]}"
        error_code = getattr(exc, "error_code", None) or STATUS_CODE_MAP.get(exc.status_code, "HTTP_EXCEPTION")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "error_code": error_code,
                "request_id": request_id,
                "error": {
                    "code": error_code,
                    "message": str(exc.detail),
                    "request_id": request_id,
                },
            },
            headers=getattr(exc, "headers", None) or {},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return await _handle_http_exception(request, exc)

    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return await _handle_http_exception(request, exc)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        # Filter validation errors to prevent schema leaks
        cleaned_errors = []
        for err in exc.errors():
            cleaned_errors.append({
                "loc": err.get("loc"),
                "msg": err.get("msg"),
                "type": err.get("type"),
            })
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": "Request validation failed.",
                "errors": cleaned_errors,
                "error_code": "VALIDATION_ERROR",
                "request_id": request_id,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed.",
                    "request_id": request_id,
                    "details": cleaned_errors,
                },
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.error(
            "unhandled_server_exception",
            request_id=request_id,
            error=str(exc),
            path=request.url.path,
        )
        # Never leak internal database errors or stack traces to client
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "An internal server error occurred. Please contact platform support.",
                "error_code": "INTERNAL_SERVER_ERROR",
                "request_id": request_id,
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An internal server error occurred. Please contact platform support.",
                    "request_id": request_id,
                },
            },
        )

    # 4. Health Check & Observability Endpoints
    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["System"],
        summary="Service Health Probe (Backward Compatible)",
    )
    async def health_check() -> HealthResponse:
        """Returns service status."""
        return HealthResponse(status="ok")

    @app.get(
        "/health/live",
        response_model=LivenessResponse,
        tags=["System"],
        summary="Kubernetes / Container Liveness Probe",
    )
    async def liveness_check() -> LivenessResponse:
        """Lightweight check verifying the process is alive."""
        from app.services.health_service import HealthService
        res = await HealthService.get_liveness()
        return LivenessResponse.model_validate(res)

    @app.get(
        "/health/ready",
        response_model=ReadinessResponse,
        tags=["System"],
        summary="Kubernetes / Container Readiness Probe",
    )
    async def readiness_check() -> JSONResponse:
        """Deep readiness probe verifying critical runtime prerequisites."""
        from app.services.health_service import HealthService
        res = await HealthService.get_readiness()
        if isinstance(res, tuple) and len(res) == 2:
            code, payload = res
        elif isinstance(res, dict):
            payload = res
            checks = payload.get("checks", {})
            has_unhealthy = any(
                (isinstance(v, dict) and v.get("status") in ["unhealthy", "unreachable"])
                or v in ["unhealthy", "unreachable"]
                for v in checks.values()
            )
            if payload.get("status") in ["not_ready", "unhealthy"] or has_unhealthy:
                code = 503
            else:
                code = 200
        else:
            code = 200
            payload = {"status": "ready"}
        return JSONResponse(status_code=code, content=payload)

    @app.get(
        "/health/database",
        response_model=DatabaseHealthResponse,
        tags=["System"],
        summary="Database Connectivity Probe",
    )
    async def database_health_check() -> DatabaseHealthResponse:
        """Verifies direct connectivity to the Supabase database."""
        db_status = await check_database_connection()
        if not db_status.get("healthy"):
            return DatabaseHealthResponse(
                status="disconnected",
                healthy=False,
                error=db_status.get("error"),
            )
        return DatabaseHealthResponse(
            status="connected",
            healthy=True,
            error=None,
        )

    # 5. Versioned API Routers (/api/v1/...)
    api_v1_prefix = settings.API_V1_PREFIX
    app.include_router(auth.router, prefix=api_v1_prefix)
    app.include_router(users.router, prefix=api_v1_prefix)
    app.include_router(vehicles.router, prefix=api_v1_prefix)
    app.include_router(addresses.router, prefix=api_v1_prefix)
    app.include_router(services.router, prefix=api_v1_prefix)
    app.include_router(bookings.router, prefix=api_v1_prefix)
    app.include_router(chat.router, prefix=api_v1_prefix)
    app.include_router(mechanic_dashboard.router, prefix=api_v1_prefix)
    app.include_router(payouts.router, prefix=api_v1_prefix)
    app.include_router(payout_accounts.router, prefix=api_v1_prefix)
    app.include_router(admin_settlements.router, prefix=api_v1_prefix)
    app.include_router(admin_operations.router, prefix=api_v1_prefix)
    app.include_router(mechanics.router, prefix=api_v1_prefix)
    app.include_router(payments.router, prefix=api_v1_prefix)
    app.include_router(reviews.router, prefix=api_v1_prefix)
    app.include_router(uploads.router, prefix=api_v1_prefix)
    app.include_router(matching.router, prefix=api_v1_prefix)
    app.include_router(service_operations.router, prefix=api_v1_prefix)
    app.include_router(operational_automation.router, prefix=api_v1_prefix)

    return app


app = create_application()
