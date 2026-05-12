FROM python:3.12-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy pyproject.toml first for layer caching
COPY pyproject.toml ./

# Install uv and use it to install deps
RUN pip install --no-cache-dir uv==0.4.18 && \
    uv pip install --system --no-cache-dir \
        fastapi==0.115.5 \
        uvicorn[standard]==0.32.0 \
        redis==5.2.0 \
        sqlalchemy==2.0.36 \
        asyncpg==0.30.0 \
        httpx==0.27.2 \
        pydantic==2.10.1 \
        pydantic-settings==2.6.1 \
        python-multipart==0.0.17 \
        websockets==14.1

# Copy all services code
COPY services/ ./

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Default entrypoint is overridden per-service in docker-compose.yml
CMD ["python", "-m", "api_gateway.main"]
