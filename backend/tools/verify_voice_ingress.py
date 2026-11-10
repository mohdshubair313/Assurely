"""Synthetic HTTP/WSS ingress checks, never a Vaani call or customer-session creator."""

import argparse
import asyncio
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx
import websockets

from app.core.config import get_settings


async def verify(base: str) -> dict[str, object]:
    url = urlsplit(base)
    if url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}:
        raise ValueError("An origin without credentials, path or query is required")
    if not (
        (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1"})
        or (url.scheme == "https" and url.hostname and url.hostname.endswith(".trycloudflare.com"))
    ):
        raise ValueError("Only local API or development Quick Tunnel origins are permitted")
    settings = get_settings()
    base = base.rstrip("/")
    room = "synthetic_transport_probe_" + uuid.uuid4().hex
    raw = json.dumps(
        {
            "event": "synthetic_transport_probe",
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {"room_name": room},
        }
    ).encode()
    signature = hmac.new(
        settings.vaani_webhook_secret.get_secret_value().encode(), raw, hashlib.sha256
    ).hexdigest()
    checks: dict[str, object] = {}
    secrets = [
        settings.vaani_api_key.get_secret_value(),
        settings.vaani_byol_token.get_secret_value(),
        settings.vaani_webhook_secret.get_secret_value(),
        settings.backend_gateway_token.get_secret_value(),
    ]
    async with httpx.AsyncClient(base_url=base, timeout=15, follow_redirects=False) as client:
        requests: list[tuple[str, str, str, dict[str, Any], int]] = [
            ("health", "GET", "/health", {}, 200),
            ("readiness", "GET", "/ready", {}, 200),
            ("docs_blocked", "GET", "/docs", {}, 404),
            ("openapi_blocked", "GET", "/openapi.json", {}, 404),
            ("customer_voice_blocked", "GET", "/v1/voice/entitlement", {}, 404),
            ("identity_gateway_required", "GET", "/v1/me", {}, 403),
            (
                "identity_token_required",
                "GET",
                "/v1/me",
                {
                    "headers": {
                        "X-Assurely-Gateway-Key": settings.backend_gateway_token.get_secret_value()
                    }
                },
                401,
            ),
            (
                "invalid_signature_rejected",
                "POST",
                "/v1/webhooks/vaani",
                {
                    "content": raw,
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Webhook-Signature": "0" * 64,
                    },
                },
                401,
            ),
            (
                "signed_synthetic_receipt",
                "POST",
                "/v1/webhooks/vaani",
                {
                    "content": raw,
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Webhook-Signature": signature,
                    },
                },
                200,
            ),
            (
                "duplicate_receipt",
                "POST",
                "/v1/webhooks/vaani",
                {
                    "content": raw,
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Webhook-Signature": signature,
                    },
                },
                200,
            ),
        ]
        for name, method, path, kwargs, expected in requests:
            response = await client.request(method, path, **kwargs)
            if any(secret and len(secret) >= 16 and secret in response.text for secret in secrets):
                raise RuntimeError("Secret reflection detected; response omitted")
            checks[name] = {
                "status": response.status_code,
                "passed": response.status_code == expected,
            }
            if name == "duplicate_receipt" and response.status_code == 200:
                checks[name]["passed"] = response.json().get("duplicate") is True  # type: ignore[index]
    ws_base = base.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
    for name, headers in [
        ("unauthorized_websocket_rejected", {}),
        (
            "unknown_call_websocket_rejected",
            {"Authorization": "Bearer " + settings.vaani_byol_token.get_secret_value()},
        ),
    ]:
        try:
            async with websockets.connect(
                ws_base + "/v1/voice/provider/byol/" + room,
                additional_headers=headers,
                open_timeout=15,
                close_timeout=3,
            ):
                checks[name] = {"passed": False}
        except websockets.exceptions.InvalidStatus as error:
            checks[name] = {
                "passed": error.response.status_code == 403,
                "status": error.response.status_code,
            }
    return {
        "base_url": base,
        "checks": checks,
        "event_digest": hashlib.sha256(raw).hexdigest(),
        "synthetic_event_only": True,
        "real_provider_call": False,
        "authenticated_byol_101_verified": False,
        "passed": all(
            isinstance(value, dict) and value.get("passed") is True for value in checks.values()
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    try:
        result = asyncio.run(verify(args.base_url))
        print(json.dumps(result))
        raise SystemExit(0 if result["passed"] else 1)
    except (ValueError, RuntimeError, httpx.HTTPError, OSError, TimeoutError):
        print(
            json.dumps(
                {"passed": False, "reason": "Ingress verification failed; private details omitted"}
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
