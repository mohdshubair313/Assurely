"""POST /v1/message — primary conversation endpoint.

Accepts a user message, runs it through the LangGraph pipeline, and
returns the response with citations and metadata per LLD § 7.5:
    {session_id, reply, citations[], escalation?, missing_fields,
     calculator_outputs, draft_output, hidden_clauses, transparency_scores}
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.security import optional_authenticated_user_id, require_matching_user_id
from app.core.tracing import request_trace
from app.db.session import AsyncSessionLocal
from app.graph.build_graph import build_graph
from app.graph.state import create_initial_state
from app.models.db.consent_record import ConsentRecord
from app.models.db.user_profile_memory import UserProfileMemory

logger = logging.getLogger(__name__)
router = APIRouter()

# Graph instance cached for application lifetime
_app_graph = build_graph()


class MessageRequest(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: uuid.UUID | None = None
    user_message: str
    target_language: str = "en"


class MessageResponse(BaseModel):
    session_id: str
    reply: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    escalation: bool = False
    escalation_reason: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    calculator_outputs: dict[str, Any] = Field(default_factory=dict)
    # Stage 3 outputs (compare_verify)
    draft_output: dict[str, Any] = Field(default_factory=dict)
    hidden_clauses: list[dict[str, Any]] = Field(default_factory=list)
    transparency_scores: dict[str, Any] = Field(default_factory=dict)
    # Stage 4 outputs (guardrail)
    approved: bool = False
    guardrail_notes: list[str] = Field(default_factory=list)
    output: dict[str, Any] = Field(default_factory=dict)
    delivery_hold: bool = True
    notification_status: str = "not_requested"


def build_message_response(session_id: str, state: dict[str, Any]) -> MessageResponse:
    """Enforce delivery separately from generation, including all side channels.

    Never edit graph output to hide it. Redact only this public response. Missing
    gate/approval fields fail closed; queue acknowledgement cannot authorize release.
    """
    notification = state.get("advisor_notification", {})
    status = notification.get("status", "not_requested")
    if status not in {"not_requested", "queued", "failed", "unconfigured"}:
        status = "failed"
    generated_report = state.get("output", {})
    report_ready = (
        isinstance(generated_report, dict)
        and generated_report.get("report_status") == "ready"
        and bool(generated_report.get("reply"))
        and bool(generated_report.get("sentences"))
    )
    held = (
        state.get("delivery_hold") is not False
        or state.get("approved") is not True
        or state.get("escalation") is True
        or bool(notification)
        or not report_ready
    )
    missing = state.get("missing_fields", [])
    if held:
        # Operational messages only. Raw assistant text, guardrail diagnostics and
        # escalation reasons could contain withheld claims or sensitive details.
        questions = {
            "age": "Could you please share your age?",
            "city_tier": "Which city do you live in?",
            "dependents": "How many family members would you like to include?",
            "pre_existing_conditions": (
                "Do any covered family members have pre-existing health conditions?"
            ),
        }
        review_pending = state.get("escalation") is True or bool(notification)
        if missing:
            reply = questions.get(missing[0], "Please complete the remaining profile details.")
        elif review_pending:
            reply = "Your report is held for advisor review. It has not been released."
        elif state.get("intent") == "life":
            reply = (
                "This phase supports health insurance only. Would you like help with health cover?"
            )
        elif state.get("intent") == "unclear":
            reply = "Could you clarify what health insurance information you need?"
        else:
            reply = "The response is awaiting validation and has not been released."
        return MessageResponse(
            session_id=session_id,
            reply=reply,
            delivery_hold=True,
            escalation=state.get("escalation", False),
            escalation_reason="Advisor review is required before delivery."
            if review_pending
            else None,
            missing_fields=missing,
            approved=state.get("approved", False),
            notification_status=status,
        )

    # Forward an already-generated report without generating or mutating output.
    # explanation_report remains the sole future writer of that state field.
    output = generated_report
    return MessageResponse(
        session_id=session_id,
        reply=output.get("reply", "Analysis is ready. The report step is pending."),
        output=output,
        delivery_hold=False,
        notification_status=status,
        citations=state.get("retrieved_facts", []),
        missing_fields=missing,
        approved=True,
        calculator_outputs=state.get("calculator_outputs", {}),
        draft_output=state.get("draft_output", {}),
        hidden_clauses=state.get("hidden_clauses", []),
        transparency_scores=state.get("transparency_scores", {}),
        guardrail_notes=state.get("guardrail_notes", []),
    )


@router.post("/message", response_model=MessageResponse)
async def send_message(
    req: MessageRequest,
    authenticated_user_id: Annotated[
        uuid.UUID | None, Depends(optional_authenticated_user_id)
    ],
) -> MessageResponse:
    """Run a user turn through the LangGraph insurance advisor pipeline."""
    try:
        if req.user_id is not None:
            if authenticated_user_id is None:
                raise HTTPException(status_code=401, detail="A verified bearer token is required.")
            require_matching_user_id(authenticated_user_id, req.user_id)
        user_id = authenticated_user_id
        consent = {"granted": False, "scopes": []}
        saved_profile: dict[str, Any] = {}
        if user_id is not None:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(ConsentRecord.scope).where(
                        ConsentRecord.user_id == user_id,
                        ConsentRecord.scope == "save_profile",
                        ConsentRecord.revoked_at.is_(None),
                    )
                )
                scopes = list(result.scalars().all())
                if scopes:
                    memory = await db.get(UserProfileMemory, user_id)
                    if memory is not None and isinstance(memory.profile_snapshot_json, dict):
                        saved_profile = memory.profile_snapshot_json
            consent = {"granted": bool(scopes), "scopes": scopes}
        with request_trace(
            req.session_id,
            message_char_count=len(req.user_message),
        ) as trace:
            config: RunnableConfig = {"configurable": {"thread_id": req.session_id}}
            current_checkpoint = await _app_graph.aget_state(config)

            if (
                current_checkpoint
                and current_checkpoint.values
                and current_checkpoint.values.get("messages")
            ):
                prior_user_id = current_checkpoint.values.get("user_id")
                requested_user_id = str(user_id) if user_id else None
                if prior_user_id != requested_user_id:
                    raise HTTPException(
                        status_code=409,
                        detail="The user_id for an existing session cannot be changed.",
                    )
                # Multi-turn continuation: append user message to existing state
                prev_messages = list(current_checkpoint.values.get("messages", []))
                new_messages = prev_messages + [{"role": "user", "content": req.user_message}]
                # Reset prior approval if intake/intent exits before the delivery gate.
                input_state: dict[str, Any] = {
                    "messages": new_messages,
                    "user_id": requested_user_id,
                    "consent": consent,
                    "approved": False,
                    "delivery_hold": True,
                }
            else:
                input_state = dict(
                    create_initial_state(
                        session_id=req.session_id,
                        user_message=req.user_message,
                        user_id=str(user_id) if user_id else None,
                        consent=consent,
                        user_profile=saved_profile,
                        target_language=req.target_language,
                    )
                )

            final_state = await _app_graph.ainvoke(input_state, config=config)
            response = build_message_response(req.session_id, final_state)
            if trace is not None:
                trace.update(
                    output={
                        "approved": response.approved,
                        "escalation": response.escalation,
                        "delivery_hold": response.delivery_hold,
                        "notification_status": response.notification_status,
                        "missing_field_count": len(response.missing_fields),
                    }
                )

        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error processing message for session %s: %s", req.session_id, e)
        raise HTTPException(
            status_code=500, detail="Unable to process this turn; no report was released."
        ) from e
