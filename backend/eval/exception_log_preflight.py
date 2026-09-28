"""Explicit local fault-injection harness, never imported by the application.

Runs a temporary loopback Uvicorn process with one failing report-provider call.
All routing, policy reads, decision persistence and tracing remain real. No
runtime setting or endpoint enables this injection in the normal application.
Use synthetic values only. General logs and full private records stay outside Git.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

FAKE_VALUES = ("SYNTHETIC_PED_MARIGOLD_84621", "SYNTHETIC_PED_CEDAR_39217")


def serve(port: int) -> None:
    import uvicorn

    from app.graph.nodes import explanation_report
    from app.main import app

    async def deliberate_failure(**kwargs: Any) -> None:
        # Both exception message and source line intentionally contain fake data.
        raise RuntimeError("provider echoed " + " ".join(FAKE_VALUES))

    explanation_report.llm_call = deliberate_failure  # type: ignore[assignment]
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info", access_log=False)


async def query_decision(session_id: str) -> dict[str, Any]:
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal, async_engine
    from app.models.db.decision_trace import DecisionTrace

    try:
        async with AsyncSessionLocal() as db:
            row = (await db.execute(select(DecisionTrace).where(
                DecisionTrace.session_id == uuid.UUID(session_id)
            ))).scalar_one()
            profile = json.dumps(row.user_profile_snapshot_json)
            assert all(value in profile for value in FAKE_VALUES), "Synthetic profile not retained"
            return {
                "id": str(row.id), "session_id": str(row.session_id),
                "correlation": row.rules_engine_output_json["correlation"],
                "synthetic_profile_values_present": True,
                "clauses_count": len(row.clauses_retrieved_json),
            }
    finally:
        await async_engine.dispose()


def run(destination: Path) -> None:
    from app.core.config import get_settings
    from app.core.exception_log import admin_read

    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination.chmod(0o700)
    session_id = str(uuid.uuid4())
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    general = destination / "general.log"
    environment = dict(os.environ)
    environment["LOG_LEVEL"] = "info"
    # The normal application's real restricted volume, not an in-memory sink.
    sink_path = Path(get_settings().exception_log_dir)
    with general.open("w", encoding="utf-8") as stream:
        general.chmod(0o600)
        process = subprocess.Popen(
            [sys.executable, "-m", "eval.exception_log_preflight", "--serve", str(port)],
            env=environment, stdout=stream, stderr=subprocess.STDOUT,
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=180) as client:
                for _ in range(120):
                    if process.poll() is not None:
                        raise RuntimeError("Preflight server exited; inspect private local log")
                    try:
                        if client.get("/health").status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    time.sleep(0.25)
                else:
                    raise RuntimeError("Preflight server did not become ready")
                response = client.post("/v1/message", json={
                    "session_id": session_id,
                    "user_message": (
                        "I need health insurance. I am 35 years old, live in Mumbai (Tier 1), "
                        "have 2 dependents, and my pre-existing conditions are "
                        + " and ".join(FAKE_VALUES)
                        + ". Those are the exact declared condition names; retain both."
                    ),
                })
                assert response.status_code == 200, f"Unexpected status {response.status_code}"
                assert response.json()["delivery_hold"] is True
                assert response.json()["output"] == {}
        finally:
            process.terminate()
            try:
                process.wait(timeout=30)  # Graceful lifespan flushes Langfuse.
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    rows = [json.loads(path.read_text()) for path in sink_path.glob("*.json")]
    matching = [
        row for row in rows if row["session_id"] == session_id
        and row["node"] == "explanation-report" and row["exception_class"] == "RuntimeError"
    ]
    assert len(matching) == 1, "Expected one injected report-provider error"
    row = admin_read(str(sink_path), matching[0]["error_ref"])
    general_text = general.read_text()
    assert all(value not in general_text + json.dumps(rows) for value in FAKE_VALUES)
    reference_lines = [line for line in general_text.splitlines() if row["error_ref"] in line]
    assert reference_lines == [f"ERROR error_ref={row['error_ref']}"]
    decision = asyncio.run(query_decision(session_id))
    assert decision["id"] == row["decision_trace_id"]
    assert decision["correlation"]["trace_id"] == row["trace_id"]
    result = {
        "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "request_status": response.status_code, "delivery_hold": True,
        "fault_injection": "temporary loopback API process; report-provider call only",
        "restricted_record": row,
        "general_error_line": reference_lines[0],
        "fake_values_absent_from_both_logs": True,
        "decision_trace": decision,
    }
    (destination / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", type=int)
    parser.add_argument("--destination", type=Path, default=Path("/tmp/exception-preflight"))
    args = parser.parse_args()
    if args.serve:
        serve(args.serve)
    else:
        run(args.destination)
