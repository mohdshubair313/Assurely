"""intent_router — classifies the user's need into a product type.

Trigger: user_profile is complete (missing_fields is empty).
Reads:   user_profile, messages.
Writes:  intent ("health" | "life" | "unclear"), messages.
Calls:   LLM classification (cheap/fast model via Groq via llm_call()).

The intent value drives the Stage 2 parallel fan-out via deterministic
conditional edges — this routing decision MUST be code, never an LLM
deciding "what should happen next" (AGENTS.md rule 2).

For Phase 1: health insurance only. The intent_router is wired as a
real conditional (not skipped), with deterministic handling for
health, deferred life (Phase 5), and unclear intent.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.graph.state import SessionState
from app.llm.fallback_chain import llm_call

logger = logging.getLogger(__name__)

INTENT_CLASSIFICATION_PROMPT = """You are an insurance intent classification engine for the Indian insurance market.
Analyze the user conversation and profile to classify intent into exactly one of three categories:
1. "health": User wants mediclaim, health insurance, hospitalization cover, family floater, critical illness, or medical expense protection.
2. "life": User wants term insurance, term life, death cover, income replacement, or pure protection life cover.
3. "unclear": User asked a general question or did not specify whether they need health or life insurance.

Return ONLY a valid JSON object with:
{
  "intent": "health" | "life" | "unclear",
  "confidence": float (0.0 to 1.0),
  "reasoning": "brief explanation"
}
Do not wrap in markdown or markdown code blocks. Output raw JSON only.
"""


def _rule_based_classify_intent(messages: list[dict[str, Any]]) -> str:
    """Deterministic keyword fallback if LLM classification fails."""
    combined_text = " ".join(m.get("content", "") for m in messages).lower()

    health_keywords = ["health", "mediclaim", "hospital", "illness", "medical", "disease", "floater", "doctor", "cashless"]
    life_keywords = ["term life", "life insurance", "death benefit", "pure term", "nominee", "human life value", "hlv"]

    has_health = any(k in combined_text for k in health_keywords)
    has_life = any(k in combined_text for k in life_keywords)

    if has_health and not has_life:
        return "health"
    elif has_life and not has_health:
        return "life"
    elif has_health and has_life:
        # If both mentioned, prioritize health for Phase 1 scope
        return "health"
    return "unclear"


async def intent_router_node(state: SessionState) -> dict[str, Any]:
    """Execute the intent_router node.

    Classifies user intent into 'health', 'life', or 'unclear'
    and updates state.
    """
    messages = list(state.get("messages", []))
    session_id = state.get("session_id", "default_session")

    intent = "unclear"
    try:
        llm_res = await llm_call(
            messages=messages,
            system_prompt=INTENT_CLASSIFICATION_PROMPT,
            task_type="router",
            session_id=session_id,
            temperature=0.0,
        )
        raw = llm_res.content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?", "", raw).rstrip("`").strip()
        parsed = json.loads(raw)
        detected_intent = str(parsed.get("intent", "")).lower()
        if detected_intent in ("health", "life", "unclear"):
            intent = detected_intent
    except Exception as e:
        logger.warning("LLM intent routing failed, using rule-based classifier: %s", e)
        intent = _rule_based_classify_intent(messages)

    updates: dict[str, Any] = {"intent": intent}

    if intent == "unclear":
        # Formulate clarifying question to distinguish health vs life
        clarification = (
            "Could you clarify whether you are looking for health insurance "
            "(hospitalization and medical bill cover) or term life insurance (financial protection for family)?"
        )
        updates["messages"] = messages + [{"role": "assistant", "content": clarification}]
    elif intent == "life":
        # Phase 1 scope disclosure
        disclosure = (
            "We currently specialize in health insurance advisory in Phase 1. "
            "Life insurance coverage sizing and plan comparisons will be available in Phase 5."
        )
        updates["messages"] = messages + [{"role": "assistant", "content": disclosure}]

    logger.info("Intent routed for session %s: %s", session_id, intent)
    return updates
