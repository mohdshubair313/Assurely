"""Host CLI for isolated claim-support experiments; credentials stay in memory.

Run from backend: python -m eval.claim_support_live provision|run --receipt PATH
The application container supplies only existing Langfuse/OpenRouter credentials.
No dotenv, policy database, advisor destination or graph state is touched.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from eval.claim_support_calibration import load_dataset, review_manifest
from eval.claim_support_experiment import MODEL, NAME, PROVIDER
from eval.claim_support_receipt import verify_evidence
from eval.provider_diagnostics import safe_quota

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = """
import json,os,sys
data=json.load(sys.stdin)
os.environ.update(data['runtime'])
sys.path.insert(0,'/app')
from eval.claim_support_experiment import run
run(data['options'])
"""


def runtime_credentials() -> tuple[dict[str, str], str]:
    inspected = subprocess.run(
        ["docker", "inspect", "insurance-api"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    info = json.loads(inspected.stdout)[0]
    values = dict(v.split("=", 1) for v in info["Config"]["Env"] if "=" in v)
    allowed = {"LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "OPENROUTER_API_KEY"}
    runtime = {k: values[k] for k in allowed if values.get(k)}
    runtime["LANGFUSE_BASE_URL"] = values.get("LANGFUSE_BASE_URL") or values.get(
        "LANGFUSE_HOST", ""
    )
    if len(runtime) != 4 or not runtime["LANGFUSE_BASE_URL"]:
        raise ValueError("Required runtime credentials unavailable")
    return runtime, info["Image"]


def quota_preflight(runtime: dict[str, str], required: int) -> dict[str, Any]:
    """A read-only check prevents starting a cohort with known insufficient quota."""
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/key",
        headers={"Authorization": "Bearer " + runtime["OPENROUTER_API_KEY"]},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.load(response)
            quota = safe_quota(data.get("data"))
        remaining = quota.get("remaining")
        return {
            "status": "checked",
            "required_requests": required,
            "quota": quota,
            "allowed": remaining is None or remaining >= required,
            "quota_known": remaining is not None,
        }
    except Exception as exc:
        return {"status": "unavailable", "allowed": False, "error_type": type(exc).__name__}


def cli(
    runtime: dict[str, str], resource: str, action: str, *arguments: str, body: Any = None
) -> Any:
    env = os.environ.copy()
    env.update({k: v for k, v in runtime.items() if k.startswith("LANGFUSE_")})
    cmd = [
        "npx.cmd" if os.name == "nt" else "npx",
        "--yes",
        "langfuse-cli",
        "api",
        resource,
        action,
        *arguments,
        "--json",
    ]
    if body is not None:
        cmd += ["--body-file", "-"]
    proc = subprocess.run(
        cmd,
        input=json.dumps(body) if body is not None else None,
        env=env,
        cwd=tempfile.gettempdir(),
        capture_output=True,
        text=True,
        timeout=90,
    )
    try:
        response = json.loads(proc.stdout)
    except ValueError:
        raise RuntimeError(f"CLI {resource}/{action} failed without JSON") from None
    if proc.returncode or response.get("status", 500) >= 300:
        raise RuntimeError(f"CLI {resource}/{action} HTTP {response.get('status')}")
    return response["body"]


def provision(runtime: dict[str, str], path: Path) -> None:
    """Create a candidate dataset/prompt and inactive categorical judge scaffold."""
    if path.exists():
        raise FileExistsError("Preserve existing provisioning receipt")
    dataset = load_dataset()
    manifest = review_manifest(dataset)
    # Avoid updating an existing named resource or creating a duplicate judge.
    existing = cli(runtime, "datasets", "list")
    if any(d["name"] == NAME for d in existing["data"]):
        raise ValueError("Candidate dataset already exists; inspect before resuming")
    result: dict[str, Any] = {"status": "provisioning", "manifest": manifest}

    def save() -> None:
        path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    with path.open("x", encoding="utf-8") as handle:
        json.dump(result, handle)
    remote = cli(
        runtime,
        "datasets",
        "create",
        body={
            "name": NAME,
            "description": "Synthetic AI-reviewed candidate labels; exploratory calibration only.",
            "metadata": {
                "labels_human_validated": False,
                "production_approved": False,
                "dataset_sha256": manifest["dataset_sha256"],
                "review": dataset["review"],
            },
        },
    )
    result["dataset_id"] = remote["id"]
    save()
    for item in dataset["items"]:
        cli(
            runtime,
            "dataset-items",
            "create",
            body={
                "datasetName": NAME,
                "id": "claim-support-candidate-v1-" + item["id"],
                "input": item["input"],
                "expectedOutput": item["expectedOutput"],
                "metadata": {
                    **item["metadata"],
                    "case_id": item["id"],
                    "labels_human_validated": False,
                },
            },
        )
        print(json.dumps({"uploaded": item["id"]}), flush=True)
    prompt = cli(
        runtime,
        "prompts",
        "create",
        body={
            "name": NAME,
            "type": "text",
            "prompt": manifest["prompt"]["text"],
            "labels": ["candidate"],
            "config": {
                "model": MODEL,
                "temperature": 0,
                "max_tokens": 2048,
                "production_approved": False,
            },
            "tags": ["synthetic", "ai-reviewed"],
        },
    )
    result["prompt_version"] = prompt["version"]
    save()
    # Flat cloud score is a scaffold only: it cannot reproduce a batch verdict array.
    # SDK calibration below uses the exact runtime prompt/output instead.
    try:
        evaluator = cli(
            runtime,
            "evaluators",
            "create",
            body={
                "name": "claim-support-candidate",
                "type": "llm_as_judge",
                "description": (
                    "Inactive categorical scaffold. SDK verdict-array calibration "
                    "does not validate this wrapper."
                ),
                "prompt": [
                    {"role": "system", "content": manifest["prompt"]["text"]},
                    {"role": "user", "content": "{{input}}"},
                ],
                "variableMapping": [{"variable": "input", "source": "input"}],
                "modelConfig": {"provider": PROVIDER, "model": MODEL},
                "outputDefinition": {
                    "dataType": "CATEGORICAL",
                    "categories": ["supported", "unsupported", "uncertain"],
                    "shouldAllowMultipleMatches": False,
                },
            },
        )
        result["evaluator_id"] = evaluator["id"]
        save()
        rule = cli(
            runtime,
            "evaluation-rules",
            "create",
            body={
                "name": "claim-support-candidate-inactive",
                "enabled": False,
                "evaluatorAssignments": [{"evaluatorId": evaluator["id"]}],
                "filter": [
                    {
                        "type": "stringOptions",
                        "column": "name",
                        "operator": "any of",
                        "value": ["claim-support-candidate"],
                    }
                ],
                "sampling": 1,
            },
        )
        result["rule_id"] = rule["id"]
        result["rule_enabled"] = rule["enabled"]
    except RuntimeError as exc:
        result["inactive_evaluator_setup_error"] = str(exc)
    result["status"] = "prepared"
    save()
    print(json.dumps({k: v for k, v in result.items() if k != "manifest"}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["provision", "run", "verify"])
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--run-name")
    parser.add_argument("--dataset", type=Path)
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=10,
        choices=range(0, 61),
        metavar="0..60",
        help="Experiment pacing outside the inference deadline",
    )
    args = parser.parse_args()
    runtime, image = runtime_credentials()
    if args.action == "provision":
        provision(runtime, args.receipt)
        return
    if args.action == "verify":
        if not args.output or args.output.exists():
            parser.error("verify requires a new --output evidence file")
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
        local = load_dataset(args.dataset) if args.dataset else load_dataset()
        if receipt["manifest"]["dataset_sha256"] != review_manifest(local)["dataset_sha256"]:
            raise ValueError("Local dataset changed since this experiment")
        receipt["dataset_items"] = local["items"]
        since = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        remote = cli(
            runtime,
            "experiment-items",
            "list",
            "--from-start-time",
            since,
            "--experiment-id",
            receipt["experiment_id"],
            "--fields",
            "core,dataset,io,scores",
            "--limit",
            "100",
        )
        verification = verify_evidence(receipt, remote)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump({"verification": verification, "remote": remote}, handle, indent=2)
        print(json.dumps(verification))
        if not verification["verified"]:
            raise RuntimeError("Cloud readback differs from local result")
        return
    if not args.output or not args.run_name:
        parser.error("run requires --output and --run-name")
    output = args.output.resolve()
    if output.parent != (ROOT / "artifacts").resolve() or output.exists():
        raise ValueError("Use a new output file directly in artifacts")
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    local = load_dataset(args.dataset) if args.dataset else load_dataset()
    dataset_option = {}
    if args.dataset:
        relative = args.dataset.resolve().relative_to((ROOT / "backend").resolve())
        dataset_option["dataset_path"] = "/app/" + relative.as_posix()
    preflight = quota_preflight(runtime, len(local["items"]))
    print(json.dumps({"preflight": preflight}), flush=True)
    if not preflight["allowed"]:
        with output.open("x", encoding="utf-8") as handle:
            json.dump(
                {
                    "status": "preflight_blocked",
                    "preflight": preflight,
                    "live_calls": 0,
                    "production_approved": False,
                },
                handle,
                indent=2,
            )
        raise RuntimeError("Provider preflight did not permit the cohort")
    command = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--read-only",
        "--tmpfs",
        "/tmp",
        "--workdir",
        "/tmp",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        "--mount",
        f"type=bind,source={ROOT / 'backend'},target=/app,readonly",
        "--mount",
        f"type=bind,source={ROOT / 'artifacts'},target=/evidence",
        image,
        "python",
        "-u",
        "-c",
        BOOTSTRAP,
    ]
    # stdin, not command arguments or a credential file; no DB credentials forwarded.
    result = subprocess.run(
        command,
        input=json.dumps(
            {
                "runtime": runtime,
                "options": {
                    **dataset_option,
                    "output": "/evidence/" + output.name,
                    "run_name": args.run_name,
                    "prompt_version": receipt["prompt_version"],
                    "model": receipt.get("model", MODEL),
                    "interval_seconds": args.interval_seconds,
                    "preflight": preflight,
                    "prompt_sha256": receipt.get(
                        "prompt_sha256", review_manifest(load_dataset())["prompt"]["sha256"]
                    ),
                },
            }
        ),
        text=True,
    )
    if result.returncode:
        raise RuntimeError("Isolated experiment exited unsuccessfully")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Claim-support runner: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
