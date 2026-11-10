"""Read-only diagnostics must detect stale configuration without disclosing secrets."""

import json
import sys
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.voice.vaani import VaaniError
from tools import vaani_preflight as preflight


@pytest.fixture
def config(monkeypatch):
    settings = Settings(
        _env_file=None,
        vaani_api_key="vaani_synthetic-private-key",
        vaani_agent_id="00000000-0000-4000-8000-000000000123",
        vaani_byol_token="synthetic-byol-private-credential",
        vaani_webhook_secret="synthetic-webhook-private-credential",
        vaani_staging_base_url="https://synthetic.trycloudflare.com",
    )
    monkeypatch.setattr(preflight, "get_settings", lambda: settings)
    return settings


@pytest.mark.parametrize("stale", [False, True])
def test_runtime_equality_is_private_and_reports_stale_key(config, monkeypatch, stale):
    values = {
        "VAANI_API_KEY": "old-private-key" if stale else config.vaani_api_key.get_secret_value(),
        "VAANI_AGENT_ID": config.vaani_agent_id,
        "VAANI_BYOL_TOKEN": config.vaani_byol_token.get_secret_value(),
        "VAANI_WEBHOOK_SECRET": config.vaani_webhook_secret.get_secret_value(),
        "VAANI_STAGING_BASE_URL": config.vaani_staging_base_url,
    }
    response = json.dumps(
        [
            {
                "Config": {"Env": [key + "=" + value for key, value in values.items()]},
                "State": {"Status": "running"},
            }
        ]
    )
    monkeypatch.setattr(
        preflight.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=response)
    )
    result = preflight.container_audit()
    assert result["consistent"] is (not stale)
    assert result["matches"]["VAANI_API_KEY"] is (not stale)
    assert all(value not in json.dumps(result) for value in values.values())


def test_inspection_errors_never_echo_private_docker_output(config, monkeypatch):
    monkeypatch.setattr(
        preflight.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            returncode=1, stdout="private credential", stderr="private credential"
        ),
    )
    result = preflight.container_audit()
    assert result["consistent"] is False
    assert "private credential" not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_auth_failures_retain_safe_numeric_status(config, monkeypatch, status):
    async def forbidden(*args):
        raise VaaniError("authentication", status_code=status)

    monkeypatch.setattr(preflight.VaaniVoiceProvider, "list_agents", forbidden)
    result = await preflight.check()
    assert result["http_status"] == status and result["authenticated"] is False
    assert config.vaani_api_key.get_secret_value() not in json.dumps(result)


def test_stale_runtime_stops_before_any_provider_request(config, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["preflight", "--container"])
    monkeypatch.setattr(preflight, "container_audit", lambda: {"consistent": False})

    async def forbidden():
        raise AssertionError("No provider request may use an unconfirmed runtime")

    monkeypatch.setattr(preflight, "check", forbidden)
    with pytest.raises(SystemExit) as error:
        preflight.main()
    assert error.value.code == 1
    assert json.loads(capsys.readouterr().out)["provider"] is None
