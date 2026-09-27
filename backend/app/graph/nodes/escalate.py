"""Notify an advisor queue and independently hold customer delivery.

This node never writes or mutates output. A queue acknowledgement is not advisor
approval. The same hold applies to real and test receivers and all failure paths.
The interim graph calls this after guardrail; after review, explanation_report
must be inserted unconditionally before this node.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import Settings, get_settings
from app.graph.state import SessionState

logger = logging.getLogger(__name__)


def _event_id(state: SessionState) -> str:
    """Stable across retries/restarts; a material case revision is a new event."""

    def material(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: material(item)
                for key, item in value.items()
                if key not in {"generated_at", "retrieved_at"}
            }
        if isinstance(value, list):
            return [material(item) for item in value]
        return value

    case = {
        "session_id": state.get("session_id"),
        "user_profile": state.get("user_profile", {}),
        "draft": state.get("draft_output", {}),
        "output": state.get("output", {}),
        "approved": state.get("approved", False),
        "reason": state.get("escalation_reason"),
    }
    canonical = json.dumps(material(case), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "advisor-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _valid_destination(url: str, settings: Settings) -> bool:
    try:
        parsed = urlsplit(url)
        if not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            return False
        return parsed.scheme == "https" or (
            settings.environment == "development"
            and parsed.scheme == "http"
            and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        )
    except ValueError:
        return False


async def dispatch_notification(
    payload: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    """POST a real queue event; require an explicit, matching durable-queue ACK.

    The receiver must atomically deduplicate Idempotency-Key/event_id and commit
    the event before returning {queued: true, event_id: ...}. A timeout after a
    commit is safe to retry under that receiver contract. No redirects followed.
    """
    event_id = payload["event_id"]
    receipt: dict[str, Any] = {"event_id": event_id, "status": "failed", "attempts": 0}
    url = settings.advisor_webhook_url
    if not url:
        return {**receipt, "status": "unconfigured"}
    if not _valid_destination(url, settings):
        return {**receipt, "error": "invalid_destination"}

    headers = {"Idempotency-Key": event_id}
    token = settings.advisor_webhook_token.get_secret_value()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(
        timeout=settings.advisor_webhook_timeout_seconds,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        for attempt in range(1, settings.advisor_webhook_max_attempts + 1):
            receipt["attempts"] = attempt
            try:
                response = await client.post(url, json=payload, headers=headers)
                if 200 <= response.status_code < 300:
                    try:
                        ack = response.json()
                    except ValueError:
                        ack = None
                    if (
                        isinstance(ack, dict)
                        and ack.get("queued") is True
                        and ack.get("event_id") == event_id
                    ):
                        receipt.pop("error", None)
                        return {**receipt, "status": "queued"}
                    return {**receipt, "error": "invalid_acknowledgement"}
                receipt["error"] = "receiver_rejected"
                if response.status_code != 429 and response.status_code < 500:
                    return receipt
            except httpx.RequestError:
                # Do not expose URLs, credentials or remote response bodies.
                receipt["error"] = "transport_failure"
            if attempt < settings.advisor_webhook_max_attempts:
                await asyncio.sleep(
                    settings.advisor_webhook_retry_delay_seconds * 2 ** (attempt - 1)
                )
    return receipt


async def escalate_node(state: SessionState) -> dict[str, Any]:
    """Set delivery_hold and a queue receipt; NEVER return an output update.

    A prior review request remains held even if a later guardrail pass is clean.
    Authenticated advisor sign-off/release is deliberately not implemented here.
    """
    previous = dict(state.get("advisor_notification", {}))
    needs_review = state.get("escalation") is True or state.get("approved") is not True
    if not needs_review and not previous:
        return {"delivery_hold": False, "advisor_notification": {}}

    # This is independent of any transport/configuration/acknowledgement result.
    held: dict[str, Any] = {"delivery_hold": True, "advisor_notification": previous}
    try:
        settings = get_settings()
        event_id = _event_id(state)
        destination_id = hashlib.sha256(settings.advisor_webhook_url.encode()).hexdigest()
        if (
            previous.get("event_id") == event_id
            and previous.get("status") == "queued"
            and previous.get("destination_id") == destination_id
        ):
            return held
        payload = {
            "event_id": event_id,
            "event_type": "advisor_review_requested",
            "session_id": state["session_id"],
            "reason": state.get("escalation_reason") or "Advisor review remains required.",
            "approved": state.get("approved") is True,
            "report_available": bool(state.get("output")),
            "delivery_hold": True,
        }
        receipt = await dispatch_notification(payload, settings)
        held["advisor_notification"] = {**receipt, "destination_id": destination_id}
    except Exception:
        # Failure cannot turn a pending human review into automatic delivery.
        logger.error("Advisor notification could not be confirmed; delivery remains held")
        held["advisor_notification"] = {**previous, "status": "failed", "error": "dispatch_failure"}
    return held
