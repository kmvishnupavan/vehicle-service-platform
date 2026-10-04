# ==============================================================================
# Vehicle Service Platform - Production Backend Dockerfile
# Multi-stage, non-root user, pinned Python 3.13 runtime, Uvicorn ASGI server
# ==============================================================================

FROM python:3.13-slim AS builder

WORKDIR /app

# Install build essentials if needed for any native packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install pinned dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# Production runtime stage
FROM python:3.13-slim AS runner

WORKDIR /app

# Create unprivileged application user
RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -s /sbin/nologin -M appuser

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source code
COPY app ./app
COPY pytest.ini ./

# Ensure proper ownership
RUN chown -R appuser:appuser /app

# Drop privileges to non-root user
USER appuser

# Expose standard ASGI application port
EXPOSE 8000

# Environment defaults for production container
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    HOST=0.0.0.0 \
    PORT=8000

# Container healthcheck using built-in Python standard library (no external curl required)
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live', timeout=3)" || exit 1

# Production ASGI server with 2 worker processes and structured logging
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--no-access-log"]
