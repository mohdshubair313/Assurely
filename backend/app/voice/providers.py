"""Provider interface for the synthetic local voice slice."""

from dataclasses import dataclass, field
from typing import Protocol

from pydantic import SecretStr


@dataclass(frozen=True)
class ProviderSession:
    provider: str
    provider_call_id: str | None
    room_id: str | None
    audio_connected: bool
    connection_url: str | None = None
    access_token: SecretStr | None = field(default=None, repr=False)
    live_captions_url: SecretStr | None = field(default=None, repr=False)


class VoiceProvider(Protocol):
    async def create_session(self, *, session_id: str, language: str) -> ProviderSession: ...


class MockVoiceProvider:
    """A no-network/no-audio provider used only for allowlisted demo users."""

    async def create_session(self, *, session_id: str, language: str) -> ProviderSession:
        del session_id, language
        return ProviderSession("mock", None, None, False)
