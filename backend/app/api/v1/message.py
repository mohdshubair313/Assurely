"""POST /v1/message — primary conversation endpoint.

Accepts a user message, runs it through the LangGraph pipeline, and
returns the response with citations and metadata per LLD § 7.5:
    {session_id, reply, citations[], escalation?, missing_fields,
     calculator_outputs, draft_output, hidden_clauses, transparency_scores}
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.graph.build_graph import build_graph
from app.graph.state import create_initial_state

logger = logging.getLogger(__name__)
router = APIRouter()

# Graph instance cached for application lifetime
_app_graph = build_graph()


class MessageRequest(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
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


@router.post("/message", response_model=MessageResponse)
async def send_message(req: MessageRequest) -> MessageResponse:
    """Run a user turn through the LangGraph insurance advisor pipeline."""
    try:
        config = {"configurable": {"thread_id": req.session_id}}
        current_checkpoint = await _app_graph.aget_state(config)

        if current_checkpoint and current_checkpoint.values and current_checkpoint.values.get("messages"):
            # Multi-turn continuation: append new user message to existing conversation state
            prev_messages = list(current_checkpoint.values.get("messages", []))
            new_messages = prev_messages + [{"role": "user", "content": req.user_message}]
            input_state: dict[str, Any] = {"messages": new_messages}
        else:
            # First turn: create clean initial state
            input_state = dict(
                create_initial_state(
                    session_id=req.session_id,
                    user_message=req.user_message,
                    target_language=req.target_language,
                )
            )

        final_state = await _app_graph.ainvoke(input_state, config=config)

        # Extract reply from assistant messages: only if generated on this turn
        msgs = final_state.get("messages", [])
        reply = ""
        if msgs and msgs[-1].get("role") == "assistant":
            reply = msgs[-1].get("content", "")

        if not reply and not final_state.get("missing_fields"):
            draft = final_state.get("draft_output", {})
            calcs = final_state.get("calculator_outputs", {})

            if draft.get("need_fit_view"):
                # Stage 3 complete: build a need-fit summary (no ranking language)
                policies_count = draft.get("total_policies_evaluated", 0)
                target_si = draft.get("risk_adjusted_target_si_inr", {}).get("value", 0)
                high_count = sum(
                    e.get("hidden_clause_count", {}).get("high", 0)
                    for e in draft["need_fit_view"]
                )
                scores = final_state.get("transparency_scores", {})
                score_summary = ", ".join(
                    f"{k.split('|')[1] if '|' in k else k}: {v}/100"
                    for k, v in scores.items()
                )
                reply = (
                    f"Analysis complete across {policies_count} policies. "
                    f"Risk-adjusted coverage target: ₹{target_si:,.0f}. "
                    f"Transparency scores — {score_summary}. "
                    f"{high_count} high-severity clause(s) flagged that directly affect "
                    f"your profile. Review the full analysis in the response."
                )
            elif "risk_analysis" in calcs:
                risk = calcs["risk_analysis"]
                net_inr = risk.get("risk_adjusted_sum_insured_inr", 0)
                reply = (
                    f"Profile assessment & risk analysis complete. Based on your healthcare cost profile, "
                    f"the risk-adjusted recommended sum insured is ₹{net_inr:,}."
                )
            elif "health_cover_sizing" in calcs:
                sizing = calcs["health_cover_sizing"]
                net_inr = sizing.get("net_recommended_sum_insured_inr", 0)
                reply = (
                    f"Profile assessment complete. Based on your location ({sizing.get('city_tier')}) "
                    f"and healthcare costs, the calculated recommended sum insured is ₹{net_inr:,}."
                )

        return MessageResponse(
            session_id=req.session_id,
            reply=reply,
            citations=final_state.get("retrieved_facts", []),
            escalation=final_state.get("escalation", False),
            escalation_reason=final_state.get("escalation_reason"),
            missing_fields=final_state.get("missing_fields", []),
            calculator_outputs=final_state.get("calculator_outputs", {}),
            draft_output=final_state.get("draft_output", {}),
            hidden_clauses=final_state.get("hidden_clauses", []),
            transparency_scores=final_state.get("transparency_scores", {}),
            approved=final_state.get("approved", False),
            guardrail_notes=final_state.get("guardrail_notes", []),
        )
    except Exception as e:
        logger.exception("Error processing message for session %s: %s", req.session_id, e)
        raise HTTPException(status_code=500, detail=str(e))
