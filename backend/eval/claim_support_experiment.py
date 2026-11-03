"""Isolated SDK experiment for the pinned semantic verifier, never app routing."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
import os
import time
from pathlib import Path
from typing import Any

from app.graph.support_verdict import parse_verdict
from eval.claim_support_calibration import (
    DEFAULT_DATASET,
    load_dataset,
    model_payload,
    review_manifest,
    summarize,
)
from eval.provider_diagnostics import (
    failure_category,
    reliability_summary,
    retry_after_seconds,
    safe_usage,
    verdict_format,
)

MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
PROVIDER = "insuranceai-claim-support-openrouter"
NAME = "judge-calibration/claim-support"


def same_json(left: Any, right: Any) -> bool:
    """Compare JSON types as well as values (False is not sentence ID zero)."""
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(
        right, sort_keys=True, allow_nan=False
    )


def exact_match(actual: Any, expected: Any) -> bool:
    """JSON structural equality with strict ID types, not Python bool/int coercion."""
    try:
        ids = {v["sentence_id"] for v in expected["verdicts"]}
        return bool(parse_verdict(json.dumps(actual), "stop", ids) == expected)
    except (KeyError, TypeError, ValueError):
        return False


def verify_remote_items(local: dict[str, Any], items: list[Any]) -> None:
    """Do not silently experiment on changed cloud labels, inputs or provenance."""
    expected = {i["id"]: i for i in local["items"]}
    seen = set()
    for item in items:
        meta = item.metadata or {}
        case_id = meta.get("case_id")
        if case_id not in expected or case_id in seen:
            raise ValueError("Unexpected or duplicate remote case")
        seen.add(case_id)
        source = expected[case_id]
        if (
            not same_json(item.input, source["input"])
            or not same_json(item.expected_output, source["expectedOutput"])
            or any(meta.get(k) != v for k, v in source["metadata"].items())
            or meta.get("labels_human_validated") is not False
        ):
            raise ValueError("Remote dataset differs from reviewed local snapshot")
    if seen != set(expected):
        raise ValueError("Remote dataset is incomplete")


def case_id_for(item: Any) -> str:
    """Support SDK object and dictionary representations without guessing IDs."""
    metadata = item.get("metadata") if isinstance(item, dict) else item.metadata
    if not isinstance(metadata, dict):
        raise ValueError("Missing case metadata")
    case_id = metadata["case_id"]
    if not isinstance(case_id, str):
        raise ValueError("Missing case identity")
    return case_id


async def infer(payload: str, prompt: str, model: str = MODEL) -> tuple[Any, dict[str, Any]]:
    """One pinned request; bounded like runtime; no retries or model fallback."""
    import httpx

    started = time.monotonic()
    info: dict[str, Any] = {"requested_model": model}
    body = {
        "model": model,
        "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": payload}],
        "temperature": 0,
        "max_tokens": 2048,
    }

    async def request() -> Any:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]},
                json=body,
            )
            info["http_status"] = response.status_code
            delay = retry_after_seconds(getattr(response, "headers", {}).get("retry-after"))
            if delay is not None:
                info["retry_after_seconds"] = delay
            if response.status_code >= 400:
                info["failure_category"] = failure_category(response.status_code)
            response.raise_for_status()
            return response.json()

    try:
        data = await asyncio.wait_for(request(), timeout=30)
        if not isinstance(data, dict):
            raise ValueError("Invalid provider envelope")
        if "error" in data:
            error = data["error"]
            code = error.get("code") if isinstance(error, dict) else None
            info["failure_category"] = "provider_error"
            if type(code) is int and 400 <= code <= 599:
                info["provider_error_status"] = code
                info["failure_category"] = failure_category(code)
            raise ValueError("Provider reported an error")
        choice = data["choices"][0]
        reason = choice.get("finish_reason")
        info.update(
            model_matches=data.get("model") == model,
            finish_reason=reason
            if reason in ("stop", "length", "tool_calls", "content_filter")
            else "unknown",
            usage=safe_usage(data.get("usage")),
        )
        if reason != "stop":
            info["failure_category"] = "completion_limit" if reason == "length" else "incomplete"
        info["verdict_format"] = verdict_format(choice["message"].get("content"))
        output = parse_verdict(
            choice["message"]["content"],
            choice["finish_reason"],
            {v["sentence_id"] for v in json.loads(payload)},
        )
        info["status"] = "parsed"
    except Exception as exc:
        # Provider errors can contain credentials/content. Retain only safe categories.
        output = None
        info.update(status="failed", error_type=type(exc).__name__)
        info.setdefault(
            "failure_category",
            "timeout"
            if isinstance(exc, (TimeoutError, httpx.TimeoutException))
            else "invalid_or_unavailable_response",
        )
    info["latency_seconds"] = round(time.monotonic() - started, 3)
    return output, info


def run(options: dict[str, Any]) -> None:
    """Fetch pinned cloud inputs, execute all cases and save a non-overwriting receipt."""
    from langfuse import Langfuse
    from langfuse.experiment import Evaluation

    output_path = Path(options["output"])
    # Reserve before any inference; do not overwrite previous experiments.
    with output_path.open("x", encoding="utf-8") as handle:
        json.dump({"status": "started", "run_name": options["run_name"]}, handle)
    journal = output_path.with_suffix(".items.jsonl")
    journal.touch(exist_ok=False)
    local = load_dataset(Path(options.get("dataset_path", DEFAULT_DATASET)))
    model = options.get("model", MODEL)
    manifest = review_manifest(local)
    lf = Langfuse(environment="claim-support-calibration", timeout=30)
    details: dict[str, Any] = {}
    try:
        dataset = lf.get_dataset(NAME)
        cohort = local.get("cohort", "baseline-v1")
        dataset.items = [
            i for i in dataset.items if (i.metadata or {}).get("cohort", "baseline-v1") == cohort
        ]
        verify_remote_items(local, dataset.items)
        prompt = lf.get_prompt(NAME, version=options["prompt_version"], type="text")
        digest = hashlib.sha256(prompt.prompt.encode()).hexdigest()
        expected_digest = options.get("prompt_sha256", manifest["prompt"]["sha256"])
        if digest != expected_digest:
            raise ValueError("Remote prompt differs from pinned candidate snapshot")
        if prompt.config.get("model") != model:
            raise ValueError("Remote prompt model differs from pinned experiment model")
        if prompt.config.get("temperature") != 0 or prompt.config.get("max_tokens") != 2048:
            raise ValueError("Remote prompt parameters differ from runtime contract")

        async def task(*, item: Any, **kwargs: Any) -> Any:
            # Pacing is outside the runtime-equivalent 30-second inference deadline.
            await asyncio.sleep(options.get("interval_seconds", 6))
            case_id = item.metadata["case_id"]
            payload = model_payload({"input": item.input})
            with lf.start_as_current_observation(
                name="claim-support-candidate",
                as_type="generation",
                input=payload,
                model=model,
                prompt=prompt,
                model_parameters={"temperature": 0, "max_tokens": 2048},
                metadata={"case_id": case_id, "labels_human_validated": False},
            ) as span:
                output, details[case_id] = await infer(payload, prompt.prompt, model)
                span.update(output=output, metadata=details[case_id])
            # Preserve completed cases even if the process or SDK subsequently fails.
            with journal.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps({"case_id": case_id, "output": output, "call": details[case_id]})
                    + "\n"
                )
            print(
                json.dumps({"case_id": case_id, "status": details[case_id]["status"]}), flush=True
            )
            return output

        def evaluator(*, output: Any, expected_output: Any, **kwargs: Any) -> Any:
            return Evaluation(
                name="claim-support-judge-output-correct",
                value=exact_match(output, expected_output),
                data_type="BOOLEAN",
                comment="Agreement with AI-reviewed synthetic candidate; not human ground truth.",
            )

        result = dataset.run_experiment(
            name="Claim support exploratory calibration",
            run_name=options["run_name"],
            task=task,
            evaluators=[evaluator],
            max_concurrency=1,
            metadata={
                "dataset_sha256": manifest["dataset_sha256"],
                "prompt_sha256": digest,
                "labels_human_validated": False,
                "production_approved": False,
            },
        )
        actual = {case_id_for(r.item): r.output for r in result.item_results}
        receipt: dict[str, Any] = {
            "status": "complete",
            "run_name": result.run_name,
            "experiment_id": result.experiment_id,
            "dataset_run_id": result.dataset_run_id,
            "url": result.dataset_run_url,
            "model": model,
            "sdk_version": importlib.metadata.version("langfuse"),
            "dataset_items": local["items"],
            "dataset_path": str(options.get("dataset_path", DEFAULT_DATASET)),
            "cohort": cohort,
            "prompt_version": prompt.version,
            "tested_prompt": {"text": prompt.prompt, "sha256": digest},
            "manifest": manifest,
            "summary": summarize(local, actual),
            "actual": actual,
            "calls": details,
            "reliability": reliability_summary(details, len(local["items"])),
            "interval_seconds": options.get("interval_seconds", 6),
            "preflight": options.get("preflight"),
            "traces": {case_id_for(r.item): r.trace_id for r in result.item_results},
            "scores": {
                case_id_for(r.item): [e.value for e in r.evaluations] for r in result.item_results
            },
        }
        receipt["manifest"]["live_calls"] = len(details)
        output_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(json.dumps({"summary": receipt["summary"], "url": receipt["url"]}), flush=True)
    except Exception as exc:
        output_path.write_text(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "calls": details,
                    "production_approved": False,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        raise RuntimeError("Experiment failed; see sanitized receipt") from None
    finally:
        lf.flush()
