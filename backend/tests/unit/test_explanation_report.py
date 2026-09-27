"""Safety and provenance tests for the Stage 5 report node."""

from unittest.mock import AsyncMock, patch

import pytest

from app.graph.nodes.explanation_report import (
    explanation_report_node,
)
from app.graph.state import SessionState
from app.llm.providers import LLMResult


def _state(*, escalation: bool = False) -> SessionState:
    return SessionState(
        session_id="explanation-report-test",
        draft_output={
            "cited_facts": [
                {
                    "claim": "The policy has a waiting period for pre-existing conditions.",
                    "source": "Policy wording, section 4",
                    "last_verified": "2026-09-20",
                    "url": "https://example.test/policy",
                }
            ],
            "need_fit_view": [
                {
                    "insurer": "Example Insurer",
                    "product_name": "Health Plan",
                    "sum_insured_range_inr": {
                        "min": 500000,
                        "max": 2500000,
                        "source": "policy_terms",
                        "last_verified": "2026-09-20",
                    },
                }
            ],
        },
        guardrail_notes=["STATUS: Approved for explanation generation."],
        retrieved_facts=[],
        target_language="en",
        escalation=escalation,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("escalation", [False, True])
async def test_report_generates_and_cites_each_sentence_even_when_escalated(
    escalation: bool,
) -> None:
    response = LLMResult(
        content='{"sentences":[{"text":"The policy includes a waiting period.",'
        '"evidence_ids":["E1"]}]}',
        provider="mock",
        model="mock-model",
    )
    with patch(
        "app.graph.nodes.explanation_report.llm_call",
        new=AsyncMock(return_value=response),
    ) as llm:
        result = await explanation_report_node(_state(escalation=escalation))

    assert result["output"]["reply"].startswith("The policy includes a waiting period.")
    assert "Source: Policy wording, section 4" in result["output"]["reply"]
    assert "last verified: 2026-09-20" in result["output"]["reply"]
    citation = result["output"]["sentences"][0]["citations"][0]
    assert citation["source"] == "Policy wording, section 4"
    assert citation["last_verified"] == "2026-09-20"
    assert llm.await_count == 1
    assert llm.await_args.kwargs["task_type"] == "explanation_report"
    assert "Target language: en" in llm.await_args.kwargs["messages"][0]["content"]


@pytest.mark.asyncio
async def test_report_does_not_emit_unverified_evidence() -> None:
    state = _state()
    state["draft_output"]["need_fit_view"] = []
    state["draft_output"]["cited_facts"][0]["last_verified"] = ""
    with patch("app.graph.nodes.explanation_report.llm_call") as llm:
        result = await explanation_report_node(state)

    llm.assert_not_awaited()
    assert result["output"]["sentences"] == []
    assert result["output"]["report_status"] == "insufficient_verified_evidence"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        '{"sentences":[{"text":"Unsupported claim.","evidence_ids":[]}]}',
        '{"sentences":[{"text":"Unsupported claim.","evidence_ids":["E99"]}]}',
        '{"sentences":[{"text":"The best plan guarantees approval.","evidence_ids":["E1"]}]}',
    ],
)
async def test_report_rejects_unsupported_or_noncompliant_sentences(content: str) -> None:
    response = LLMResult(content=content, provider="mock", model="mock-model")
    with patch(
        "app.graph.nodes.explanation_report.llm_call",
        new=AsyncMock(return_value=response),
    ):
        result = await explanation_report_node(_state())
    assert result == {"output": {}}
