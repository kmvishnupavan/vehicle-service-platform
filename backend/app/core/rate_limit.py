"""
In-Memory Sliding-Window Rate Limiting & Security Headers Middleware (Phase 9).

Production Abuse Prevention:
- Sliding-window in-memory tracking without requiring external Redis dependencies.
- Tiered rate limits for sensitive endpoints (auth, payments, locations, uploads, webhooks).
- Returns HTTP 429 with Retry-After header and sanitized error envelope when threshold exceeded.
- Security headers middleware appending X-Content-Type-Options, X-Frame-Options, Referrer-Policy,
  and Strict-Transport-Security (in production).
"""

from collections import defaultdict
import time
from typing import Callable
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("core.rate_limit")

# Window size in seconds
DEFAULT_WINDOW_SECONDS = 60

# Rate limits: (max_requests, window_seconds)
PATH_RATE_LIMITS: list[tuple[str, int, int]] = [
    ("/api/v1/auth/login", 10, 60),
    ("/api/v1/auth/register", 10, 60),
    ("/api/v1/payments/create-order", 20, 60),
    ("/api/v1/payments/verify", 20, 60),
    ("/api/v1/mechanics/location", 60, 60),
    ("/api/v1/uploads", 15, 60),
    ("/api/v1/payments/webhook", 120, 60),
    ("/api/v1/payout-accounts/settlements", 30, 60),
]

GLOBAL_MAX_REQUESTS = 300
GLOBAL_WINDOW_SECONDS = 60


class SlidingWindowRateLimiter:
    """Thread-safe in-memory rate limiter using sliding window timestamps."""

    def __init__(self):
        self._history: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int]:
        """
        Check if request is permitted.
        Returns (is_allowed, remaining_seconds_to_wait).
        """
        now = time.time()
        cutoff = now - window_seconds
        records = self._history[key]

        # Purge timestamps outside current window
        while records and records[0] <= cutoff:
            records.pop(0)

        if len(records) >= max_requests:
            oldest = records[0]
            retry_after = max(1, int(oldest + window_seconds - now))
            return False, retry_after

        records.append(now)
        return True, 0

    def clear(self):
        """Reset all tracked history (for testing)."""
        self._history.clear()


limiter = SlidingWindowRateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Applies tiered rate limiting per client IP and path."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Bypass rate limiting in testing mode if desired
        settings = get_settings()
        if settings.ENVIRONMENT.lower() == "testing" and getattr(request.state, "disable_rate_limit", False):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path

        # Determine endpoint-specific limit
        max_req = GLOBAL_MAX_REQUESTS
        window = GLOBAL_WINDOW_SECONDS
        for pattern, p_max, p_window in PATH_RATE_LIMITS:
            if path.startswith(pattern):
                max_req = p_max
                window = p_window
                break

        key = f"{client_ip}:{path}"
        allowed, retry_after = limiter.is_allowed(key, max_req, window)

        if not allowed:
            logger.warning(
                "rate_limit_exceeded",
                client_ip=client_ip,
                path=path,
                retry_after=retry_after,
            )
            request_id = getattr(request.state, "request_id", None)
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": f"Rate limit exceeded. Please retry in {retry_after} seconds.",
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "request_id": request_id,
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Rate limit exceeded. Please retry in {retry_after} seconds.",
                        "request_id": request_id,
                    },
                },
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)
        remaining = max(0, max_req - len(limiter._history[key]))
        response.headers["X-RateLimit-Limit"] = str(max_req)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time() + window))
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Applies standard HTTP security headers to all responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        settings = get_settings()

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(self), camera=(), microphone=()"

        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response
