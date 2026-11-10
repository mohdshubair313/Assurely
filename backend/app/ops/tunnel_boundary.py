"""Narrow development-tunnel exposure; never infer trust from forwarding headers."""

import hmac
import re

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings


class TunnelBoundary:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        settings = get_settings()
        if not getattr(settings, "tunnel_ingress_only", False) or scope["type"] not in {
            "http",
            "websocket",
        }:
            await self.app(scope, receive, send)
            return
        safe = (
            settings.environment == "development"
            and settings.voice_provider == "disabled"
            and not settings.vaani_dispatch_enabled
        )
        path = scope["path"]
        # Encoded aliases and query strings are unnecessary for these exact ingress contracts.
        raw_path = scope.get("raw_path", path.encode())
        canonical = raw_path == path.encode() and not scope.get("query_string")
        if scope["type"] == "websocket":
            allowed = bool(re.fullmatch(r"/v1/voice/provider/byol/[A-Za-z0-9_-]{1,160}", path))
            if not safe or not canonical or not allowed:
                await send({"type": "websocket.close", "code": 1008})
                return
        else:
            route = (scope["method"], path)
            allowed = route in {
                ("GET", "/health"),
                ("GET", "/ready"),
                ("POST", "/v1/webhooks/vaani"),
                ("GET", "/v1/me"),
            }
            if not safe or not canonical or not allowed:
                await JSONResponse(
                    {"detail": "Not found."}, status_code=404, headers={"Cache-Control": "no-store"}
                )(scope, receive, send)
                return
            if path == "/v1/me":
                expected = settings.backend_gateway_token.get_secret_value().encode()
                supplied = [
                    v for k, v in scope["headers"] if k.lower() == b"x-assurely-gateway-key"
                ]
                if (
                    len(expected) < 32
                    or len(supplied) != 1
                    or not hmac.compare_digest(expected, supplied[0])
                ):
                    await JSONResponse(
                        {"detail": "Service access is unavailable."},
                        status_code=403,
                        headers={"Cache-Control": "no-store"},
                    )(scope, receive, send)
                    return
        # The underlying routes still enforce Clerk, webhook HMAC or BYOL ownership independently.
        await self.app(scope, receive, send)
