"""Persist per-turn decision provenance and consent-gated profile memory.

Decision traces are operational/compliance evidence and are written on every
completed graph turn regardless of profile-memory consent. Profile memory is a
separate JSONB record keyed by explicit user identity, loaded only after an
active save_profile consent receipt, and removed on revocation or deletion.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.tracing import current_llm_metadata
from app.db.session import AsyncSessionLocal
from app.graph.state import SessionState
from app.models.db.decision_trace import DecisionTrace
from app.models.db.policy_document import PolicyDocument
from app.models.db.policy_terms import PolicyTerms
from app.models.db.session import Session as DBSession
from app.models.db.user import User
from app.models.db.user_profile_memory import UserProfileMemory

logger = logging.getLogger(__name__)
_SESSION_NAMESPACE = uuid.UUID("3c8b8c8f-a4c5-4b19-9ec8-413f5a11c92e")


def _database_session_id(value: str) -> uuid.UUID:
    """Preserve UUID session IDs; map arbitrary API IDs stably for the FK."""
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        return uuid.uuid5(_SESSION_NAMESPACE, value)


def _json_safe(value: Any) -> Any:
    """Normalize state values to JSON-compatible data for JSONB columns."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (Decimal, uuid.UUID)):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _sources_per_claim(state: SessionState) -> dict[str, list[dict[str, Any]]]:
    sources: dict[str, list[dict[str, Any]]] = {}
    evidence = list(state.get("retrieved_facts", []))
    evidence.extend(state.get("draft_output", {}).get("cited_facts", []))
    for group in state.get("hidden_clauses", []):
        evidence.extend(group.get("clauses", []))
    for claim in evidence:
        if not isinstance(claim, dict):
            continue
        text = claim.get("claim") or claim.get("clause")
        if not text:
            continue
        sources.setdefault(str(text), []).append(
            {
                key: claim[key]
                for key in ("source", "url", "last_verified", "retrieved_at", "conflict")
                if claim.get(key) is not None
            }
        )
    return sources


def _profile_memory_consent_granted(state: SessionState) -> bool:
    """Require an explicit identity and durable save_profile consent receipt."""
    consent = state.get("consent") or {}
    return (
        bool(state.get("user_id"))
        and consent.get("granted") is True
        and "save_profile" in consent.get("scopes", [])
    )


async def persist_memory_node(state: SessionState) -> dict[str, Any]:
    """Write the unconditional decision trace; never infer profile consent."""
    raw_session_id = str(state.get("session_id") or "")
    if not raw_session_id:
        raise ValueError("persist_memory requires a session_id")
    session_id = _database_session_id(raw_session_id)
    requested_user_id = state.get("user_id")
    user_id = uuid.UUID(requested_user_id) if requested_user_id else uuid.uuid5(
        _SESSION_NAMESPACE, f"user:{session_id}"
    )

    async with AsyncSessionLocal() as db:
        await db.execute(
            insert(User)
            .values(id=user_id, role="customer")
            .on_conflict_do_nothing(index_elements=[User.id])
        )
        await db.execute(
            insert(DBSession)
            .values(id=session_id, user_id=user_id, intent=state.get("intent"))
            .on_conflict_do_nothing(index_elements=[DBSession.id])
        )
        owner_result = await db.execute(
            select(DBSession.user_id).where(DBSession.id == session_id)
        )
        if owner_result.scalar_one() != user_id:
            raise ValueError("The session_id is already associated with another user_id")

        policy_versions: list[dict[str, str]] = []
        if state.get("draft_output", {}).get("stage") == "compare_verify":
            stmt = (
                select(PolicyTerms, PolicyDocument)
                .join(PolicyDocument, PolicyTerms.policy_document_id == PolicyDocument.id)
                .where(PolicyTerms.expiry_date.is_(None))
            )
            result = await db.execute(stmt)
            policy_versions = [
                {
                    "policy_id": str(document.id),
                    "product_name": document.product_name,
                    "document_version_hash": document.version_hash,
                    "terms_version_hash": terms.version_hash,
                }
                for terms, document in result.all()
            ]

        llm_metadata = current_llm_metadata()
        profile = _json_safe(state.get("user_profile", {}))
        confidence_inputs = _json_safe(state.get("confidence_inputs", {}))
        if not confidence_inputs and state.get("confidence_score") is None:
            confidence_inputs = {"status": "guardrail_not_reached"}
        trace = DecisionTrace(
            session_id=session_id,
            user_profile_snapshot_json=profile,
            policy_versions_evaluated_json=policy_versions,
            clauses_retrieved_json=_json_safe(state.get("retrieved_facts", [])),
            rules_engine_output_json=_json_safe(
                {
                    "calculator_outputs": state.get("calculator_outputs", {}),
                    "hidden_clauses": state.get("hidden_clauses", []),
                    "approved": state.get("approved"),
                    "escalation": state.get("escalation"),
                    "escalation_reason": state.get("escalation_reason"),
                    "guardrail_notes": state.get("guardrail_notes", []),
                    "report_status": state.get("output", {}).get("report_status"),
                }
            ),
            sources_per_claim_json=_json_safe(_sources_per_claim(state)),
            model_version=llm_metadata["model_version"],
            prompt_version=llm_metadata["prompt_version"],
            confidence_score=state.get("confidence_score"),
            confidence_inputs_json=confidence_inputs,
        )
        db.add(trace)
        save_profile = _profile_memory_consent_granted(state)
        if save_profile:
            await db.execute(
                insert(UserProfileMemory)
                .values(user_id=user_id, profile_snapshot_json=profile)
                .on_conflict_do_update(
                    index_elements=[UserProfileMemory.user_id],
                    set_={
                        "profile_snapshot_json": profile,
                        "updated_at": func.now(),
                    },
                )
            )
        await db.commit()

    logger.info("persist_memory: decision trace written for session %s", session_id)
    return {
        "decision_trace_persisted": True,
        "profile_memory_persisted": save_profile,
    }
