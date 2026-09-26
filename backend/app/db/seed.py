"""Seed script for populating policy_terms, policy_documents, and audit_log tables.

Can be run standalone via:
  python -m app.db.seed

Populates:
  - 3 Real Indian Health Insurance policy documents (HDFC ERGO, Care, Star Health)
  - policy_terms with deterministic limits, waiting periods, exclusions, and rate tables
  - Seed user, active session, and starter audit_log entry
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.db.audit_log import AuditLog
from app.models.db.policy_document import PolicyDocument
from app.models.db.policy_terms import PolicyTerms
from app.models.db.session import Session
from app.models.db.user import User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SEED_POLICIES = [
    {
        "insurer": "HDFC ERGO General Insurance",
        "product_name": "Optima Secure",
        "doc_url": "https://www.hdfcergo.com/policy-wordings/optima-secure.pdf",
        "version_hash": hashlib.sha256(b"hdfc-optima-secure-2024-v1").hexdigest(),
        "terms": {
            "sum_insured_min": Decimal("500000.00"),     # 5 Lakhs
            "sum_insured_max": Decimal("20000000.00"),   # 2 Crores
            "entry_age_min": 18,
            "entry_age_max": 65,
            "waiting_period_days_preexisting": 1095,      # 36 months / 3 years
            "exclusions_json": [
                "Investigation & evaluation admission without active treatment",
                "Rest cure, rehabilitation and respite care",
                "Obesity/weight control treatments",
                "Cosmetic or plastic surgery",
                "Hazardous or adventure sports",
                "Breach of law / criminal acts",
                "Maternity expenses unless explicitly purchased as rider",
            ],
            "premium_rate_table_json": {
                "base_5L": {"age_18_35": 9400, "age_36_45": 14100, "age_46_55": 22300, "age_56_65": 38200},
                "base_10L": {"age_18_35": 12800, "age_36_45": 18900, "age_46_55": 30500, "age_56_65": 51000},
                "base_25L": {"age_18_35": 18500, "age_36_45": 27200, "age_46_55": 43800, "age_56_65": 72500},
            },
            "effective_date": date(2024, 1, 1),
            "expiry_date": None,
        },
    },
    {
        "insurer": "Care Health Insurance",
        "product_name": "Care Supreme",
        "doc_url": "https://www.careinsurance.com/policy-wordings/care-supreme.pdf",
        "version_hash": hashlib.sha256(b"care-supreme-2024-v1").hexdigest(),
        "terms": {
            "sum_insured_min": Decimal("500000.00"),     # 5 Lakhs
            "sum_insured_max": Decimal("10000000.00"),   # 1 Crore
            "entry_age_min": 18,
            "entry_age_max": 99,
            "waiting_period_days_preexisting": 1095,      # 36 months / 3 years
            "exclusions_json": [
                "Cosmetic surgery or aesthetic treatments",
                "Dental treatment or surgery unless necessitated by accidental injury",
                "Circumcision unless necessary for treatment of disease",
                "Experimental or unproven treatments",
                "Self-inflicted injuries",
            ],
            "premium_rate_table_json": {
                "base_5L": {"age_18_35": 8200, "age_36_45": 12600, "age_46_55": 20400, "age_56_65": 34500},
                "base_10L": {"age_18_35": 11400, "age_36_45": 17100, "age_46_55": 27800, "age_56_65": 46900},
                "base_25L": {"age_18_35": 16200, "age_36_45": 24300, "age_46_55": 39500, "age_56_65": 65800},
            },
            "effective_date": date(2024, 1, 1),
            "expiry_date": None,
        },
    },
    {
        "insurer": "Star Health and Allied Insurance",
        "product_name": "Star Comprehensive",
        "doc_url": "https://www.starhealth.in/policy-wordings/star-comprehensive.pdf",
        "version_hash": hashlib.sha256(b"star-comprehensive-2024-v1").hexdigest(),
        "terms": {
            "sum_insured_min": Decimal("500000.00"),     # 5 Lakhs
            "sum_insured_max": Decimal("10000000.00"),   # 1 Crore
            "entry_age_min": 18,
            "entry_age_max": 65,
            "waiting_period_days_preexisting": 1095,      # 36 months / 3 years
            "exclusions_json": [
                "Cosmetic and plastic surgery",
                "Treatment for alcoholism, drug or substance abuse",
                "War, riot, and nuclear weapons risk",
                "Congenital external diseases or defects",
                "Stem cell therapy and non-allopathic treatments without accreditation",
            ],
            "premium_rate_table_json": {
                "base_5L": {"age_18_35": 8900, "age_36_45": 13400, "age_46_55": 21500, "age_56_65": 36800},
                "base_10L": {"age_18_35": 12100, "age_36_45": 18200, "age_46_55": 29400, "age_56_65": 49800},
                "base_25L": {"age_18_35": 17400, "age_36_45": 26100, "age_46_55": 42100, "age_56_65": 70200},
            },
            "effective_date": date(2024, 1, 1),
            "expiry_date": None,
        },
    },
]


async def seed_data(session: AsyncSession) -> dict[str, int]:
    """Insert seed policy documents, terms, user, session, and audit log."""
    counts = {"policy_documents": 0, "policy_terms": 0, "users": 0, "sessions": 0, "audit_log": 0}

    # 1. Seed Policy Documents & Terms
    for pdata in SEED_POLICIES:
        # Check if already exists by version_hash
        stmt = select(PolicyDocument).where(PolicyDocument.version_hash == pdata["version_hash"])
        res = await session.execute(stmt)
        doc = res.scalar_one_or_none()

        if not doc:
            doc = PolicyDocument(
                insurer=pdata["insurer"],
                product_name=pdata["product_name"],
                doc_url=pdata["doc_url"],
                version_hash=pdata["version_hash"],
            )
            session.add(doc)
            await session.flush()
            counts["policy_documents"] += 1

            terms_data = pdata["terms"]
            terms = PolicyTerms(
                policy_document_id=doc.id,
                version_hash=pdata["version_hash"],
                sum_insured_min=terms_data["sum_insured_min"],
                sum_insured_max=terms_data["sum_insured_max"],
                entry_age_min=terms_data["entry_age_min"],
                entry_age_max=terms_data["entry_age_max"],
                waiting_period_days_preexisting=terms_data["waiting_period_days_preexisting"],
                exclusions_json=terms_data["exclusions_json"],
                premium_rate_table_json=terms_data["premium_rate_table_json"],
                effective_date=terms_data["effective_date"],
                expiry_date=terms_data["expiry_date"],
            )
            session.add(terms)
            counts["policy_terms"] += 1

    # 2. Seed Customer User
    seed_phone_hash = hashlib.sha256(b"+919876543210").hexdigest()
    stmt = select(User).where(User.phone_hash == seed_phone_hash)
    res = await session.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        user = User(
            phone_hash=seed_phone_hash,
            email_hash=hashlib.sha256(b"shubair@example.com").hexdigest(),
            role="customer",
        )
        session.add(user)
        await session.flush()
        counts["users"] += 1

    # 3. Seed Active Session
    session_stmt = select(Session).where(Session.user_id == user.id)
    s_res = await session.execute(session_stmt)
    user_session = s_res.scalar_one_or_none()

    if not user_session:
        user_session = Session(
            user_id=user.id,
            intent="health",
        )
        session.add(user_session)
        await session.flush()
        counts["sessions"] += 1

    # 4. Seed Audit Log Entry
    audit_stmt = select(AuditLog).where(AuditLog.session_id == user_session.id)
    a_res = await session.execute(audit_stmt)
    audit_entry = a_res.scalar_one_or_none()

    if not audit_entry:
        audit_entry = AuditLog(
            session_id=user_session.id,
            node_name="needs_intake",
            input_hash=hashlib.sha256(b'{"user_message": "Looking for health insurance for family"}').hexdigest(),
            output_hash=hashlib.sha256(b'{"missing_fields": ["age", "city_tier"]}').hexdigest(),
            sources_json=[
                {
                    "source": "HDFC ERGO Optima Secure Policy Wordings 2024",
                    "clause": "Entry Age & Pre-existing Waiting Period",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }
            ],
        )
        session.add(audit_entry)
        counts["audit_log"] += 1

    await session.commit()
    logger.info("Database seeding complete: %s", counts)
    return counts


async def main() -> None:
    async with AsyncSessionLocal() as session:
        await seed_data(session)


if __name__ == "__main__":
    asyncio.run(main())
