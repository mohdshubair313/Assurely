"""Windows host runner: isolated Docker eval, runtime credentials, no dotenv access."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = """
import asyncio,json,os,sys
data=json.load(sys.stdin)
os.environ.update(data['runtime'])
os.environ['OPENROUTER_MODELS']='nvidia/nemotron-3-super-120b-a12b:free'
os.environ['LOG_LEVEL']='warning'
os.environ['PYTHONDONTWRITEBYTECODE']='1'
from app.core import config
config.Settings.model_config['env_file']=None
config.get_settings=lambda:config.Settings(_env_file=None)
try:
 from eval.rubric_live import execute
 result=asyncio.run(execute(data['options']))
except Exception as exc:
 print(json.dumps({'status':'bootstrap_failed','error_class':type(exc).__name__}),flush=True)
 result=2
raise SystemExit(result)
"""


async def preflight() -> bool:
    """Only read-only connectivity checks; never generate text or seed data."""
    import chromadb
    import httpx
    from redis.asyncio import Redis
    from sqlalchemy import select, text

    from app.core.config import get_settings
    from app.db.session import async_engine
    from app.models.db.decision_trace import DecisionTrace
    from eval.rubric_scorer import JUDGE_MODEL

    settings = get_settings()
    missing = [
        name
        for name in (
            "groq_api_key",
            "gemini_api_key",
            "openrouter_api_key",
            "langfuse_public_key",
            "langfuse_secret_key",
        )
        if not getattr(settings, name)
    ]
    checks = {"credentials_present": not missing}
    errors = {}
    redis = Redis.from_url(settings.redis_url)
    try:
        async with async_engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            await connection.execute(
                select(
                    DecisionTrace.id,
                    DecisionTrace.model_version,
                    DecisionTrace.prompt_version,
                    DecisionTrace.policy_versions_evaluated_json,
                ).limit(0)
            )
        from chromadb.config import Settings as ChromaSettings

        checks["postgres"] = True
        checks["redis"] = bool(await redis.ping())
        client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        checks["chroma_has_clauses"] = client.get_collection("policy_clauses").count() > 0
        async with httpx.AsyncClient(timeout=30) as http:
            response = await http.get(
                f"https://openrouter.ai/api/v1/models/{JUDGE_MODEL}/endpoints"
            )
            response.raise_for_status()
            endpoints = response.json()["data"]["endpoints"]
        checks["free_judge_endpoint"] = any(
            float(e["pricing"]["prompt"]) == 0
            and float(e["pricing"]["completion"]) == 0
            and {"reasoning", "response_format", "structured_outputs"}.issubset(
                e.get("supported_parameters", [])
            )
            for e in endpoints
        )
    except Exception as exc:
        errors["connectivity_error_class"] = type(exc).__name__
    finally:
        await redis.aclose()
        await async_engine.dispose()
    passed = not errors and len(checks) == 5 and all(checks.values())
    print(
        json.dumps(
            {
                "status": "preflight_passed" if passed else "preflight_failed",
                "checks": checks,
                "missing_credential_names": missing,
                **errors,
                "dotenv_accessed": False,
                "llm_calls": 0,
            }
        ),
        flush=True,
    )
    return passed


async def postgres_versions(entries: list[dict[str, Any]]) -> dict[str, Any]:
    import uuid as uuid_module

    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.db.decision_trace import DecisionTrace

    ids = {uuid_module.UUID(i) for entry in entries for i in entry["decision_trace_ids"]}
    async with AsyncSessionLocal() as database:
        result = await database.execute(
            select(
                DecisionTrace.id,
                DecisionTrace.model_version,
                DecisionTrace.prompt_version,
                DecisionTrace.policy_versions_evaluated_json,
            ).where(DecisionTrace.id.in_(ids))
        )
        rows = result.all()
    return {
        "expected": len(ids),
        "found": len(rows),
        "all_present": len(rows) == len(ids),
        "versions": [
            {
                "decision_trace_id": str(row.id),
                "model_version": row.model_version,
                "prompt_version": row.prompt_version,
                "policy_versions_evaluated": row.policy_versions_evaluated_json,
            }
            for row in rows
        ],
    }


async def execute(options: dict[str, Any]) -> int:
    isolation = None
    if options.get("case05_isolated_database"):
        from eval.case05_fixture import prepare_isolated_database, verify_isolated_database

        if options.get("prepare_case05_only"):
            isolation = await prepare_isolated_database(options["case05_isolated_database"])
            print(json.dumps({"status": "isolated_fixture_prepared", **isolation}), flush=True)
            return 0
        isolation = await verify_isolated_database(options["case05_isolated_database"])
    if not await preflight():
        return 2
    if options["preflight"]:
        return 0
    from typing import cast

    from app.core.config import get_settings
    from app.graph.nodes.explanation_report import _evidence_catalog
    from app.graph.state import SessionState
    from eval import ragas_live as pipeline
    from eval.rubric_scorer import (
        JUDGE_MODEL,
        PROMPT_VERSION,
        RUBRIC_VERSION,
        RubricJudgeError,
        build_packet,
        control_scores,
        judge_packet,
        summarize,
    )

    references = json.loads(pipeline.REFERENCES_PATH.read_text())
    cases = pipeline.load_cases()
    if options["cases"]:
        selected = set(options["cases"])
        if selected - {case["id"] for case in cases}:
            raise ValueError("Unknown case ID")
        cases = [case for case in cases if case["id"] in selected]
    priority = {
        "case_04_conflicting_sources": 0,
        "case_01_normal_health": 1,
        "case_08_provenance_diabetes_comparison": 2,
    }
    cases.sort(key=lambda case: (priority.get(case["id"], 3), case["id"]))
    output = Path("/artifacts") / options["output_name"]
    artifact: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "run_status": "in_progress",
        "rubric_version": RUBRIC_VERSION,
        "prompt_version": PROMPT_VERSION,
        "judge_model": JUDGE_MODEL,
        "selected_case_ids": [c["id"] for c in cases],
        "live_pipeline": True,
        "mocked_pipeline_components": [],
        "dotenv_accessed": False,
        "confidence_blind": True,
        "labels_human_validated": False,
        "pipeline_source_sha256": options.get("pipeline_source_sha256"),
        "reference_sha256": hashlib.sha256(pipeline.REFERENCES_PATH.read_bytes()).hexdigest(),
        "isolated_evaluation_fixture": isolation,
        "cases": [],
        "review_candidates": [],
        "pacing_seconds": {"between_cases": 180, "after_pipeline": 60},
    }

    def save() -> None:
        output.write_text(json.dumps(artifact, indent=2, allow_nan=False), encoding="utf-8")

    save()
    try:
        async with pipeline.app.router.lifespan_context(pipeline.app):
            for index, case in enumerate(cases):
                print(json.dumps({"status": "running_case", "case_id": case["id"]}), flush=True)
                sample = await pipeline.run_pipeline_case(case)
                entry = {
                    "case_id": case["id"],
                    "status": "pipeline_complete_pending_judge",
                    "answer_source": sample["answer_source"],
                    "retrieved_fact_count": sample["retrieved_fact_count"],
                    "delivery_hold": sample["delivery_hold"],
                    "trace_ids": [t["trace_id"] for t in sample["turns"]],
                    "decision_trace_ids": [t["decision_trace_id"] for t in sample["turns"]],
                    "judged_trace_id": sample["turns"][-1]["trace_id"],
                    "judged_decision_trace_id": sample["turns"][-1]["decision_trace_id"],
                }
                artifact["cases"].append(entry)
                save()
                checkpoint = await pipeline._app_graph.aget_state(
                    {"configurable": {"thread_id": sample["session_id"]}}
                )
                state = cast(SessionState, checkpoint.values)
                evidence = _evidence_catalog(state)
                packet = build_packet(
                    case,
                    sample,
                    state,
                    evidence,
                    references.get(case["id"], {}).get("retrieval_reference"),
                )
                controls = control_scores(sample, state, evidence)
                entry["packet_sha256"] = hashlib.sha256(
                    json.dumps(packet, sort_keys=True).encode()
                ).hexdigest()
                entry["judge_input_counts"] = {
                    field: len(packet[field])
                    for field in ("retrieved_clauses", "generation_evidence", "sentences")
                }
                await asyncio.sleep(60)
                scores, usage = await judge_packet(packet, get_settings().openrouter_api_key)
                summary = summarize(scores, controls)
                entry.update(
                    status="scored",
                    scores=scores,
                    controls=controls,
                    **summary,
                    judge_usage=usage,
                    not_applicable_criteria=packet["not_applicable_criteria"],
                )
                if entry["review_candidate"]:
                    artifact["review_candidates"].append(
                        {
                            "case_id": case["id"],
                            "trace_ids": entry["trace_ids"],
                            "failed_criteria": entry["failed_criteria"],
                            "status": "awaiting_validated_feedback_review",
                        }
                    )
                save()
                print(
                    json.dumps(
                        {
                            "status": "case_scored",
                            "case_id": case["id"],
                            **summary,
                            "judge_usage": usage,
                        }
                    ),
                    flush=True,
                )
                if index < len(cases) - 1:
                    print("Cooldown: 180 seconds before the next case.", flush=True)
                    await asyncio.sleep(180)
            artifact["postgres_verification"] = await postgres_versions(artifact["cases"])
        artifact["run_status"] = "scores_complete_pending_langfuse_verification"
    except Exception as exc:
        artifact["run_status"] = "failed"
        artifact["failure"] = {"error_class": type(exc).__name__}
        if isinstance(exc, (RubricJudgeError, pipeline.PipelineReportUnavailableError)):
            artifact["failure"].update(exc.details)
        if isinstance(exc, pipeline.PipelineReportUnavailableError):
            artifact["cases"].append(
                {
                    "case_id": exc.details["case_id"],
                    "status": "pipeline_failed",
                    "trace_ids": exc.details.get("trace_ids", []),
                    "decision_trace_ids": exc.details.get("decision_trace_ids", []),
                }
            )
        try:
            artifact["postgres_verification"] = await postgres_versions(artifact["cases"])
        except Exception as verification_error:
            artifact["postgres_verification"] = {
                "all_present": False,
                "error_class": type(verification_error).__name__,
            }
        save()
        print(json.dumps({"status": "run_failed", **artifact["failure"]}), flush=True)
        return 2
    save()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preflight", action="store_true", help="Connectivity only; zero LLM calls"
    )
    parser.add_argument("--case", action="append", dest="cases", default=[])
    parser.add_argument(
        "--case05-isolated-database",
        help="Initialize a newly provisioned, empty CASE05-only evaluation database",
    )
    parser.add_argument(
        "--prepare-case05-only", action="store_true",
        help="Explicitly initialize the empty isolated DB, then exit without model calls",
    )
    parser.add_argument("--output-name", default=f"rubric-live-{datetime.now(UTC).date()}.json")
    args = parser.parse_args()
    if args.prepare_case05_only and (not args.case05_isolated_database or args.preflight):
        raise ValueError("Fixture preparation requires isolated DB and cannot use --preflight")
    if Path(args.output_name).name != args.output_name or not args.output_name.endswith(".json"):
        raise ValueError("Output must be a JSON filename inside artifacts")
    output = ROOT / "artifacts" / args.output_name
    if not args.preflight and output.exists():
        raise ValueError("Output exists; keep it for review instead of rerunning blindly")
    inspected = subprocess.run(
        ["docker", "inspect", "insurance-api"], capture_output=True, text=True
    )
    if inspected.returncode:
        raise ValueError("Docker/backend unavailable; start the existing stack first")
    info = json.loads(inspected.stdout)[0]
    if not info["State"]["Running"]:
        raise ValueError("insurance-api is not running")
    try:
        node = subprocess.run(["npx.cmd", "--version"], capture_output=True, timeout=15)
        if node.returncode:
            raise ValueError
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Node.js/npx unavailable; install Node.js LTS before running") from exc
    runtime = dict(item.split("=", 1) for item in info["Config"]["Env"] if "=" in item)
    if args.case05_isolated_database:
        from eval.case05_fixture import isolated_database_url

        runtime["DATABASE_URL"] = isolated_database_url(
            runtime.get("DATABASE_URL", ""), args.case05_isolated_database, args.cases
        )
    networks = info["NetworkSettings"]["Networks"]
    if len(networks) != 1:
        raise ValueError("Expected one backend Docker network; review configuration")
    ROOT.joinpath("artifacts").mkdir(exist_ok=True)
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        f"insurance-rubric-{uuid.uuid4().hex[:8]}",
        "--network",
        next(iter(networks)),
        "--workdir",
        "/tmp",
        "-i",
    ]
    for source, target, readonly in (
        (ROOT / "backend/app", "/app/app", True),
        (ROOT / "backend/eval", "/app/eval", True),
        (ROOT / "artifacts", "/artifacts", False),
    ):
        command += [
            "--mount",
            f"type=bind,source={source},target={target}" + (",readonly" if readonly else ""),
        ]
    command += [info["Image"], "python", "-u", "-c", BOOTSTRAP]
    source_digest = hashlib.sha256()
    for directory in (ROOT / "backend/app", ROOT / "backend/eval"):
        for file in sorted(directory.rglob("*.py")):
            source_digest.update(str(file.relative_to(ROOT)).encode())
            source_digest.update(file.read_bytes())
    options = {**vars(args), "pipeline_source_sha256": source_digest.hexdigest()}
    completed = subprocess.run(
        command, input=json.dumps({"runtime": runtime, "options": options}), text=True
    )
    if args.preflight or args.prepare_case05_only or not output.exists():
        return completed.returncode
    artifact = json.loads(output.read_text(encoding="utf-8"))
    trace_ids = {i for entry in artifact["cases"] for i in entry["trace_ids"]}
    cli_env = os.environ.copy()
    cli_env.update({k: v for k, v in runtime.items() if k.startswith("LANGFUSE_")})
    cli_env["LANGFUSE_BASE_URL"] = (
        runtime.get("LANGFUSE_HOST")
        or runtime.get("LANGFUSE_BASE_URL")
        or "https://cloud.langfuse.com"
    )
    counts: dict[str, int] = {}
    from eval.free_runtime_live import observation_status

    for trace_id in sorted(trace_ids):
        try:
            cli = subprocess.run(
                [
                    "npx.cmd",
                    "--yes",
                    "langfuse-cli",
                    "api",
                    "observations",
                    "list",
                    "--trace-id",
                    trace_id,
                    "--fields",
                    "core",
                    "--limit",
                    "1",
                    "--json",
                ],
                env=cli_env,
                cwd=tempfile.gettempdir(),
                capture_output=True,
                text=True,
                timeout=60,
            )
            status = (
                observation_status(json.loads(cli.stdout), trace_id)
                if not cli.returncode
                else "cli_error"
            )
        except Exception as exc:
            status = "cli_" + type(exc).__name__
        counts[status] = counts.get(status, 0) + 1
    artifact["langfuse_verification"] = {
        "expected": len(trace_ids),
        "statuses": counts,
        "method": "CLI observations --fields core",
    }
    if artifact["run_status"] != "failed":
        verified = (
            artifact.get("postgres_verification", {}).get("all_present")
            and counts.get("found", 0) == len(trace_ids)
            and bool(trace_ids)
        )
        artifact["run_status"] = "complete" if verified else "verification_incomplete"
    output.write_text(json.dumps(artifact, indent=2, allow_nan=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": artifact["run_status"],
                "result_file": str(output),
                "scored_cases": sum(c["status"] == "scored" for c in artifact["cases"]),
            }
        )
    )
    return 0 if artifact["run_status"] == "complete" else 2


if __name__ == "__main__":
    # The host CLI needs only the standard library, including when invoked by path.
    sys.path.insert(0, str(ROOT / "backend"))
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Runner stopped: {error}")
        raise SystemExit(2) from None
