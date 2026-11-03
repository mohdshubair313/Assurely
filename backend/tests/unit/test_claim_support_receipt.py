"""Telemetry verification cannot pass on missing, duplicate or mismatched evidence."""

from copy import deepcopy

import pytest

from eval.claim_support_calibration import load_dataset
from eval.claim_support_receipt import verify_evidence


def evidence():
    items = load_dataset()["items"]
    receipt = {
        "dataset_items": items,
        "experiment_id": "experiment",
        "actual": {i["id"]: i["expectedOutput"] for i in items},
        "traces": {i["id"]: "trace-" + i["id"] for i in items},
    }
    remote = {
        "data": [
            {
                "experimentItemId": "claim-support-candidate-v1-" + i["id"],
                "experimentId": "experiment",
                "traceId": "trace-" + i["id"],
                "input": i["input"],
                "output": i["expectedOutput"],
                "expectedOutput": i["expectedOutput"],
                "scores": [
                    {
                        "name": "claim-support-judge-output-correct",
                        "dataType": "BOOLEAN",
                        "value": True,
                    }
                ],
            }
            for i in items
        ]
    }
    return deepcopy(receipt), deepcopy(remote)


def test_complete_evidence_passes_without_production_approval():
    receipt, remote = evidence()
    result = verify_evidence(receipt, remote)
    assert result["verified"] and result["remote_cases"] == 12
    assert not result["production_approved"]


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "duplicate",
        "trace",
        "label",
        "score",
        "output",
        "input",
        "malformed",
        "score_missing",
    ],
)
def test_each_evidence_gap_fails(change):
    receipt, remote = evidence()
    row = remote["data"][0]
    if change == "missing":
        remote["data"].pop()
    elif change == "duplicate":
        remote["data"].append(row)
    elif change == "trace":
        row["traceId"] = "different"
    elif change == "label":
        row["expectedOutput"] = {"verdicts": []}
    elif change == "score":
        row["scores"][0]["value"] = False
    elif change == "output":
        row["output"] = None
    elif change == "input":
        row["input"] = []
    elif change == "score_missing":
        row["scores"] = []
    else:
        row["input"] = "not json"
    assert not verify_evidence(receipt, remote)["verified"]
