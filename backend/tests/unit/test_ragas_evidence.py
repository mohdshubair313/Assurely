"""Eval-only checks; live matrix runs continue to use real provider responses."""

from types import SimpleNamespace
from typing import Any

import pytest

from eval.free_runtime_live import observation_status, validate_resume
from eval.ragas_live import (
    PipelineReportUnavailableError,
    create_metrics,
    evaluation_answer,
    generation_contexts,
    score_case,
)


def test_generation_evidence_includes_sourced_policy_terms() -> None:
    state = {
        "retrieved_facts": [
            {
                "claim": "Hospitalization is covered.",
                "source": "Seed clause fixture",
                "last_verified": "2026-10-08",
            }
        ],
        "draft_output": {
            "need_fit_view": [
                {
                    "insurer": "Fixture insurer",
                    "product_name": "Fixture policy",
                    "entry_age_window": {
                        "min": 18,
                        "max": 65,
                        "source": "Seed policy_terms fixture",
                        "last_verified": "2026-10-08",
                    },
                }
            ]
        },
    }
    evidence = generation_contexts(state)
    assert len(evidence) == 2
    assert any("18 to 65 years" in fact for fact in evidence)
    assert any("Seed policy_terms fixture" in fact for fact in evidence)
    assert all("last verified: 2026-10-08" in fact for fact in evidence)
    assert state["retrieved_facts"][0]["claim"] == "Hospitalization is covered."


class RecordingMetric:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def ascore(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(value=1.0)


@pytest.mark.asyncio
async def test_retrieval_and_generation_judges_receive_separate_evidence() -> None:
    metrics = {name: RecordingMetric() for name in (
        "context_precision", "context_recall", "faithfulness"
    )}
    sample = {
        "case_id": "evidence-test",
        "user_input": "Explain coverage and the entry-age window.",
        "answer": "Coverage is available within the sourced entry-age window.",
        "contexts": ["RAG clause text"],
        "generation_contexts": ["RAG clause text", "Sourced policy_terms entry-age window"],
    }
    scores = await score_case(sample, "Reference clause", metrics, set(metrics))
    for name in ("context_precision", "context_recall"):
        assert metrics[name].calls[0]["retrieved_contexts"] == sample["contexts"]
    assert metrics["faithfulness"].calls[0]["retrieved_contexts"] == sample["generation_contexts"]
    assert scores["faithfulness"]["status"] == "scored"


@pytest.mark.asyncio
async def test_deterministic_evidence_can_be_scored_without_rag_clauses() -> None:
    metric = RecordingMetric()
    sample = {
        "case_id": "deterministic-evidence-test",
        "user_input": "What is the entry-age window?",
        "answer": "The sourced entry-age window is 18 to 65 years.",
        "contexts": [],
        "generation_contexts": ["Entry-age window: 18 to 65 years; source: policy_terms"],
    }
    scores = await score_case(sample, None, {"faithfulness": metric}, {"faithfulness"})
    assert len(metric.calls) == 1
    assert scores["faithfulness"]["status"] == "scored"


@pytest.mark.asyncio
async def test_paid_openrouter_model_is_rejected_before_provider_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAGAS_OPENROUTER_MODEL", "provider/paid-model")
    with pytest.raises(ValueError, match=":free"):
        await create_metrics("groq", "openrouter")


def test_langfuse_cli_envelope_is_unwrapped_before_checking_trace_ids() -> None:
    payload = {"status": 200, "headers": {}, "body": {"data": [{"traceId": "trace-test"}]}}
    assert observation_status(payload, "trace-test") == "found"
    assert observation_status(payload, "other-trace") == "not_found"
    assert observation_status({"status": 401, "body": {}}, "trace-test") == "http_401"


@pytest.mark.parametrize("output", [{}, None, {"reply": "", "report_status": "ready"}])
def test_failed_report_never_scores_delivery_hold_reply(output: Any) -> None:
    with pytest.raises(PipelineReportUnavailableError) as caught:
        evaluation_answer(
            "case_08_provenance_diabetes_comparison", output, "Pending advisor review."
        )
    assert caught.value.details["reason"] == "generated_report_unavailable"


def test_held_report_scores_generated_content_instead_of_delivery_status() -> None:
    output = {"reply": "Sourced generated explanation.", "report_status": "ready"}
    assert evaluation_answer(
        "case_08_provenance_diabetes_comparison", output, "Pending advisor review."
    ) == output["reply"]


@pytest.mark.parametrize("case_id", ["case_03_missing_info_loop", "case_07_ambiguous_intent"])
def test_intentional_clarification_paths_score_the_actual_api_reply(case_id: str) -> None:
    assert evaluation_answer(case_id, {}, "Please clarify your needs.") == (
        "Please clarify your needs."
    )


def _completed_checkpoint() -> dict[str, Any]:
    return {
        "evidence_input_version": 3,
        "metric_providers": {
            "context_precision": "groq", "context_recall": "groq",
            "answer_relevancy": "groq", "faithfulness": "openrouter",
        },
        "faithfulness_model": "nvidia/nemotron-3-super-120b-a12b:free",
        "faithfulness_context": "complete_sourced_explanation_evidence",
        "live_pipeline": True,
        "mocked_pipeline_components": [],
        "scores": [{
            "case_id": "case_01_normal_health",
            "answer_source": "generated_report",
            "report_status": "ready",
            "scores": {
                name: {"status": "scored", "value": 0.5}
                for name in (
                    "context_precision", "context_recall", "faithfulness", "answer_relevancy"
                )
            },
        }],
    }


def test_resume_accepts_completed_measurements_with_the_current_evidence_contract() -> None:
    validate_resume(_completed_checkpoint())


def test_resume_rejects_status_reply_measurements() -> None:
    checkpoint = _completed_checkpoint()
    checkpoint["scores"][0].update(answer_source="delivery_status", report_status=None)
    with pytest.raises(ValueError, match="generation target"):
        validate_resume(checkpoint)


@pytest.mark.parametrize("score", [
    {"status": "invalid_measurement", "invalid_observed_value": 0.0},
    {"status": "provider_error", "error_class": "RateLimitError"},
    {"status": "scored", "value": None},
    {"status": "scored", "value": float("nan")},
])
def test_resume_rejects_errors_and_nonfinite_scores(score: dict[str, Any]) -> None:
    checkpoint = _completed_checkpoint()
    checkpoint["scores"][0]["scores"]["faithfulness"] = score
    with pytest.raises(ValueError):
        validate_resume(checkpoint)


def test_resume_rejects_a_changed_provider_assignment() -> None:
    checkpoint = _completed_checkpoint()
    checkpoint["metric_providers"]["faithfulness"] = "gemini"
    with pytest.raises(ValueError, match="provider/evidence contract"):
        validate_resume(checkpoint)


def test_resume_rejects_duplicate_case_ids() -> None:
    checkpoint = _completed_checkpoint()
    checkpoint["scores"].append(checkpoint["scores"][0])
    with pytest.raises(ValueError, match="duplicate"):
        validate_resume(checkpoint)
