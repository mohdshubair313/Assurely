"""Managed Vaani lifecycle, separate from direct dispatch. No automatic POST retries.

Contract: official SDK 0.3.1 resources/sessions.py, inspected 2026-11-08.
Provider master/session tokens remain server-side. Live acceptance is still required.
"""

import logging
import uuid
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AwareDatetime, BaseModel, Field, SecretStr, ValidationError

from app.voice.vaani import ROOM_PATTERN, VaaniError, VaaniVoiceProvider, trusted_url


class ManagedURLFilter(logging.Filter):
    """The official status contract embeds a session credential in its URL path."""

    def filter(self, record: logging.LogRecord) -> bool:
        if "/api/webrtc/session/status/" in record.getMessage():
            record.msg, record.args = "Managed voice status request [credential redacted]", ()
        return True


logging.getLogger("httpx").addFilter(ManagedURLFilter())


class ManagedSession(BaseModel):
    session_token: SecretStr = Field(min_length=20, max_length=8192)
    expires_at: AwareDatetime


class ManagedStatus(BaseModel):
    status: Literal["created", "agent_ready", "active", "reconnecting", "ended", "expired"]
    room_name: str = Field(pattern=ROOM_PATTERN)
    agent_id: uuid.UUID


class ManagedConnection(BaseModel):
    lk_url: str = Field(max_length=2048)
    lk_token: SecretStr = Field(min_length=20, max_length=8192)
    room_name: str = Field(pattern=ROOM_PATTERN)


class ManagedVaaniProvider(VaaniVoiceProvider):
    async def create(self, reference: uuid.UUID, cap: int) -> ManagedSession:
        if not 60 <= cap <= 1800:
            raise VaaniError("duration_contract")
        try:
            agent = uuid.UUID(self.settings.vaani_agent_id)
            return ManagedSession.model_validate(
                await self._request(
                    "POST",
                    "/api/webrtc/session/create",
                    {
                        "agent_id": str(agent),
                        "ui_type": "widget",
                        "grace_period": 20,
                        "session_ttl": cap,
                        "initial_message": (
                            "I am an AI guide. Fictional development audio only; no policy advice."
                        ),
                        "metadata": {"assurely_voice_reference": str(reference)},
                    },
                )
            )
        except (ValidationError, ValueError):
            raise VaaniError("managed_create_contract") from None

    async def status(self, token: SecretStr) -> ManagedStatus:
        # This endpoint embeds a credential. Never log the URL, response or exception body.
        value = token.get_secret_value()
        if (
            not value
            or len(value) > 8192
            or any(
                c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
                for c in value
            )
        ):
            raise VaaniError("managed_token_contract")
        try:
            result = ManagedStatus.model_validate(
                await self._request("GET", "/api/webrtc/session/status/" + value)
            )
        except ValidationError:
            raise VaaniError("managed_status_contract") from None
        if str(result.agent_id) != self.settings.vaani_agent_id:
            raise VaaniError("agent_mismatch")
        return result

    async def connect(self, token: SecretStr) -> ManagedConnection:
        try:
            result = ManagedConnection.model_validate(
                await self._request(
                    "POST",
                    "/api/webrtc/session/connect",
                    {"session_token": token.get_secret_value()},
                )
            )
        except ValidationError:
            raise VaaniError("managed_connect_contract") from None
        if (
            not trusted_url(result.lk_url, {"rtc.vaanivoice.ai", "livekit.vaanivoice.ai"})
            or urlsplit(result.lk_url).query
        ):
            raise VaaniError("connection_host")
        if any(char.isspace() for char in result.lk_token.get_secret_value()):
            raise VaaniError("managed_connect_contract")
        return result

    async def terminate(self, token: SecretStr) -> ManagedStatus:
        try:
            result = ManagedStatus.model_validate(
                await self._request(
                    "POST",
                    "/api/webrtc/session/disconnect",
                    {"session_token": token.get_secret_value(), "explicit_end": True},
                )
            )
        except ValidationError:
            raise VaaniError("managed_end_contract") from None
        if str(result.agent_id) != self.settings.vaani_agent_id or result.status not in (
            "ended",
            "expired",
        ):
            raise VaaniError("termination_unconfirmed")
        return result
