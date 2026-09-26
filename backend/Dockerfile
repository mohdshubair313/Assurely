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

# Install Python dependencies
RUN pip install --no-cache-dir -e ".[dev]"


# Expose port
EXPOSE 8000

# Run with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
