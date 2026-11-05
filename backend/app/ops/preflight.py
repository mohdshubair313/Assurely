"""Read-only deployment checks; emits no secrets and never grants source approval."""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core.config import Settings, get_settings
from app.core.security import _auth_configuration
from app.db.session import AsyncSessionLocal


def _https(value: str) -> bool:
    try:
        url = urlsplit(value)
        return bool(
            url.scheme == "https" and url.hostname and not url.username and not url.password
        )
    except ValueError:
        return False


def configuration_checks(settings: Settings) -> dict[str, bool]:
    groups = [
        settings.policy_reviewer_subjects,
        settings.policy_publisher_subjects,
        settings.advisor_subjects,
    ]
    if settings.auth_provider == "clerk":
        groups.append(settings.admin_subjects)
    try:
        valid_roles = all(
            group and all(str(UUID(value)) == value for value in group) for group in groups
        )
    except (ValueError, TypeError):
        valid_roles = False
    try:
        _auth_configuration(settings)
        valid_identity = _https(settings.auth_issuer) and _https(settings.auth_jwks_url)
    except (HTTPException, ValueError):
        valid_identity = False
    database = make_url(settings.database_url)
    redis = urlsplit(settings.redis_url)
    return {
        "non_development": settings.environment in {"staging", "production"},
        "trusted_gateway_configured": len(settings.backend_gateway_token.get_secret_value()) >= 32,
        "identity_configured": valid_identity,
        "explicit_operator_roles": valid_roles,
        "separate_review_and_publication_roles": bool(groups[0] and groups[1])
        and not set(groups[0]) & set(groups[1]),
        "advisor_destination_configured": _https(settings.advisor_webhook_url)
        and bool(settings.advisor_webhook_token.get_secret_value()),
        "provider_configured": any(
            (settings.groq_api_key, settings.gemini_api_key, settings.openrouter_api_key)
        ),
        "database_password_not_development_default": bool(database.password)
        and database.password not in {"insurance_dev", "postgres", "password"},
        "database_verified_tls": database.query.get("ssl") == "verify-full",
        "redis_authenticated_tls": redis.scheme == "rediss" and bool(redis.password),
        "explicit_browser_origins": all(
            value != "*" and _https(value) for value in settings.cors_origins
        ),
    }


async def database_checks() -> dict[str, bool]:
    result = {"application_schema": False, "checkpoint_schema": False}
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        async with AsyncSessionLocal() as db, db.begin():
            await db.execute(text("SET TRANSACTION READ ONLY"))
            revisions: list[str] = list(
                (await db.execute(text("SELECT version_num FROM alembic_version"))).scalars()
            )
            result["application_schema"] = revisions == ["010_clerk_identity"]
            version = await db.scalar(text("SELECT MAX(v) FROM checkpoint_migrations"))
            result["checkpoint_schema"] = version == len(AsyncPostgresSaver.MIGRATIONS) - 1
    except Exception:
        # Database errors may contain credentials/host details; never print them.
        pass
    return result


async def report(check_database: bool) -> dict[str, Any]:
    checks = configuration_checks(get_settings())
    if check_database:
        checks.update(await database_checks())
    return {
        "scope": "infrastructure_configuration_only",
        "checks": checks,
        "database_checked": check_database,
        "configuration_passed": all(checks.values()),
        "production_release_authorized": False,
        "external_evidence_required": [
            "Qualified real policy/tariff review and authenticated publication/import",
            "Calculator assumption approval or exclusion from delivered scope",
            "Live identity and independent advisor notification/delivery verification",
            "Database backup/restore, retention, encryption and deployment capacity review",
            "Customer/advisor browser journey using genuine deployment identities",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(report(args.database))
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["configuration_passed"] else 1)


if __name__ == "__main__":
    main()
