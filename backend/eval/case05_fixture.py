"""Guarded, opt-in CASE05 fixture preparation for a disposable eval database.

No database is created or dropped here. The orchestrator must provision a new
empty database first and retain its provenance until live verification finishes.
This module never writes the shared Chroma corpus or invokes model providers.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "case05_archived_policy.json"
CASE_ID = "case_05_outdated_policy"
_DATABASE_NAME = re.compile(r"insurance_case05_eval_[a-f0-9]{12}\Z")


def validate_database_name(name: str) -> str:
    if not isinstance(name, str) or not _DATABASE_NAME.fullmatch(name):
        raise ValueError("CASE05 requires a uniquely named isolated evaluation database")
    return name


def isolated_database_url(url: str, name: str, cases: list[str]) -> str:
    """Change only the target database; never print credentials or accept SQL names."""
    validate_database_name(name)
    if cases != [CASE_ID]:
        raise ValueError("The isolated CASE05 database may run case 05 only")
    parsed = urlsplit(url)
    if parsed.scheme != "postgresql+asyncpg" or not parsed.netloc or parsed.query:
        raise ValueError("Expected a configured asyncpg URL without connection overrides")
    if parsed.path == f"/{name}":
        raise ValueError("Isolated database must differ from the application database")
    return urlunsplit(parsed._replace(path=f"/{name}", fragment=""))


def fixture_records() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return source-labelled ORM kwargs without making any database connections."""
    raw = FIXTURE_PATH.read_bytes()
    fixture = json.loads(raw)
    if fixture["fixture_kind"] != "synthetic_isolated_evaluation_only":
        raise ValueError("CASE05 fixture must remain explicitly synthetic")
    version = hashlib.sha256(raw).hexdigest()
    document = {
        "id": uuid.UUID(fixture["policy_document_id"]),
        "insurer": fixture["insurer"],
        "product_name": fixture["product_name"],
        "doc_url": fixture["doc_url"],
        "version_hash": version,
        "ingested_at": datetime.fromisoformat(fixture["recorded_at"]),
    }
    terms = {
        "id": uuid.UUID(fixture["policy_terms_id"]),
        "policy_document_id": document["id"],
        "version_hash": version,
        "effective_date": date.fromisoformat(fixture["effective_date"]),
        "expiry_date": date.fromisoformat(fixture["expiry_date"]),
    }
    provenance = {
        "kind": fixture["fixture_kind"],
        "notice": fixture["notice"],
        "fixture_sha256": version,
        "policy_document_id": str(document["id"]),
        "policy_terms_id": str(terms["id"]),
        "shared_policy_database_modified": False,
        "chroma_modified": False,
    }
    return document, terms, provenance


async def prepare_isolated_database(database_name: str) -> dict[str, Any]:
    """Initialize only a matching, empty disposable DB; fail before any writes otherwise."""
    from sqlalchemy import text

    from app.db.seed import seed_data
    from app.db.session import AsyncSessionLocal, async_engine
    from app.models.db import Base
    from app.models.db.policy_document import PolicyDocument
    from app.models.db.policy_terms import PolicyTerms

    validate_database_name(database_name)
    if async_engine.url.database != database_name:
        raise ValueError("Connected engine does not target the requested isolated database")
    async with async_engine.begin() as connection:
        actual = await connection.scalar(text("SELECT current_database()"))
        if actual != database_name:
            raise ValueError("Connected database does not match the isolated database")
        count = await connection.scalar(text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema NOT IN ('pg_catalog', 'information_schema')"
        ))
        if count != 0:
            raise ValueError("CASE05 requires an empty newly provisioned database")
        await connection.run_sync(Base.metadata.create_all)
    document, terms, provenance = fixture_records()
    async with AsyncSessionLocal() as session:
        # seed_data uses Postgres only; do not call seed.main (which seeds Chroma).
        await seed_data(session)
        session.add(PolicyDocument(**document))
        await session.flush()
        session.add(PolicyTerms(**terms))
        await session.commit()
    return {"database": database_name, **provenance}


async def verify_isolated_database(database_name: str) -> dict[str, Any]:
    """Read the fixture back; a previous preparation is required, never reseed."""
    from sqlalchemy import select, text

    from app.db.session import AsyncSessionLocal, async_engine
    from app.models.db.policy_document import PolicyDocument
    from app.models.db.policy_terms import PolicyTerms

    validate_database_name(database_name)
    if async_engine.url.database != database_name:
        raise ValueError("Connected engine does not target the requested isolated database")
    document, terms, provenance = fixture_records()
    async with AsyncSessionLocal() as session:
        if await session.scalar(text("SELECT current_database()")) != database_name:
            raise ValueError("Connected database does not match the isolated database")
        row = (await session.execute(
            select(PolicyTerms, PolicyDocument)
            .join(PolicyDocument, PolicyTerms.policy_document_id == PolicyDocument.id)
            .where(PolicyTerms.id == terms["id"])
        )).one_or_none()
        if row is None or any(
            getattr(row[index], key) != value
            for index, expected in ((0, terms), (1, document))
            for key, value in expected.items()
        ):
            raise ValueError("Isolated CASE05 fixture missing or different from its manifest")
    return {"database": database_name, **provenance}
