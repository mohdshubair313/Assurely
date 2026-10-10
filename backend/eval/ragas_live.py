"""Run RAGAS metrics against live pipeline traces for the existing eval cases.

Usage inside a configured backend environment::

    python -m eval.ragas_live --output ../artifacts/ragas-live.json

This imports the real API route and compiled graph, calls configured providers,
and uses the live Postgres/Chroma/Redis services. It does not mock the pipeline.
Only aggregate scores, trace identifiers, and content-free counts are written.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import types
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.api.v1.message import MessageRequest, _app_graph, send_message
from app.core.config import get_settings
from app.core.correlation import correlation_scope
from app.graph.nodes.explanation_report import _evidence_catalog
from app.main import app

logger = logging.getLogger("ragas_live")
EVAL_DIR = Path(__file__).parent
CASE_DIR = EVAL_DIR / "cases"
REFERENCES_PATH = EVAL_DIR / "ragas_references.json"
METRIC_NAMES = (
    "context_precision",
    "context_recall",
    "faithfulness",
    "answer_relevancy",
)
FREE_FAITHFULNESS_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"

# These additions are deterministic synthetic intake answers. They let cases
# whose objective is retrieval reach the existing retrieval nodes without
# altering the original case message. Missing-info and ambiguous-intent cases
# intentionally remain on their early-return paths.
INTAKE_FOLLOWUP = {
    "age": "I am 40 years old.",
    "city_tier": "I live in Bengaluru.",
    "dependents": "This is for me only; I have no dependents.",
    "pre_existing_conditions": "I have no pre-existing health conditions.",
}
EARLY_RETURN_CASES = {"case_03_missing_info_loop", "case_07_ambiguous_intent"}
SPECIAL_MESSAGES = {
    "case_04_conflicting_sources": (
        "I am 40 years old, live in Bengaluru, and need cover for myself only with no "
          "pre-existing conditions. I am asking about health insurance. For HDFC ERGO "
          "Optima Secure, an aggregator says the "
        "pre-existing disease waiting period is 24 months, while the insurer wording says "
        "36 months. What does the policy wording say?"
    ),
    "case_05_outdated_policy": (
        "I am 40 years old, live in Bengaluru, and need cover for myself only with no "
        "pre-existing conditions. Is Health Companion 2021 still active? Its stated expiry "
        "date was 2023-12-31, and I am asking on 2026-09-21."
    ),
}


class PipelineReportUnavailableError(RuntimeError):
    """A report case failed generation; a delivery-status reply is not its answer."""

    def __init__(self, case_id: str, report_status: str | None) -> None:
        super().__init__(f"Generated report unavailable for {case_id}")
        self.details: dict[str, Any] = {
            "case_id": case_id,
            "report_status": report_status,
            "reason": "generated_report_unavailable",
        }


def evaluation_answer(case_id: str, output: Any, api_reply: str) -> str:
    """Score generated reports even when held, and clarification replies by design."""
    if case_id in EARLY_RETURN_CASES:
        return api_reply
    report = output if isinstance(output, dict) else {}
    status = report.get("report_status")
    answer = report.get("reply")
    if status != "ready" or not isinstance(answer, str) or not answer.strip():
        raise PipelineReportUnavailableError(
            case_id,
            status if status in {"ready", "insufficient_verified_evidence"} else None,
        )
    return answer


def install_ragas_langchain_compatibility() -> None:
    """Bridge RAGAS 0.4's removed LangChain Vertex AI import names.

    RAGAS 0.4.3 imports these names at module load even when its Google GenAI
    integration is used. LangChain moved them out of langchain-community. The
    RAGAS import only uses the classes in its multiple-completion type check;
    this evaluator uses OpenAI-compatible clients, never either class.
    Remove this local shim after RAGAS ships the upstream import fix.
    """
    community_vertex_module = "langchain_community.chat_models.vertexai"
    try:
        __import__(community_vertex_module)
    except ModuleNotFoundError:
        legacy_vertex_type = type("LegacyVertexModel", (), {})
        module = types.ModuleType(community_vertex_module)
        module.ChatVertexAI = legacy_vertex_type  # type: ignore[attr-defined]
        sys.modules[community_vertex_module] = module

    try:
        import langchain_community.llms as community_llms
    except ImportError:
        community_llms = None
    if community_llms is not None and not hasattr(community_llms, "VertexAI"):
        community_llms.VertexAI = type("LegacyVertexAIModel", (), {})  # type: ignore[attr-defined]


def load_cases() -> list[dict[str, Any]]:
    cases = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(CASE_DIR.glob("*.json"))
    ]
    if len(cases) < 8:
        raise RuntimeError(f"Expected at least 8 existing eval cases; found {len(cases)}")
    return cases


def adapted_message(case: dict[str, Any]) -> str:
    case_id = case["id"]
    if case_id in SPECIAL_MESSAGES:
        return SPECIAL_MESSAGES[case_id]
    message = case.get("input", {}).get("user_message")
    if not isinstance(message, str):
        raise ValueError(f"Case {case_id} needs an explicit live-message adapter")
    return message


def generation_contexts(state: Any) -> list[str]:
    """Give the generation judge the same sourced facts available to the report.

    Retrieval metrics still receive clause text only. The report also receives
    deterministic policy_terms facts; omitting them from the faithfulness judge
    would incorrectly penalize valid numeric claims. Source/date metadata is
    included because the generated reply contains that metadata too.
    """
    return list(
        dict.fromkeys(
            f"{fact['claim']} [Source: {fact['source']}; "
            f"last verified: {fact['last_verified']}]"
            for fact in _evidence_catalog(state)
        )
    )


async def run_pipeline_case(case: dict[str, Any]) -> dict[str, Any]:
    case_id = case["id"]
    session_id = f"ragas-{uuid.uuid4()}"
    config = {"configurable": {"thread_id": session_id}}
    pending_message = adapted_message(case)
    final_response: Any = None
    turn_ids: list[dict[str, str]] = []
    followup_count = 0

    while True:
        with correlation_scope(session_id) as turn:
            final_response = await send_message(
                MessageRequest(session_id=session_id, user_message=pending_message),
                authenticated_user_id=None,
            )
            turn_ids.append(
                {
                    "trace_id": turn.trace_id,
                    "decision_trace_id": turn.decision_trace_id,
                }
            )

        checkpoint = await _app_graph.aget_state(config)
        state = checkpoint.values if checkpoint and checkpoint.values else {}
        missing_fields = state.get("missing_fields", [])
        if (
            case_id in EARLY_RETURN_CASES
            or not missing_fields
            or followup_count >= 4
        ):
            break

        followup_fields = [field for field in missing_fields if field in INTAKE_FOLLOWUP]
        if not followup_fields:
            break
        pending_message = " ".join(INTAKE_FOLLOWUP[field] for field in followup_fields)
        followup_count += 1

    state = checkpoint.values if checkpoint and checkpoint.values else {}
    output = state.get("output") or {}
    try:
        answer = evaluation_answer(
            case_id, output, final_response.reply if final_response is not None else ""
        )
    except PipelineReportUnavailableError as exc:
        exc.details.update(
            trace_ids=[turn["trace_id"] for turn in turn_ids],
            decision_trace_ids=[turn["decision_trace_id"] for turn in turn_ids],
            retrieved_fact_count=len(state.get("retrieved_facts") or []),
        )
        raise

    retrieved_facts = state.get("retrieved_facts") or []
    contexts = []
    for fact in retrieved_facts:
        if not isinstance(fact, dict):
            continue
        claim = fact.get("claim")
        if isinstance(claim, str) and claim.strip():
            contexts.append(claim.strip())

    return {
        "case_id": case_id,
        "session_id": session_id,
        "turns": turn_ids,
        "answer": answer,
        "answer_source": (
            "clarification_response" if case_id in EARLY_RETURN_CASES else "generated_report"
        ),
        "contexts": contexts,
        "generation_contexts": generation_contexts(state),
        # Kept transiently for side-by-side inspection; never written to the
        # content-free result artifact.
        "retrieved_chunks": [
            fact for fact in retrieved_facts if isinstance(fact, dict)
        ],
        "retrieved_fact_count": len(contexts),
        "intent": state.get("intent"),
        "missing_field_count": len(state.get("missing_fields") or []),
        "report_status": (output.get("report_status") if isinstance(output, dict) else None),
        "delivery_hold": bool(state.get("delivery_hold", True)),
        "approved": bool(state.get("approved", False)),
    }


async def create_metrics(
    judge_provider: str = "groq", faithfulness_provider: str = "openrouter"
) -> dict[str, Any]:
    openrouter_model = os.getenv("RAGAS_OPENROUTER_MODEL", FREE_FAITHFULNESS_MODEL)
    if "openrouter" in {judge_provider, faithfulness_provider} and not openrouter_model.endswith(
        ":free"
    ):
        raise ValueError("Free-tier evaluation requires a pinned OpenRouter :free model")
    install_ragas_langchain_compatibility()
    try:
        from openai import AsyncOpenAI
        from ragas.embeddings.base import embedding_factory
        from ragas.llms import llm_factory
        from ragas.metrics.collections import (
            AnswerRelevancy,
            ContextPrecision,
            ContextRecall,
            Faithfulness,
        )
    except ImportError as exc:
        raise RuntimeError(
            'Install the optional evaluation dependencies with `pip install -e ".[eval]`'
        ) from exc

    settings = get_settings()
    if not settings.groq_api_key or not settings.gemini_api_key:
        raise RuntimeError("GROQ_API_KEY and GEMINI_API_KEY are required for RAGAS evaluation")
    if faithfulness_provider not in {"groq", "gemini", "openrouter"}:
        raise ValueError("Unsupported faithfulness provider")
    if "openrouter" in {judge_provider, faithfulness_provider} and not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required for the selected evaluator")

    import httpx

    def paced_client(min_interval_seconds: float) -> httpx.AsyncClient:
        lock = asyncio.Lock()
        last_request = 0.0

        async def pace_request(_request: httpx.Request) -> None:
            nonlocal last_request
            async with lock:
                now = asyncio.get_running_loop().time()
                delay = min_interval_seconds - (now - last_request)
                if delay > 0:
                    await asyncio.sleep(delay)
                last_request = asyncio.get_running_loop().time()

        return httpx.AsyncClient(
            event_hooks={"request": [pace_request]},
            timeout=httpx.Timeout(120.0),
        )

    groq_client = AsyncOpenAI(
        api_key=settings.groq_api_key,
        base_url="https://api.groq.com/openai/v1",
        timeout=45.0,
        max_retries=0,
        http_client=paced_client(60 if judge_provider == "groq" else 15),
    )
    gemini_client = AsyncOpenAI(
        api_key=settings.gemini_api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        timeout=90.0,
        max_retries=0,
        http_client=paced_client(
            60 if faithfulness_provider == "gemini" or judge_provider == "gemini" else 15
        ),
    )
    openrouter_client = (
        AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
            timeout=120.0,
            max_retries=0,
            http_client=paced_client(
                60
                if faithfulness_provider == "openrouter" or judge_provider == "openrouter"
                else 15
            ),
        )
        if settings.openrouter_api_key
        else None
    )
    groq_llm = llm_factory(
        settings.groq_model,
        provider="openai",
        client=groq_client,
        system_prompt="You are an independent evaluator. Judge only the supplied sample data.",
        max_tokens=2048,
    )
    gemini_llm = llm_factory(
        settings.gemini_model,
        provider="openai",
        client=gemini_client,
        system_prompt="You are an independent evaluator. Judge only the supplied sample data.",
        max_tokens=1024,
    )
    # Pin the fallback route to the model verified against RAGAS structured
    # output. Avoid openrouter/free here because it can change models per call.
    openrouter_llm = (
        llm_factory(
            openrouter_model,
            provider="openai",
            client=openrouter_client,
            system_prompt="You are an independent evaluator. Judge only the supplied sample data.",
            max_tokens=4096,
        )
        if openrouter_client is not None
        else None
    )
    primary_llm = {
        "groq": groq_llm,
        "gemini": gemini_llm,
        "openrouter": openrouter_llm,
    }[judge_provider]
    faithfulness_llm = {
        "groq": groq_llm,
        "gemini": gemini_llm,
        "openrouter": openrouter_llm,
    }[faithfulness_provider]
    embeddings = embedding_factory(
        "openai",
        model="gemini-embedding-2-preview",
        client=gemini_client,
    )
    return {
        "context_precision": ContextPrecision(llm=primary_llm),
        "context_recall": ContextRecall(llm=primary_llm),
        # Faithfulness has a higher completion count (statement extraction and
        # per-statement support checks), so keep it off the constrained Groq and
        # Gemini free tiers. OpenRouter fallback is pinned to one model.
        "faithfulness": Faithfulness(llm=faithfulness_llm),
        "answer_relevancy": AnswerRelevancy(
            llm=primary_llm,
            embeddings=embeddings,
        ),
        "evaluator_model": {
            "groq": settings.groq_model,
            "gemini": settings.gemini_model,
            "openrouter": openrouter_model,
        }[judge_provider],
        "faithfulness_model": {
            "groq": settings.groq_model,
            "gemini": settings.gemini_model,
            "openrouter": openrouter_model,
        }[faithfulness_provider],
        "faithfulness_provider": faithfulness_provider,
        "embedding_model": "gemini-embedding-2-preview",
        "faithfulness_context": "complete_sourced_explanation_evidence",
        "evaluator_provider": judge_provider,
    }


async def score_case(
    sample: dict[str, Any],
    reference: str | None,
    metrics: dict[str, Any],
    selected_metrics: set[str] | None = None,
    metric_delay_seconds: float = 0,
) -> dict[str, Any]:
    if not sample["answer"].strip():
        return {name: {"status": "not_scored", "reason": "empty_response"} for name in METRIC_NAMES}
    scores: dict[str, Any] = {}
    generation_evidence = sample.get("generation_contexts", sample["contexts"])
    for name in METRIC_NAMES:
        if selected_metrics is not None and name not in selected_metrics:
            scores[name] = {"status": "not_requested"}
            continue
        if (
            name in {"context_precision", "context_recall"}
            and not sample["contexts"]
        ):
            scores[name] = {"status": "not_applicable", "reason": "no_context_retrieved"}
            continue
        if name == "faithfulness" and not generation_evidence:
            scores[name] = {"status": "not_applicable", "reason": "no_generation_evidence"}
            continue
        if name in {"context_precision", "context_recall"} and not reference:
            scores[name] = {"status": "not_applicable", "reason": "no_case_retrieval_reference"}
            continue
        try:
            if metric_delay_seconds:
                await asyncio.sleep(metric_delay_seconds)
            backoff = (90, 180, 300, 300) if name == "faithfulness" else (75, 150, 240)
            for attempt in range(len(backoff) + 1):
                try:
                    if name in {"context_precision", "context_recall"}:
                        result = await metrics[name].ascore(
                            user_input=sample["user_input"],
                            reference=reference,
                            retrieved_contexts=sample["contexts"],
                        )
                    elif name == "faithfulness":
                        result = await metrics[name].ascore(
                            user_input=sample["user_input"],
                            response=sample["answer"],
                            retrieved_contexts=generation_evidence,
                        )
                    else:
                        result = await metrics[name].ascore(
                            user_input=sample["user_input"],
                            response=sample["answer"],
                        )
                    break
                except Exception as exc:
                    if type(exc).__name__ != "RateLimitError" or attempt >= len(backoff):
                        raise
                    logger.warning(
                        "RAGAS provider rate limit for %s/%s; retrying after %s seconds",
                        sample["case_id"],
                        name,
                        backoff[attempt],
                    )
                    await asyncio.sleep(backoff[attempt])
            value = result.value
            scores[name] = {
                "status": "scored",
                "value": round(float(value), 4) if value is not None else None,
            }
        except Exception as exc:
            logger.warning(
                "RAGAS metric failed for %s/%s (%s)",
                sample["case_id"],
                name,
                type(exc).__name__,
            )
            response = getattr(exc, "response", None)
            headers = getattr(response, "headers", {}) or {}
            scores[name] = {
                "status": "provider_error",
                "error_class": type(exc).__name__,
                "status_code": getattr(exc, "status_code", None),
                "retry_after_header": headers.get("retry-after"),
            }
    return scores


async def verify_trace_persistence(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify generated trace IDs exist in Postgres and, where configured, Langfuse."""
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.db.decision_trace import DecisionTrace

    decision_ids = {
        uuid.UUID(trace_id)
        for result in results
        for trace_id in result["decision_trace_ids"]
    }
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(DecisionTrace.id).where(DecisionTrace.id.in_(decision_ids))
        )
        persisted_decision_ids = {row[0] for row in rows.all()}

    settings = get_settings()
    langfuse_statuses: dict[str, int] = {}
    langfuse_configured = bool(settings.langfuse_public_key and settings.langfuse_secret_key)
    if langfuse_configured:
        import httpx

        trace_ids = {trace_id for result in results for trace_id in result["trace_ids"]}
        async with httpx.AsyncClient(
            base_url=settings.langfuse_host.rstrip("/"),
            auth=(settings.langfuse_public_key, settings.langfuse_secret_key),
            timeout=15.0,
        ) as client:
            for trace_id in trace_ids:
                try:
                    response = await client.get(
                        "/api/public/v2/observations",
                        params={
                            "traceId": trace_id,
                            "fromStartTime": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
                            "toStartTime": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
                            "fields": "core",
                        },
                    )
                    has_observation = response.status_code == 200 and any(
                        item.get("traceId") == trace_id
                        for item in response.json().get("data", [])
                    )
                    status = (
                        "found"
                        if has_observation
                        else "not_found"
                        if response.status_code == 200
                        else f"http_{response.status_code}"
                    )
                    langfuse_statuses[status] = langfuse_statuses.get(status, 0) + 1
                except httpx.HTTPError:
                    langfuse_statuses["request_error"] = (
                        langfuse_statuses.get("request_error", 0) + 1
                    )

    return {
        "decision_trace_rows_expected": len(decision_ids),
        "decision_trace_rows_found": len(persisted_decision_ids),
        "decision_trace_rows_all_present": persisted_decision_ids == decision_ids,
        "langfuse_configured": langfuse_configured,
        "langfuse_trace_status_counts": langfuse_statuses,
    }


async def run(
    output_path: Path,
    case_ids: set[str] | None = None,
    selected_metrics: set[str] | None = None,
    judge_provider: str = "groq",
    faithfulness_provider: str = "openrouter",
    metric_delay_seconds: float = 0,
    between_cases_delay_seconds: float = 180,
) -> int:
    references = json.loads(REFERENCES_PATH.read_text(encoding="utf-8"))
    cases = load_cases()
    if case_ids:
        cases = [case for case in cases if case["id"] in case_ids]
        missing = case_ids - {case["id"] for case in cases}
        if missing:
            raise ValueError(f"Unknown eval case IDs: {sorted(missing)}")
    metric_bundle = await create_metrics(judge_provider, faithfulness_provider)
    results: list[dict[str, Any]] = []

    async with app.router.lifespan_context(app):
        for case_index, case in enumerate(cases):
            if case_index and between_cases_delay_seconds > 0:
                logger.info(
                    "Cooling down for %.0f seconds before the next case",
                    between_cases_delay_seconds,
                )
                await asyncio.sleep(between_cases_delay_seconds)
            sample = await run_pipeline_case(case)
            sample["user_input"] = adapted_message(case)
            reference = references.get(case["id"], {}).get("retrieval_reference")
            scores = await score_case(
                sample,
                reference,
                metric_bundle,
                selected_metrics=selected_metrics,
                metric_delay_seconds=metric_delay_seconds,
            )
            results.append(
                {
                    "case_id": sample["case_id"],
                    "category": case.get("category"),
                    "trace_ids": [turn["trace_id"] for turn in sample["turns"]],
                    "decision_trace_ids": [
                        turn["decision_trace_id"] for turn in sample["turns"]
                    ],
                    "turn_count": len(sample["turns"]),
                    "retrieved_fact_count": sample["retrieved_fact_count"],
                    "generation_evidence_count": len(sample["generation_contexts"]),
                    "intent": sample["intent"],
                    "missing_field_count": sample["missing_field_count"],
                    "report_status": sample["report_status"],
                    "answer_source": sample["answer_source"],
                    "delivery_hold": sample["delivery_hold"],
                    "approved": sample["approved"],
                    "scores": scores,
                }
            )
            logger.info(
                "Scored %s: retrieved=%d report_status=%s",
                sample["case_id"],
                sample["retrieved_fact_count"],
                sample["report_status"],
            )

    persistence = await verify_trace_persistence(results)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "timestamp": datetime.now(UTC).isoformat(),
        "runner": "RAGAS collections API",
        "evaluator_model": metric_bundle["evaluator_model"],
        "faithfulness_model": metric_bundle["faithfulness_model"],
        "faithfulness_provider": metric_bundle["faithfulness_provider"],
        "evaluator_provider": metric_bundle["evaluator_provider"],
        "between_cases_delay_seconds": between_cases_delay_seconds,
        "metric_providers": {
            "context_precision": judge_provider,
            "context_recall": judge_provider,
            "answer_relevancy": judge_provider,
            "faithfulness": faithfulness_provider,
        },
        "embedding_model": metric_bundle["embedding_model"],
        "faithfulness_context": metric_bundle["faithfulness_context"],
        "live_pipeline": True,
        "mocked_pipeline_components": [],
        "case_count": len(results),
        "trace_persistence": persistence,
        "scores": results,
        "notes": [
            (
                "RAGAS judge inputs are omitted; the artifact retains scores, IDs, and counts."
            ),
            (
                "Seeded corpus/reference text is a project test fixture, not independently "
                "verified insurance wording."
            ),
            (
                "Retrieval N/A means no clauses or no case reference; faithfulness N/A "
                "means no sourced generation evidence. Neither is a zero score."
            ),
            (
                "Faithfulness uses the report's complete sourced evidence, including "
                "deterministic policy_terms facts. Retrieval metrics use RAG clauses only."
            ),
        ],
    }
    output_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    all_scores_resolved = all(
        entry["scores"][name]["status"]
        in {"scored", "not_applicable", "not_requested"}
        for entry in results
        for name in METRIC_NAMES
    )
    langfuse_ids_expected = sum(len(result["trace_ids"]) for result in results)
    langfuse_ok = not persistence["langfuse_configured"] or (
        persistence["langfuse_trace_status_counts"].get("found", 0)
        == langfuse_ids_expected
    )
    return (
        0
        if all_scores_resolved
        and persistence["decision_trace_rows_all_present"]
        and langfuse_ok
        else 2
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("../artifacts/ragas-live.json"),
        help="Content-free JSON artifact destination",
    )
    parser.add_argument("--case-id", action="append", help="Run only this case; repeatable")
    parser.add_argument(
        "--only-metric",
        action="append",
        choices=METRIC_NAMES,
        help="Score only this metric; repeatable",
    )
    parser.add_argument(
        "--judge-provider",
        choices=("groq", "gemini", "openrouter"),
        default="groq",
        help="Judge provider for other metrics; faithfulness uses the pinned OpenRouter model",
    )
    parser.add_argument(
        "--faithfulness-provider",
        choices=("groq", "gemini", "openrouter"),
        default="openrouter",
        help="Judge provider for faithfulness, whose scoring makes several model calls",
    )
    parser.add_argument(
        "--metric-delay-seconds",
        type=float,
        default=0,
        help="Minimum pause before each metric call for rate-limit headroom",
    )
    parser.add_argument(
        "--between-cases-delay-seconds",
        type=float,
        default=180,
        help="Cooldown between cases to respect organization-wide quotas",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    return asyncio.run(
        run(
            args.output,
            case_ids=set(args.case_id) if args.case_id else None,
            selected_metrics=set(args.only_metric) if args.only_metric else None,
            judge_provider=args.judge_provider,
            faithfulness_provider=args.faithfulness_provider,
            metric_delay_seconds=args.metric_delay_seconds,
            between_cases_delay_seconds=args.between_cases_delay_seconds,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())

