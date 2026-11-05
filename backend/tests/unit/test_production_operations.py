"""Deployment probes and startup must fail closed without leaking dependency errors."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db.connection_urls import checkpoint_conninfo
from app.main import create_app
from app.ops.readiness import dependencies_ready
from app.ops.serve import checked_configuration


@pytest.mark.parametrize("mode", ["verify-full", "require", "disable"])
def test_checkpoint_tls_option_is_translated_without_downgrade(mode):
    from sqlalchemy.engine import make_url

    url = make_url(checkpoint_conninfo(
        f"postgresql+asyncpg://service:encoded%40password@db.example/service?ssl={mode}"))
    assert url.password == "encoded@password"
    assert url.drivername == "postgresql"
    assert url.query["sslmode"] == mode and "ssl" not in url.query
    if mode == "verify-full":
        assert url.query["sslrootcert"] == "system"


def test_conflicting_tls_modes_fail():
    with pytest.raises(ValueError, match="Conflicting"):
        checkpoint_conninfo("postgresql+asyncpg://host/db?ssl=verify-full&sslmode=disable")


@pytest.mark.asyncio
@pytest.mark.parametrize("db_ok,redis_ok", [(True, True), (False, True), (True, False)])
async def test_readiness_checks_both_dependencies(db_ok, redis_ok):
    db = AsyncMock()
    db.__aenter__.return_value = db
    db.scalar.return_value = "010_clerk_identity" if db_ok else "009_turn_recovery"
    redis = AsyncMock()
    redis.ping.return_value = redis_ok
    with patch("app.ops.readiness.AsyncSessionLocal", return_value=db), patch(
        "app.ops.readiness.get_redis_client", AsyncMock(return_value=redis),
    ):
        assert await dependencies_ready() is (db_ok and redis_ok)


@pytest.mark.asyncio
async def test_dependency_exception_is_sanitized():
    with patch("app.ops.readiness.AsyncSessionLocal", side_effect=RuntimeError("secret-dsn")):
        assert not await dependencies_ready()


@pytest.mark.parametrize("diagnostics,runtime,dependencies,code", [
    (True, True, True, 200), (False, True, True, 503),
    (True, False, True, 503), (True, True, False, 503),
])
def test_production_readiness_requires_diagnostics_runtime_and_dependencies(
    diagnostics, runtime, dependencies, code,
):
    with patch("app.main.get_settings", return_value=SimpleNamespace(
        environment="production", cors_origins=[])), patch(
        "app.api.v1.message._production_graph", object() if runtime else None,
    ), patch("app.ops.readiness.dependencies_ready", AsyncMock(return_value=dependencies)):
        app = create_app()
        app.state.exception_sink = SimpleNamespace(failed=not diagnostics)
        response = TestClient(app).get("/ready")
        assert response.status_code == code
        assert response.json() == {"status": "ready" if code == 200 else "unavailable"}
        assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
@pytest.mark.parametrize("passed", [True, False])
async def test_production_entrypoint_closes_preflight_pool(passed, capsys):
    with patch("app.ops.serve.report", AsyncMock(return_value={
        "configuration_passed": passed, "production_release_authorized": False,
    })), patch("app.ops.serve.async_engine", SimpleNamespace(dispose=AsyncMock())) as engine:
        assert await checked_configuration() is passed
        engine.dispose.assert_awaited_once()
        assert not json.loads(capsys.readouterr().out)["production_release_authorized"]


@pytest.mark.asyncio
async def test_production_entrypoint_sanitizes_failures(capsys):
    with patch("app.ops.serve.report", AsyncMock(side_effect=RuntimeError("secret"))), patch(
        "app.ops.serve.async_engine", SimpleNamespace(dispose=AsyncMock()),
    ):
        assert not await checked_configuration()
    assert "secret" not in capsys.readouterr().out


@pytest.mark.parametrize("key,code", [(None, 403), ("wrong", 403), ("s" * 40, 404)])
def test_gateway_secret_required_before_any_non_development_route(key, code):
    from pydantic import SecretStr

    settings = SimpleNamespace(environment="production", cors_origins=[],
                               backend_gateway_token=SecretStr("s" * 40))
    with patch("app.main.get_settings", return_value=settings):
        headers = {"X-Assurely-Gateway-Key": key} if key else {}
        response = TestClient(create_app()).get("/not-a-route", headers=headers)
        assert response.status_code == code
        assert "s" * 40 not in response.text


def test_gateway_missing_configuration_and_duplicate_keys_fail_closed():
    from pydantic import SecretStr

    settings = SimpleNamespace(environment="production", cors_origins=[],
                               backend_gateway_token=SecretStr(""))
    with patch("app.main.get_settings", return_value=settings):
        client = TestClient(create_app())
        assert client.get("/not-a-route").status_code == 403
        settings.backend_gateway_token = SecretStr("s" * 40)
        assert client.get("/not-a-route", headers=[
            ("X-Assurely-Gateway-Key", "s" * 40),
            ("X-Assurely-Gateway-Key", "s" * 40),
        ]).status_code == 403


@pytest.mark.asyncio
async def test_redis_initialization_failure_does_not_log_url_or_provider_error(caplog):
    from app.cache.redis_client import get_redis_client

    secret = "synthetic-password-do-not-log"
    with patch("app.cache.redis_client._redis_client", None), patch(
        "app.cache.redis_client.get_settings", return_value=SimpleNamespace(
            redis_url=f"rediss://service:{secret}@redis.invalid:6379/0"),
    ), patch("redis.asyncio.from_url", side_effect=ValueError(secret)):
        assert await get_redis_client() is None
    assert "Redis client initialization failed" in caplog.text
    assert secret not in caplog.text and "redis.invalid" not in caplog.text


def test_deployment_requires_verified_transport_and_gateway_configuration():
    from app.core.config import Settings
    from app.ops.preflight import configuration_checks

    settings = Settings(_env_file=None, database_url=(
        "postgresql+asyncpg://service:synthetic-password@db.invalid/assurely?ssl=verify-full"),
        redis_url="rediss://service:synthetic-password@redis.invalid:6379/0",
        backend_gateway_token="s" * 40)
    checks = configuration_checks(settings)
    assert checks["database_verified_tls"] and checks["redis_authenticated_tls"]
    assert checks["trusted_gateway_configured"]
    settings.database_url = "postgresql+asyncpg://service:synthetic-password@db.invalid/assurely"
    settings.redis_url = "redis://redis.invalid:6379/0"
    checks = configuration_checks(settings)
    assert not checks["database_verified_tls"] and not checks["redis_authenticated_tls"]
