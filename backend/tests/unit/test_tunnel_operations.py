"""Synthetic tunnel boundary and worker checks; no provider or tunnel is contacted."""

import asyncio
import json
import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.websockets import WebSocketDisconnect

from app.api.v1 import vaani
from app.core.config import Settings
from app.ops.voice_worker import healthy, heartbeat


@pytest.fixture
def client(monkeypatch):
    from app import main
    from app.core import security
    from app.ops import tunnel_boundary

    settings = Settings(
        _env_file=None,
        tunnel_ingress_only=True,
        voice_provider="disabled",
        backend_gateway_token="g" * 48,
        auth_provider="clerk",
        auth_issuer="https://synthetic.clerk.accounts.dev",
        auth_jwks_url="https://synthetic.clerk.accounts.dev/.well-known/jwks.json",
        auth_authorized_parties=["http://localhost:3000"],
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(tunnel_boundary, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    return TestClient(main.create_app()), settings


@pytest.mark.parametrize(
    "path",
    [
        "/docs",
        "/redoc",
        "/openapi.json",
        "/v1/admin",
        "/v1/voice/entitlement",
        "/v1/me/",
        "/v1/%6de",
        "/health?debug=1",
    ],
)
def test_tunnel_rejects_noncanonical_and_unnecessary_routes(client, path):
    browser, _ = client
    response = browser.get(path, headers={"X-Assurely-Gateway-Key": "g" * 48})
    assert response.status_code == 404 and response.headers["cache-control"] == "no-store"


def test_tunnel_health_and_authentication_are_independent(client):
    browser, settings = client
    assert browser.get("/health").status_code == 200
    assert browser.post("/health").status_code == 404
    assert browser.get("/v1/me").status_code == 403
    assert browser.get("/v1/me", headers={"X-Assurely-Gateway-Key": "g" * 48}).status_code == 401
    settings.vaani_dispatch_enabled = True
    assert browser.get("/health").status_code == 404


def test_tunnel_cannot_expose_arbitrary_websockets(client):
    browser, _ = client
    for path in ["/echo", "/v1/voice/provider/byol/room?token=private"]:
        with pytest.raises(WebSocketDisconnect), browser.websocket_connect(path):
            pass


def test_worker_health_receipt_is_bounded_and_sanitized(tmp_path):
    path = tmp_path / "worker.json"
    assert not healthy(path, 30)
    heartbeat(path, True)
    assert healthy(path, 30)
    assert set(json.loads(path.read_text())) == {"at", "healthy"}
    heartbeat(path, False)
    assert not healthy(path, 30)
    for at in [time.time() - 60, time.time() + 60]:
        path.write_text(json.dumps({"healthy": True, "at": at}))
        assert not healthy(path, 30)


@pytest.mark.asyncio
async def test_webhook_stalled_body_has_deadline_and_no_persistence(monkeypatch):
    monkeypatch.setattr(
        vaani, "get_settings", lambda: Settings(_env_file=None, vaani_ingress_enabled=True)
    )
    monkeypatch.setattr(vaani, "BODY_RECEIVE_TIMEOUT", 0.01)

    async def stalled():
        await asyncio.sleep(10)

    async def forbidden(*args):
        raise AssertionError("Unauthenticated body must not reach persistence")

    monkeypatch.setattr(vaani, "receive_event", forbidden)
    request = Request(
        {
            "type": "http",
            "headers": [
                (b"x-webhook-signature", b"0" * 64),
                (b"content-type", b"application/json"),
            ],
        },
        stalled,
    )
    with pytest.raises(HTTPException) as error:
        await vaani.vaani_webhook(request)
    assert error.value.status_code == 408


@pytest.mark.asyncio
@pytest.mark.parametrize("length,status", [(b"262145", 413), (b"-1", 400), (b"garbage", 400)])
async def test_webhook_rejects_invalid_length_before_read(monkeypatch, length, status):
    monkeypatch.setattr(
        vaani, "get_settings", lambda: Settings(_env_file=None, vaani_ingress_enabled=True)
    )

    async def forbidden():
        raise AssertionError("Invalid length must be rejected before body read")

    request = Request(
        {
            "type": "http",
            "headers": [
                (b"x-webhook-signature", b"0" * 64),
                (b"content-type", b"application/json"),
                (b"content-length", length),
            ],
        },
        forbidden,
    )
    with pytest.raises(HTTPException) as error:
        await vaani.vaani_webhook(request)
    assert error.value.status_code == status
