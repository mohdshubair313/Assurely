"""needs_intake — multi-turn profiling and the Missing Info Detector loop.

Trigger: session start OR missing_fields is non-empty.
Reads:   user_profile, messages, missing_fields.
Writes:  user_profile, missing_fields, calculator_outputs, messages.
Calls:   LLM (Groq via llm_call() for extraction and conversational turns),
         calculator functions (health_cover_sizing).

This node LOOPS on itself while ``missing_fields`` is non-empty:
  - On each turn, it extracts user details or asks for the next required piece of info.
  - Once all required fields are filled, it runs the calculators
    (ideal health cover sizing) and clears missing_fields.
  - The loop is a conditional edge in the graph (needs_intake → needs_intake
    while missing_fields non-empty), not an internal while-loop (AGENTS.md rule 2).

The calculators it calls are deterministic, zero-LLM (AGENTS.md rule 5).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.calculators.health_cover_sizing import calculate_health_cover_sizing
from app.graph.state import SessionState
from app.llm.fallback_chain import llm_call

logger = logging.getLogger(__name__)

REQUIRED_HEALTH_FIELDS = ["age", "city_tier", "dependents", "pre_existing_conditions"]
OPTIONAL_HEALTH_FIELDS = ["is_nri", "existing_coverage"]

EXTRACTION_SYSTEM_PROMPT = """You are an insurance intake assistant in India.
Extract user profile fields from the conversation. Return ONLY a valid JSON object with keys:
- "age": integer or null (e.g. 35)
- "city_tier": string ("tier_1" for metros like Mumbai/Delhi/Bengaluru/Chennai/Hyderabad/Kolkata,
  "tier_2" for large cities like Pune/Jaipur/Ahmedabad/Lucknow, "tier_3" for others) or null
- "dependents": integer or null (count of family members to cover)
- "pre_existing_conditions": boolean or list of strings or null
  (e.g. diabetes, hypertension, asthma)
- "existing_coverage": integer in INR or 0
- "is_nri": boolean or null (true if user mentions living abroad, NRI status, or overseas residence)

If a field is not mentioned, set its value to null.
Do not wrap in markdown or extra text. Output JSON only.
"""


def _rule_based_extract(text: str, current_profile: dict[str, Any]) -> dict[str, Any]:
    """Deterministic fallback extraction for numbers and keywords."""
    extracted = dict(current_profile)
    text_lower = text.lower()

    # Age extraction: "32 years", "age 32", "i am 32"
    if "age" not in extracted or extracted["age"] is None:
        age_match = re.search(
            r"\b(?:age\s*(?:is\s*)?|i am\s*|i'm\s*)?(\d{1,2})\s*(?:years?\s*old|yrs?|years?)?\b",
            text_lower,
        )
        if age_match:
            val = int(age_match.group(1))
            if 18 <= val <= 100:
                extracted["age"] = val

    # City tier extraction
    if "city_tier" not in extracted or extracted["city_tier"] is None:
        metros = ["mumbai", "delhi", "bangalore", "bengaluru", "chennai", "hyderabad", "kolkata"]
        tier_2 = [
            "pune",
            "ahmedabad",
            "jaipur",
            "lucknow",
            "chandigarh",
            "kochi",
            "surat",
            "indore",
        ]
        if any(m in text_lower for m in metros) or "tier 1" in text_lower or "metro" in text_lower:
            extracted["city_tier"] = "tier_1"
        elif any(t in text_lower for t in tier_2) or "tier 2" in text_lower:
            extracted["city_tier"] = "tier_2"
        elif "tier 3" in text_lower or "town" in text_lower or "village" in text_lower:
            extracted["city_tier"] = "tier_3"

    # Pre-existing conditions
    if "pre_existing_conditions" not in extracted or extracted["pre_existing_conditions"] is None:
        if any(
            neg in text_lower
            for neg in [
                "no illness",
                "no disease",
                "healthy",
                "no pre-existing",
                "no preexisting",
                "none",
                "no health issue",
                "no condition",
            ]
        ):
            extracted["pre_existing_conditions"] = False
        elif any(
            pos in text_lower
            for pos in ["diabetes", "bp", "hypertension", "thyroid", "asthma", "heart", "surgery"]
        ):
            extracted["pre_existing_conditions"] = True

    # Dependents
    if "dependents" not in extracted or extracted["dependents"] is None:
        dep_match = re.search(r"\b(\d+)\s*(?:dependents?|family members?|members?)\b", text_lower)
        if dep_match:
            extracted["dependents"] = int(dep_match.group(1))
        elif (
            "no dependents" in text_lower
            or "zero dependents" in text_lower
            or "myself only" in text_lower
            or "individual" in text_lower
            or "single" in text_lower
            or "just me" in text_lower
        ):
            extracted["dependents"] = 0
        elif "wife" in text_lower or "husband" in text_lower or "spouse" in text_lower:
            dep_count = 1
            if "kid" in text_lower or "child" in text_lower:
                dep_count += 1
            extracted["dependents"] = dep_count

    # NRI status (flagged if user declares living abroad or NRI status)
    # Explicit declarations can correct a prior turn; word boundaries avoid
    # incidental substrings, and negation must not become an NRI declaration.
    if re.search(
        r"\b(?:not (?:an? )?(?:nri|non[- ]resident)|no longer (?:an? )?nri|"
        r"not living abroad|(?<!non-)(?<!non )resident indian)\b",
        text_lower,
    ):
        extracted["is_nri"] = False
    elif re.search(
        r"\b(?:nri|non[- ]resident|living abroad|living in (?:dubai|uae|us|usa|uk|singapore))\b",
        text_lower,
    ):
        extracted["is_nri"] = True

    return extracted


def _normalize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Keep calculator inputs in their declared types before checking completeness."""
    normalized = dict(profile)
    for field in ("age", "dependents", "existing_coverage"):
        value = normalized.get(field)
        if isinstance(value, str) and re.fullmatch(r"\d+", value.strip()):
            value = int(value)
        if type(value) is int and value >= (1 if field == "age" else 0):
            normalized[field] = value
        else:
            normalized.pop(field, None)
    if normalized.get("city_tier") not in ("tier_1", "tier_2", "tier_3"):
        normalized.pop("city_tier", None)
    ped = normalized.get("pre_existing_conditions")
    if not isinstance(ped, bool) and not (
        isinstance(ped, list) and all(isinstance(item, str) and item.strip() for item in ped)
    ):
        normalized.pop("pre_existing_conditions", None)
    return normalized


async def needs_intake_node(state: SessionState) -> dict[str, Any]:
    """Execute the needs_intake node.

    Extracts user details, computes missing fields, and runs deterministic
    calculators when the profile is complete.
    """
    user_profile = _normalize_profile(state.get("user_profile", {}))
    messages = list(state.get("messages", []))
    session_id = state.get("session_id", "default_session")

    # Get latest user message
    last_user_msg = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user_msg = msg.get("content", "")
            break

    # 1. Attempt LLM-based profile extraction if we have user input
    if last_user_msg:
        try:
            llm_res = await llm_call(
                messages=[{"role": "user", "content": last_user_msg}],
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                task_type="intake",
                session_id=session_id,
                temperature=0.0,
            )
            raw = llm_res.content.strip()
            # Clean markdown JSON block if returned
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?", "", raw).rstrip("`").strip()
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("Intake extraction must be a JSON object")
            for k, v in _normalize_profile(parsed).items():
                if v is not None and k in REQUIRED_HEALTH_FIELDS + OPTIONAL_HEALTH_FIELDS:
                    user_profile[k] = v
            # Preserve explicit NRI declarations even if model extraction omits
            # this optional field; missing_fields and routing stay unchanged.
            declared = _rule_based_extract(last_user_msg, user_profile)
            if "is_nri" in declared:
                user_profile["is_nri"] = declared["is_nri"]
        except Exception as e:
            logger.warning("LLM extraction failed, using deterministic fallback: %s", e)
            user_profile = _rule_based_extract(last_user_msg, user_profile)
    else:
        user_profile = _rule_based_extract("", user_profile)

    user_profile = _normalize_profile(user_profile)

    # 2. Determine missing required fields
    missing_fields = [f for f in REQUIRED_HEALTH_FIELDS if user_profile.get(f) is None]

    updates: dict[str, Any] = {
        "user_profile": user_profile,
        "missing_fields": missing_fields,
    }

    # 3. If profile is complete, run the deterministic calculators
    if not missing_fields:
        logger.info("Intake complete for session %s. Running calculators.", session_id)
        has_ped = bool(user_profile.get("pre_existing_conditions"))
        calc_out = calculate_health_cover_sizing(
            age=int(user_profile.get("age", 30)),
            city_tier=str(user_profile.get("city_tier", "tier_1")),
            dependents_count=int(user_profile.get("dependents", 0)),
            has_pre_existing_conditions=has_ped,
            existing_coverage=int(user_profile.get("existing_coverage", 0)),
        )
        current_calcs = dict(state.get("calculator_outputs", {}))
        current_calcs["health_cover_sizing"] = calc_out
        updates["calculator_outputs"] = current_calcs
    else:
        # Formulate clarification question for the next missing field
        next_missing = missing_fields[0]
        prompts = {
            "age": "Could you please share your age?",
            "city_tier": "Which city do you live in? (Hospital costs vary significantly by city).",
            "dependents": "How many family members would you like to include in the cover?",
            "pre_existing_conditions": (
                "Do you or any covered family members have any pre-existing health conditions "
                "(e.g., diabetes, blood pressure)?"
            ),
        }
        question = prompts.get(
            next_missing, "Could you provide more details about your insurance requirements?"
        )
        updates["messages"] = messages + [{"role": "assistant", "content": question}]

    return updates
