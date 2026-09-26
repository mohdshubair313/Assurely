"""Actual local HTTP queue/hold proof, using only synthetic data.

The SQLite-backed loopback receiver below is TEST INFRASTRUCTURE, not the Phase 2
advisor destination. It deliberately acknowledges after committing an event and
deduplicates stable IDs. No external advisor is contacted.
Run from backend: python -m eval.escalation_preflight
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Lock, Thread
from unittest.mock import patch

from app.api.v1.message import build_message_response
from app.core.config import Settings
from app.graph.nodes.escalate import escalate_node
from app.graph.state import create_initial_state


@contextmanager
def local_receiver(database: Path):
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE queue (event_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
    requests = []
    lock = Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            event = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.headers.get("Idempotency-Key") != event["event_id"]:
                self.send_error(400)
                return
            with lock:
                requests.append(event)
                first = len(requests) == 1
                with sqlite3.connect(database) as conn:
                    conn.execute("INSERT OR IGNORE INTO queue VALUES (?, ?)",
                                 (event["event_id"], json.dumps(event)))
            # Simulate an uncertain outcome AFTER commit; retry must not duplicate.
            body = json.dumps({"queued": True, "event_id": event["event_id"]}).encode()
            self.send_response(503 if first else 202)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/advisor-test-queue", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


async def run_preflight():
    state = create_initial_state("synthetic-escalation-preflight")
    state.update(approved=True, escalation=True, missing_fields=[],
                 escalation_reason="Synthetic advisor review",
                 output={"reply": "SYNTHETIC_HELD_REPORT", "source": "test fixture"},
                 draft_output={"claim": "SYNTHETIC_HELD_DRAFT"},
                 calculator_outputs={"value": "SYNTHETIC_HELD_CALCULATION"},
                 retrieved_facts=[{"claim": "SYNTHETIC_HELD_CITATION"}])
    original = deepcopy(state)
    with TemporaryDirectory() as temp:
        database = Path(temp) / "local-test-queue.sqlite3"
        with local_receiver(database) as (url, requests):
            settings = Settings(_env_file=None, environment="development",
                                advisor_webhook_url=url,
                                advisor_webhook_retry_delay_seconds=0)
            with patch("app.graph.nodes.escalate.get_settings", return_value=settings):
                result = await escalate_node(state)
                assert result["advisor_notification"]["status"] == "queued"
                assert result["advisor_notification"]["attempts"] == 2
                assert result["delivery_hold"] is True and "output" not in result
                assert state == original
                # Replay without a client receipt, including concurrent invocations.
                replay = await asyncio.gather(escalate_node(state), escalate_node(state))
                assert all(item["delivery_hold"] for item in replay)
                before_receipt_replay = len(requests)
                await escalate_node({**state, **result})
                assert len(requests) == before_receipt_replay
            response = build_message_response(state["session_id"], {**state, **result})
            assert response.delivery_hold and response.output == {}
            assert response.calculator_outputs == {} and response.draft_output == {}
            assert response.citations == []
            assert "SYNTHETIC_HELD" not in response.model_dump_json()
            with sqlite3.connect(database) as conn:
                queued = conn.execute("SELECT COUNT(*) FROM queue").fetchone()[0]
            assert queued == 1
            report = {
                "executed_at": datetime.now(timezone.utc).isoformat(),
                "receiver": "LOCAL TEST PLACEHOLDER ONLY; no external advisor destination",
                "transport": "real HTTP over loopback, SQLite commit before acknowledgement",
                "http_requests": len(requests), "unique_queued_events": queued,
                "notification": result["advisor_notification"],
                "graph_output_unchanged": state == original,
                "delivery_hold_after_queue_ack": result["delivery_hold"],
                "public_response": response.model_dump(),
                "phase_2_task": "Configure and validate the actual advisor-queue destination",
            }
    return report


async def main():
    report = await run_preflight()
    target = Path(__file__).resolve().parents[2] / "artifacts" / "escalate-preflight.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
