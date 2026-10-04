"""
Structured Logging Configuration, Request Correlation, and Security Redaction.

Phase 9 Production Hardening:
- Correlated request tracing via X-Request-ID and operation_id.
- Validates incoming request IDs (sanitizes format, prevents log injection).
- Redacts sensitive credentials, tokens, secrets, full bank account numbers, and payment details.
- Captures duration, status, method, path, user_id, role, client_ip, and error_classification.
- Provides JSON-formatted structured logging for production and readable logs for development.
"""

from collections.abc import Mapping
import contextvars
import logging
import re
import sys
import time
from typing import Any, Callable
import uuid
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import structlog
from app.core.config import get_settings

# Context variables for distributed request and operation tracing
request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
operation_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("operation_id", default=None)

# Valid format for incoming request IDs (alphanumeric, hyphens, underscores, length 8..64)
REQUEST_ID_REGEX = re.compile(r"^[A-Za-z0-9_\-]{8,64}$")

# Sensitive parameter names and headers that must never appear in logs
SENSITIVE_KEYS = {
    "authorization",
    "password",
    "token",
    "access_token",
    "refresh_token",
    "service_role",
    "service_role_key",
    "secret",
    "api_key",
    "jwt",
    "card_number",
    "cvv",
    "pin",
    "razorpay_key_secret",
    "razorpay_webhook_secret",
    "account_number",
    "confirm_account_number",
    "private_key",
    "client_secret",
}


def sanitize_value(key: str, val: Any) -> Any:
    """Sanitize individual field values against sensitive key matches."""
    if not isinstance(key, str):
        return val
    lower_key = key.lower()
    for sensitive in SENSITIVE_KEYS:
        if sensitive in lower_key:
            if isinstance(val, str) and len(val) >= 4 and ("account" in lower_key or "number" in lower_key):
                clean = re.sub(r"\s+", "", val)
                return f"•••• •••• {clean[-4:]}"
            return "[REDACTED]"
    if isinstance(val, Mapping):
        return {k: sanitize_value(str(k), v) for k, v in val.items()}
    if isinstance(val, list):
        return [sanitize_value(key, item) for item in val]
    return val


def redact_sensitive_processor(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Structlog processor that recursively redacts sensitive information."""
    sanitized: dict[str, Any] = {}
    for k, v in event_dict.items():
        sanitized[k] = sanitize_value(k, v)
    return sanitized


def configure_logging() -> None:
    """Configure standard library logging and structlog processors."""
    settings = get_settings()

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        redact_sensitive_processor,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.is_production:
        # JSON formatting for production log ingestion (Datadog, CloudWatch, Loki)
        shared_processors.append(structlog.processors.JSONRenderer())
    else:
        # Human-friendly colored formatting for development
        shared_processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=shared_processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    log_level = logging.DEBUG if settings.DEBUG else logging.INFO
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """Retrieve a configured structlog logger instance."""
    return structlog.get_logger(name)


def get_current_request_id() -> str:
    """Retrieve the active request ID or generate a fallback."""
    return request_id_ctx.get() or f"req_{uuid.uuid4().hex[:16]}"


def get_current_operation_id() -> str | None:
    """Retrieve the active background/provider operation ID."""
    return operation_id_ctx.get()


def set_operation_id(op_id: str | None = None) -> str:
    """Assign or generate an operation ID for tracing across async/provider operations."""
    active_op = op_id or f"op_{uuid.uuid4().hex[:14]}"
    operation_id_ctx.set(active_op)
    return active_op


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware capturing request ID, duration, HTTP status,
    authenticated user context, role, and error classification.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        raw_req_id = request.headers.get("X-Request-ID")
        if raw_req_id and REQUEST_ID_REGEX.match(raw_req_id.strip()):
            request_id = raw_req_id.strip()
        else:
            request_id = f"req_{uuid.uuid4().hex[:16]}"

        request_id_ctx.set(request_id)
        request.state.request_id = request_id

        start_time = time.perf_counter()
        logger = get_logger("http.request")

        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            user_id = getattr(request.state, "user_id", None)
            user_role = getattr(request.state, "user_role", None)

            # Classify errors
            error_classification = None
            if 400 <= response.status_code < 500:
                error_classification = "client_error"
            elif response.status_code >= 500:
                error_classification = "server_error"

            logger.info(
                "http_request_finished",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                user_id=str(user_id) if user_id else None,
                role=str(user_role) if user_role else None,
                client_ip=request.client.host if request.client else None,
                error_classification=error_classification,
            )

            response.headers["X-Request-ID"] = request_id
            return response

        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            user_id = getattr(request.state, "user_id", None)
            user_role = getattr(request.state, "user_role", None)

            logger.error(
                "http_request_failed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
                user_id=str(user_id) if user_id else None,
                role=str(user_role) if user_role else None,
                client_ip=request.client.host if request.client else None,
                error_classification="server_error",
                error=str(exc),
            )
            raise
