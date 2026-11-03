"""Verify remote experiment evidence before claiming successful telemetry delivery."""

from __future__ import annotations

import json
from typing import Any

from eval.claim_support_experiment import exact_match, same_json


def _decoded(value: Any) -> Any:
    if value == "" or value is None:
        return None
    return json.loads(value) if isinstance(value, str) else value


def verify_evidence(receipt: dict[str, Any], remote: dict[str, Any]) -> dict[str, Any]:
    """Require every trace, output, expected label and Boolean score to match."""
    expected = {i["id"]: i for i in receipt["dataset_items"]}
    seen: set[str] = set()
    issues = []
    for row in remote.get("data", []):
        case_id = str(row.get("experimentItemId", "")).removeprefix("claim-support-candidate-v1-")
        if case_id not in expected or case_id in seen:
            issues.append("unknown_or_duplicate_case")
            continue
        seen.add(case_id)
        item = expected[case_id]
        try:
            input_ok = same_json(_decoded(row.get("input")), item["input"])
            output_ok = same_json(_decoded(row.get("output")), receipt["actual"].get(case_id))
            expected_ok = same_json(_decoded(row.get("expectedOutput")), item["expectedOutput"])
        except (ValueError, TypeError):
            input_ok = output_ok = expected_ok = False
        desired_score = exact_match(receipt["actual"].get(case_id), item["expectedOutput"])
        scores = [
            s
            for s in row.get("scores", [])
            if s.get("name") == "claim-support-judge-output-correct"
        ]
        score_ok = (
            len(scores) == 1
            and scores[0].get("dataType") == "BOOLEAN"
            and type(scores[0].get("value")) is bool
            and scores[0]["value"] is desired_score
        )
        if not (
            input_ok
            and output_ok
            and expected_ok
            and score_ok
            and row.get("experimentId") == receipt["experiment_id"]
            and row.get("traceId") == receipt["traces"].get(case_id)
            and bool(row.get("traceId"))
        ):
            issues.append(case_id + ":evidence_mismatch")
    if seen != set(expected):
        issues.append("missing_cases")
    return {
        "verified": not issues,
        "expected_cases": len(expected),
        "remote_cases": len(seen),
        "issues": issues,
        "labels_human_validated": False,
        "production_approved": False,
    }
