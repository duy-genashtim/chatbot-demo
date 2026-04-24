# ----------------------------------------------------------------
# Stage 1: builder — install dependencies into isolated venv
# ----------------------------------------------------------------
FROM python:3.12-slim AS builder

# Build tools required by some packages (cryptography, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Create venv and install deps
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ----------------------------------------------------------------
# Stage 2: runtime — slim image, non-root user
# ----------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Non-root user (uid 1000 matches typical host user for volume perms)
RUN useradd --create-home --uid 1000 --shell /bin/bash appuser

WORKDIR /app

# Copy application source
COPY app/ ./app/

# Create data dirs and hand ownership to appuser
RUN mkdir -p /app/data /app/uploads /app/chroma_data /app/logs && \
    chown -R appuser:appuser /app

# Default to prod — override with --env ENVIRONMENT=dev in docker compose dev
ENV ENVIRONMENT=prod
ENV PATH="/opt/venv/bin:$PATH"

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/healthz')" || exit 1

# uvloop is bundled in uvicorn[standard] — use it for lower event-loop overhead
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "uvloop", "--workers", "1"]
