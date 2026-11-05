"""Validate user-supplied local Clerk settings; never print credential values.

Read-only provider calls: public JWKS and the fixed Clerk Backend API JWKS route.
Only after matching keys are verified, normalize ignored local environment files.
"""

import base64
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values, set_key, unset_key


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    backend = root / "backend/.env"
    frontend = root / "frontend/.env.local"
    source = dotenv_values(backend)
    targets = dotenv_values(frontend) if frontend.exists() else {}
    aliases = {
        "CLERK_PUBLISHABLE_KEY": "CLERK_PUBLISHABLE_KEYS",
        "CLERK_SECRET_KEY": "CLERK_SECREY_KEYS",
        "AUTH_JWKS_URL": "JWKS_URL",
    }
    values = {}
    for canonical, old in aliases.items():
        value = source.get(canonical) or source.get(old)
        if not value or (
            source.get(canonical) and source.get(old) != source[canonical] and source.get(old)
        ):
            raise SystemExit(
                "Missing or conflicting local Clerk configuration; no values displayed."
            )
        values[canonical] = value
    public = values["CLERK_PUBLISHABLE_KEY"]
    secret = values["CLERK_SECRET_KEY"]
    mode = (
        "test" if public.startswith("pk_test_") else "live" if public.startswith("pk_live_") else ""
    )
    if not mode or not secret.startswith(f"sk_{mode}_"):
        raise SystemExit("Clerk key formats/environments do not match; no files changed.")
    encoded = public.split("_", 2)[2]
    host = base64.b64decode(encoded + "=" * (-len(encoded) % 4), validate=True).decode().rstrip("$")
    issuer = "https://" + host
    parsed = urlsplit(issuer)
    expected = issuer + "/.well-known/jwks.json"
    if (
        parsed.hostname != host
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
        or values["AUTH_JWKS_URL"] != expected
    ):
        raise SystemExit(
            "Publishable key and supplied JWKS origin/path do not match; no files changed."
        )
    checks = {}
    try:
        with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
            exposed = client.get(expected)
            owned = client.get(
                "https://api.clerk.com/v1/jwks", headers={"Authorization": f"Bearer {secret}"}
            )
            checks["public_jwks_reachable"] = exposed.status_code == 200
            checks["backend_secret_accepted"] = owned.status_code == 200
            keys_a = exposed.json().get("keys", []) if exposed.status_code == 200 else []
            keys_b = owned.json().get("keys", []) if owned.status_code == 200 else []
            checks["public_and_secret_instance_match"] = bool(
                {(row.get("n"), row.get("e")) for row in keys_a if row.get("kty") == "RSA"}
                & {(row.get("n"), row.get("e")) for row in keys_b if row.get("kty") == "RSA"}
            )
    except Exception:
        raise SystemExit(
            "Clerk connectivity validation failed; no credentials displayed or files changed."
        ) from None
    print(json.dumps({"provider_checks": checks}))
    if not all(checks.values()):
        raise SystemExit("Clerk credential checks failed; local files unchanged.")
    origin = targets.get("APP_ORIGIN") or "http://localhost:3000"
    updates = {
        **values,
        "AUTH_PROVIDER": "clerk",
        "AUTH_ISSUER": issuer,
        "AUTH_AUTHORIZED_PARTIES": json.dumps([origin]),
    }
    front_updates = {
        "NEXT_PUBLIC_AUTH_PROVIDER": "clerk",
        "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY": public,
        "CLERK_SECRET_KEY": secret,
        "APP_ORIGIN": origin,
        "BACKEND_URL": targets.get("BACKEND_URL") or "http://127.0.0.1:8000",
    }
    for name, value in front_updates.items():
        if targets.get(name) and targets[name] != value:
            raise SystemExit("Existing frontend configuration conflicts; no files changed.")
    for name, value in updates.items():
        set_key(backend, name, value)
    for old in aliases.values():
        if old in source:
            unset_key(backend, old)
    for name, value in front_updates.items():
        set_key(frontend, name, value)
    receipt = {
        "provider_checks": checks,
        "local_configuration_aligned": True,
        "development_instance": mode == "test",
        "secret_values_displayed": False,
        "authenticated_session_e2e_verified": False,
        "production_deployed": False,
    }
    (root / "artifacts").mkdir(exist_ok=True)
    (root / "artifacts/clerk-config-check-20261104.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "local_configuration_aligned": True,
                "secret_values_displayed": False,
                "production_deployed": False,
            }
        )
    )


if __name__ == "__main__":
    main()
