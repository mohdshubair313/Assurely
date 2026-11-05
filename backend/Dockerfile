# Default Dockerfile is the production target for container hosting providers.
FROM python:3.11-slim AS build
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml constraints-production.txt ./
RUN python -c "import tomllib; from pathlib import Path; Path('/tmp/runtime-requirements.txt').write_text('\n'.join(tomllib.loads(Path('pyproject.toml').read_text())['project']['dependencies']))"
RUN --mount=type=cache,target=/root/.cache/pip \
    pip wheel --wheel-dir /wheels -c constraints-production.txt -r /tmp/runtime-requirements.txt

FROM build AS package
COPY app ./app
RUN --mount=type=cache,target=/root/.cache/pip pip wheel --no-deps --wheel-dir /wheels .

FROM python:3.11-slim AS production
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 ENVIRONMENT=production
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 assurely && useradd --uid 10001 --gid 10001 assurely \
    && mkdir -p /var/log/insuranceai/private && chown -R assurely:assurely /var/log/insuranceai \
    && chmod 700 /var/log/insuranceai/private
COPY --from=build /wheels /wheels
COPY --from=build /tmp/runtime-requirements.txt /tmp/runtime-requirements.txt
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r /tmp/runtime-requirements.txt \
    && pip check && rm -rf /wheels /tmp/runtime-requirements.txt
COPY --from=package /wheels/insurance_advisor_backend-*.whl /tmp/
RUN pip install --no-cache-dir --no-deps /tmp/insurance_advisor_backend-*.whl \
    && pip check && rm -f /tmp/insurance_advisor_backend-*.whl
COPY --chown=assurely:assurely alembic.ini ./
COPY --chown=assurely:assurely alembic ./alembic
USER assurely
EXPOSE 8000
CMD ["python", "-m", "app.ops.serve"]
