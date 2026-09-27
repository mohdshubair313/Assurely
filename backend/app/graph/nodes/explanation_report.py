"""Stage 5: render a sourced explanation for the user and advisor review."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any

from app.graph.nodes.guardrail import check_ranking_language, check_unlicensed_advice
from app.graph.state import SessionState
from app.llm.fallback_chain import llm_call

logger = logging.getLogger(__name__)

_SUPPORTED_LANGUAGES = {"en", "hi", "hi-en-mixed"}
_SYSTEM_PROMPT = """You write a concise health-insurance explanation for India.
Use only the supplied evidence. Do not add facts, numbers, eligibility conclusions,
recommendations, or promises. Do not repeat internal guardrail notes. Do not use
prohibited sales or comparison language. Write in the requested language.
Return raw JSON only in this shape:
{"sentences":[{"text":"one evidence-grounded sentence","evidence_ids":["E1"]}]}
Every sentence must cite one or more supplied evidence IDs. Do not output any
other keys or markdown. If evidence is insufficient, return {"sentences":[]}.
"""


class ExplanationReportError(ValueError):
    """The report could not be safely grounded in source evidence."""


def _verified_date(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    if len(candidate) == 10:
        try:
            date.fromisoformat(candidate)
        except ValueError:
            return None
    else:
        try:
            datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            return None
    return candidate


def _evidence_catalog(state: SessionState) -> list[dict[str, str]]:
    """Collect only claims that have both a source and a valid verification date."""
    evidence: list[dict[str, str]] = []

    def add(claim: Any, source: Any, verified: Any, url: Any = "") -> None:
        verified_date = _verified_date(verified)
        if not isinstance(claim, str) or not claim.strip():
            return
        if not isinstance(source, str) or not source.strip() or verified_date is None:
            return
        row = {
            "id": f"E{len(evidence) + 1}",
            "claim": claim.strip(),
            "source": source.strip(),
            "last_verified": verified_date,
        }
        if isinstance(url, str) and url.strip():
            row["url"] = url.strip()
        evidence.append(row)

    draft = state.get("draft_output", {})
    for fact in draft.get("cited_facts", []):
        if isinstance(fact, dict):
            add(fact.get("claim"), fact.get("source"), fact.get("last_verified"), fact.get("url"))

    for fact in state.get("retrieved_facts", []):
        if isinstance(fact, dict):
            add(fact.get("claim"), fact.get("source"), fact.get("last_verified"), fact.get("url"))

    # Deterministic policy facts are copied from sourced policy_terms fields.
    for policy in draft.get("need_fit_view", []):
        if not isinstance(policy, dict):
            continue
        label = " ".join(
            str(policy.get(key, "")).strip()
            for key in ("insurer", "product_name")
            if policy.get(key)
        )
        for field, description in (
            ("sum_insured_range_inr", "Sum insured range"),
            ("entry_age_window", "Entry age window"),
            ("waiting_period_days_preexisting", "Pre-existing condition waiting period"),
            ("premium_estimate", "Premium estimate"),
        ):
            term = policy.get(field)
            if not isinstance(term, dict):
                continue
            value = term.get("value")
            if value is None and field == "sum_insured_range_inr":
                value = f"INR {term.get('min')} to {term.get('max')}"
            elif value is None and field == "entry_age_window":
                value = f"{term.get('min')} to {term.get('max')} years"
            elif value is None and field == "premium_estimate":
                value = term.get("annual_premium_inr")
            if value is None:
                continue
            add(
                f"{description} for {label}: {value}",
                term.get("source"),
                term.get("last_verified"),
            )
    return evidence


def _parse_sentences(content: str, evidence: list[dict[str, str]]) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ExplanationReportError("Report provider returned invalid JSON") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("sentences"), list):
        raise ExplanationReportError("Report response did not contain a sentence list")

    by_id = {item["id"]: item for item in evidence}
    result: list[dict[str, Any]] = []
    for sentence in parsed["sentences"]:
        if not isinstance(sentence, dict):
            raise ExplanationReportError("Report sentence has an invalid shape")
        text = sentence.get("text")
        evidence_ids = sentence.get("evidence_ids")
        if not isinstance(text, str) or not text.strip() or not isinstance(evidence_ids, list):
            raise ExplanationReportError("Report sentence is missing text or citations")
        if not evidence_ids or any(
            not isinstance(item, str) or item not in by_id for item in evidence_ids
        ):
            raise ExplanationReportError("Report sentence cites unknown evidence")
        if check_ranking_language(text) or check_unlicensed_advice(text):
            raise ExplanationReportError("Report sentence failed compliance validation")
        citations = [by_id[item] for item in dict.fromkeys(evidence_ids)]
        result.append({"text": text.strip(), "citations": citations})
    return result


async def explanation_report_node(state: SessionState) -> dict[str, Any]:
    """Render sourced explanation; escalation affects delivery, never generation."""
    evidence = _evidence_catalog(state)
    language = state.get("target_language", "en")
    if language not in _SUPPORTED_LANGUAGES:
        language = "en"

    if evidence:
        evidence_json = json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
        guardrail_notes = state.get("guardrail_notes", [])
        notes_json = json.dumps(
            [note for note in guardrail_notes if isinstance(note, str)],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        try:
            result = await llm_call(
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Target language: {language}\n"
                            f"Guardrail notes (internal; do not repeat): {notes_json}\n"
                            f"Verified evidence: {evidence_json}"
                        ),
                    }
                ],
                system_prompt=_SYSTEM_PROMPT,
                task_type="explanation_report",
                session_id=state.get("session_id"),
                temperature=0.1,
                max_tokens=2048,
            )
            sentences = _parse_sentences(result.content, evidence)
        except Exception:
            # Keep the graph moving so `escalate` can still notify and hold.
            # The empty report remains undeliverable at the API boundary.
            logger.exception(
                "explanation_report failed for session=%s; output remains empty",
                state.get("session_id"),
            )
            return {"output": {}}
    else:
        # No sourced material means no factual report can safely be rendered.
        sentences = []

    output = {
        "reply": " ".join(
            f"{item['text']} "
            + " ".join(
                f"[Source: {citation['source']}; last verified: {citation['last_verified']}]"
                for citation in item["citations"]
            )
            for item in sentences
        ),
        "sentences": sentences,
        "target_language": language,
        "evidence_count": len(evidence),
        "report_status": "ready" if sentences else "insufficient_verified_evidence",
    }
    logger.info(
        "explanation_report: session=%s evidence=%d sentences=%d escalation=%s",
        state.get("session_id"),
        len(evidence),
        len(sentences),
        state.get("escalation") is True,
    )
    return {"output": output}
