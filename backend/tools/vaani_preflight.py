"""Read-only provider authentication/owned-agent check; never dispatches a call."""

import argparse
import asyncio
import hmac
import json
import subprocess
import uuid

from app.core.config import get_settings
from app.voice.vaani import VaaniError, VaaniVoiceProvider


def local_audit() -> dict[str, object]:
    settings = get_settings()
    key = settings.vaani_api_key.get_secret_value()
    try:
        uuid.UUID(settings.vaani_agent_id)
        valid_agent = True
    except ValueError:
        valid_agent = False
    return {
        "key_present": bool(key),
        "key_has_surrounding_whitespace": key != key.strip(),
        "key_has_bearer_prefix": key.lower().startswith("bearer "),
        "key_has_control_character": any(ord(char) < 32 for char in key),
        "key_matches_documented_prefix": key.startswith("vaani_"),
        "agent_uuid_valid": valid_agent,
        "api_origin": "https://api.vaanivoice.ai",
        "auth_header": "X-API-Key",
        "byol_variable": "VAANI_BYOL_TOKEN",
        "customer_dispatch_enabled": False,
    }


def container_audit() -> dict[str, object]:
    """Compare the named local runtime privately; Docker environment output never prints."""
    settings = get_settings()
    expected = {
        "VAANI_API_KEY": settings.vaani_api_key.get_secret_value(),
        "VAANI_AGENT_ID": settings.vaani_agent_id,
        "VAANI_BYOL_TOKEN": settings.vaani_byol_token.get_secret_value(),
        "VAANI_WEBHOOK_SECRET": settings.vaani_webhook_secret.get_secret_value(),
        "VAANI_STAGING_BASE_URL": settings.vaani_staging_base_url,
    }
    try:
        response = subprocess.run(
            ["docker", "inspect", "--type", "container", "insurance-api"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if response.returncode:
            raise ValueError("Runtime inspection failed")
        instance = json.loads(response.stdout)[0]
        runtime = dict(item.split("=", 1) for item in instance["Config"]["Env"] if "=" in item)
        matches = {
            name: bool(value)
            and hmac.compare_digest(value.encode(), runtime.get(name, "").encode())
            for name, value in expected.items()
        }
        running = instance["State"]["Status"] == "running"
        return {
            "checked": True,
            "running": running,
            "matches": matches,
            "consistent": running and all(matches.values()),
        }
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, IndexError, TypeError):
        return {
            "checked": True,
            "consistent": False,
            "reason": "Runtime could not be safely inspected",
        }


async def check() -> dict[str, object]:
    settings = get_settings()
    provider = VaaniVoiceProvider(settings)
    result: dict[str, object] = {"dispatch_attempted": False, "authenticated": False}
    try:
        agents = await provider.list_agents()
        result.update(authenticated=True, first_page_agent_count=len(agents))
        # Agent configuration is never dumped; names may contain customer information.
        if settings.vaani_agent_id:
            agent = await provider.validate_agent()
            result.update(configured_agent_owned=True, agent_id=str(agent.id))
        else:
            result["configured_agent_owned"] = False
    except VaaniError as exc:
        result["error_category"] = exc.category
        if exc.status_code is not None:
            result["http_status"] = exc.status_code
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline", action="store_true", help="Inspect config without provider requests"
    )
    parser.add_argument(
        "--container", action="store_true", help="Privately compare insurance-api environment first"
    )
    args = parser.parse_args()
    runtime = container_audit() if args.container else None
    remote = None
    if not args.offline and (runtime is None or runtime.get("consistent") is True):
        remote = asyncio.run(check())
    result = {"configuration": local_audit(), "container": runtime, "provider": remote}
    print(json.dumps(result))
    if runtime is not None and runtime.get("consistent") is not True:
        raise SystemExit(1)
    if remote is not None and (
        remote.get("authenticated") is not True or remote.get("configured_agent_owned") is not True
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
