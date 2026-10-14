# backend/Dockerfile
# Multi-stage build for the FastAPI insurance advisor backend.
# Per deployment topology (LLD § 7.6): api and agent-runtime colocated initially,
# split into separate services once traffic justifies it.

FROM python:3.11-slim AS base

WORKDIR /app

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy source and pyproject
COPY . .

# Maintenance builds may constrain unrelated versions without baking the local
# constraints snapshot into the image.
RUN --mount=type=secret,id=dependency_constraints \
    if [ -f /run/secrets/dependency_constraints ]; then \
        pip install --no-cache-dir -c /run/secrets/dependency_constraints -e ".[dev]"; \
    else \
        pip install --no-cache-dir -e ".[dev]"; \
    fi && pip check


# Expose port
EXPOSE 8000

# Run with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
