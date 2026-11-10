"""Bounded Vaani REST adapter. It is not wired to the customer start API."""

from __future__ import annotations

import re
import uuid
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, SecretStr, ValidationError

from app.core.config import Settings
from app.voice.providers import ProviderSession

API_BASE = "https://api.vaanivoice.ai"
ROOM_PATTERN = r"^[A-Za-z0-9_-]{1,160}$"


class VaaniError(Exception):
    def __init__(self, category: str, *, status_code: int | None = None) -> None:
        self.category = category
        self.status_code = status_code
        super().__init__(f"Voice provider unavailable ({category}).")


class Agent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: uuid.UUID = Field(validation_alias=AliasChoices("id", "agent_id"))
    display_name: str = Field(
        default="",
        max_length=200,
        validation_alias=AliasChoices("display_name", "agent_display_name"),
    )


class WebRTCRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: uuid.UUID
    medium: Literal["webrtc"] = "webrtc"
    primary_language: Literal["en", "hi"]
    secondary_language: Literal["en"] = "en"
    welcome_message: str = (
        "I am an AI insurance guide. This development call uses fictional examples only."
    )
    metadata: dict[str, str]
    modify_agent: dict[str, object]


class WebRTCResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    token: SecretStr = Field(min_length=16, max_length=8192)
    room_name: str = Field(pattern=ROOM_PATTERN)
    connection_url: str = Field(max_length=2048)
    live_captions_url: SecretStr | None = Field(default=None)


def trusted_url(value: str, hosts: set[str], *, scheme: str = "wss") -> bool:
    try:
        url = urlsplit(value)
        return (
            url.scheme == scheme
            and url.hostname in hosts
            and url.port in (None, 443)
            and not url.username
            and not url.password
            and not url.fragment
        )
    except ValueError:
        return False


class VaaniVoiceProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.client = client

    async def _request(
        self, method: str, path: str, payload: dict[str, object] | None = None
    ) -> object:
        key = self.settings.vaani_api_key.get_secret_value()
        if not key:
            raise VaaniError("missing_key")
        client = self.client or httpx.AsyncClient()
        try:
            # No redirect following or POST retry: a timeout may have created a real call.
            async with client.stream(
                method,
                API_BASE + path,
                headers={"X-API-Key": key},
                json=payload,
                timeout=httpx.Timeout(20, connect=5),
                follow_redirects=False,
            ) as response:
                if response.status_code in (401, 403):
                    raise VaaniError("authentication", status_code=response.status_code)
                if response.status_code == 429:
                    raise VaaniError("rate_limited", status_code=response.status_code)
                if not 200 <= response.status_code < 300:
                    raise VaaniError("upstream_status", status_code=response.status_code)
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 262144:
                        raise VaaniError("response_too_large")
                import json

                return json.loads(body)
        except (httpx.TimeoutException, httpx.NetworkError):
            raise VaaniError("uncertain_transport") from None
        except (ValueError, httpx.HTTPError):
            raise VaaniError("invalid_response") from None
        finally:
            if self.client is None:
                await client.aclose()

    async def list_agents(self) -> list[Agent]:
        body = await self._request("GET", "/api/agents?page=1&page_size=100")
        if isinstance(body, dict):
            body = body.get("data", body.get("items"))
        if not isinstance(body, list) or len(body) > 100:
            raise VaaniError("agent_contract")
        try:
            return [Agent.model_validate(item) for item in body]
        except ValidationError:
            raise VaaniError("agent_contract") from None

    async def validate_agent(self) -> Agent:
        try:
            expected = uuid.UUID(self.settings.vaani_agent_id)
        except ValueError:
            raise VaaniError("missing_agent") from None
        try:
            agent = Agent.model_validate(await self._request("GET", f"/api/agents/{expected}"))
        except ValidationError:
            raise VaaniError("agent_contract") from None
        if agent.id != expected:
            raise VaaniError("agent_mismatch")
        return agent

    def capabilities(self) -> dict[str, bool]:
        return {
            "webrtc_documented": True,
            "customer_calls_enabled": False,
            "hard_termination_verified": False,
            "insurance_tools_enabled": False,
            "synthetic_dispatch_opt_in": self.settings.vaani_dispatch_enabled,
        }

    async def create_session(self, *, session_id: str, language: str) -> ProviderSession:
        # No public API invokes this method in V2a. Explicit development flags are additional gates.
        if (
            not self.settings.vaani_dispatch_enabled
            or not self.settings.vaani_dev_agent_reviewed
            or not self.settings.vaani_byol_enabled
            or not self.settings.vaani_ingress_enabled
            or self.settings.environment not in ("development", "staging")
            or len(self.settings.vaani_byol_token.get_secret_value()) < 32
            or len(self.settings.vaani_webhook_secret.get_secret_value()) < 32
        ):
            raise VaaniError("development_gate")
        parsed = urlsplit(self.settings.vaani_staging_base_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
        ):
            raise VaaniError("staging_gate")
        try:
            reference = str(uuid.UUID(session_id))
        except ValueError:
            raise VaaniError("session_reference") from None
        if language not in ("en", "hi"):
            raise VaaniError("language_unverified")
        agent = await self.validate_agent()
        websocket_url = (
            self.settings.vaani_staging_base_url.rstrip("/").replace("https://", "wss://", 1)
            + "/v1/voice/provider/byol"
        )
        request = WebRTCRequest(
            agent_id=agent.id,
            primary_language=language,
            metadata={"assurely_voice_reference": reference},
            modify_agent={
                "persona": {
                    "senses_capabilities": {
                        "brain": {
                            "llm": {
                                "extra_params": {
                                    "fallback": "none",
                                    "llm_websocket_url": websocket_url,
                                }
                            }
                        }
                    }
                }
            },
        )
        try:
            result = WebRTCResponse.model_validate(
                await self._request("POST", "/api/trigger-call/", request.model_dump(mode="json"))
            )
        except ValidationError:
            raise VaaniError("webrtc_contract") from None
        if (
            not trusted_url(result.connection_url, {"rtc.vaanivoice.ai", "livekit.vaanivoice.ai"})
            or urlsplit(result.connection_url).query
        ):
            raise VaaniError("connection_host")
        if result.live_captions_url:
            value = result.live_captions_url.get_secret_value()
            url = urlsplit(value)
            if (
                len(value) > 8192
                or not trusted_url(value, {"api.vaanivoice.ai"})
                or url.path != f"/api/live-transcripts/ws/{result.room_name}"
                or not url.query
            ):
                raise VaaniError("captions_host")
        return ProviderSession(
            "vaani",
            result.room_name,
            result.room_name,
            False,
            result.connection_url,
            result.token,
            result.live_captions_url,
        )


def valid_room(value: str) -> bool:
    return re.fullmatch(ROOM_PATTERN, value) is not None
