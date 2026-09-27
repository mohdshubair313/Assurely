"""Graph assembly — nodes + conditional edges, wired per LLD § 7.3.

Builds the compiled LangGraph ``StateGraph`` that implements the pipeline:
  1. input_validate → rate-limit check
  2. needs_intake → multi-turn profiling with deterministic calculators
  3. intent_router → sets intent ("health" | "life" | "unclear")
  4. Parallel fan-out: health_domain_agent + risk_analysis (Stage 2)
  5. compare_verify → fan-in / join (Stage 3, deterministic DB lookups)
  6. guardrail → sets approved / escalation (Stage 4)
  7. explanation_report → escalate → persist_memory → END
  8. Early-return paths also pass through persist_memory once per turn.

Every routing decision is a plain conditional edge over explicit state fields
(AGENTS.md rule 2). No node asks an LLM "what should happen next."
"""

from __future__ import annotations

import logging
from typing import Any, Literal, cast

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.core.tracing import trace_node
from app.graph.nodes.compare_verify import compare_verify_node
from app.graph.nodes.escalate import escalate_node
from app.graph.nodes.explanation_report import explanation_report_node
from app.graph.nodes.guardrail import guardrail_node
from app.graph.nodes.health_domain_agent import health_domain_agent_node
from app.graph.nodes.intent_router import intent_router_node
from app.graph.nodes.needs_intake import needs_intake_node
from app.graph.nodes.persist_memory import persist_memory_node
from app.graph.nodes.risk_analysis import risk_analysis_node
from app.graph.state import SessionState

logger = logging.getLogger(__name__)


def route_after_intake(state: SessionState) -> Literal["continue_intake", "route_intent"]:
    """Deterministic routing after needs_intake based on missing_fields.

    AGENTS.md rule 2: routing between nodes is deterministic code,
    never an LLM decision.
    """
    missing = state.get("missing_fields", [])
    if missing:
        # Still missing profile information; turn completes to wait for user input
        return "continue_intake"
    # Profile complete; advance to intent classification
    return "route_intent"


def route_after_intent(
    state: SessionState,
) -> list[str] | Literal["life_deferred", "unclear_intent"]:
    """Deterministic routing after intent_router based on explicit state['intent'].

    AGENTS.md rule 2: conditional edges over explicit state fields.
    When intent == 'health', fans out concurrently to both health_domain_agent
    and risk_analysis (Stage 2 parallel fan-out).
    """
    intent = state.get("intent")
    if intent == "health":
        return ["health_domain_agent", "risk_analysis"]
    elif intent == "life":
        return "life_deferred"
    return "unclear_intent"


def build_graph(
    checkpointer: MemorySaver | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Build and compile the LangGraph workflow.

    Wires Stage 1 (needs_intake, intent_router), Stage 2 parallel fan-out
    (health_domain_agent, risk_analysis), and Stage 3 fan-in (compare_verify)
    with deterministic conditional edges.

    Stage 5 report runs unconditionally before escalation gates delivery.
    Persist memory runs at the end of every completed turn.
    """
    builder: StateGraph[Any, Any, Any, Any] = StateGraph(cast(Any, SessionState))

    # 1. Register nodes
    builder.add_node("needs_intake", trace_node("needs-intake", needs_intake_node))
    builder.add_node("intent_router", trace_node("intent-router", intent_router_node))
    builder.add_node(
        "health_domain_agent", trace_node("health-domain-agent", health_domain_agent_node)
    )
    builder.add_node("risk_analysis", trace_node("risk-analysis", risk_analysis_node))
    builder.add_node(
        "compare_verify", trace_node("compare-verify", compare_verify_node)
    )  # Stage 3 fan-in
    builder.add_node("guardrail", trace_node("guardrail", guardrail_node))  # Stage 4 check
    builder.add_node(
        "explanation_report", trace_node("explanation-report", explanation_report_node)
    )
    builder.add_node("escalate", trace_node("escalate", escalate_node))
    builder.add_node("persist_memory", trace_node("persist-memory", persist_memory_node))

    # 2. Wire entry point
    builder.add_edge(START, "needs_intake")

    # 3. Deterministic conditional edge after needs_intake
    builder.add_conditional_edges(
        "needs_intake",
        route_after_intake,
        {
            "continue_intake": "persist_memory",  # Persist before returning the question
            "route_intent": "intent_router",  # Profile complete -> classify intent
        },
    )

    # 4. Deterministic conditional edge after intent_router (Stage 2 parallel fan-out)
    builder.add_conditional_edges(
        "intent_router",
        route_after_intent,
        {
            "health_domain_agent": "health_domain_agent",
            "risk_analysis": "risk_analysis",
            "life_deferred": "persist_memory",  # Persist before returning scope message
            "unclear_intent": "persist_memory",  # Persist before returning clarification
        },
    )

    # 5. Stage 2 → Stage 3 fan-in: both branches join at compare_verify
    builder.add_edge("health_domain_agent", "compare_verify")
    builder.add_edge("risk_analysis", "compare_verify")

    # 6. Stage 3 -> Stage 4 guardrail (compliance & disclosure check)
    builder.add_edge("compare_verify", "guardrail")

    # Report generation always runs; escalation is only a delivery gate.
    builder.add_edge("guardrail", "explanation_report")
    builder.add_edge("explanation_report", "escalate")
    builder.add_edge("escalate", "persist_memory")
    builder.add_edge("persist_memory", END)

    memory = checkpointer or MemorySaver()
    return builder.compile(checkpointer=memory)
