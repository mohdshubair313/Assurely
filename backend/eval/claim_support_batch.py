"""Multi-sentence candidate validation and scoring; no model or settings imports."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from app.graph.support_verdict import parse_verdict

COHORT = "multi-sentence-v1"


def flattened(dataset: dict[str, Any]) -> dict[str, Any]:
    """Reuse the single-sentence validator without changing source metadata."""
    result = {"name": dataset["name"], "labels_human_validated": False, "items": []}
    items: list[dict[str, Any]] = []
    for item in dataset["items"]:
        labels = {v["sentence_id"]: v["verdict"] for v in item["expectedOutput"]["verdicts"]}
        for sentence in item["input"]:
            sid = sentence["sentence_id"]
            value = deepcopy(sentence)
            value["sentence_id"] = 0
            items.append(
                {
                    "id": f"{item['id']}:{sid}",
                    "input": [value],
                    "expectedOutput": {"verdicts": [{"sentence_id": 0, "verdict": labels[sid]}]},
                    "metadata": item["metadata"],
                }
            )
    result["items"] = items
    return result


def validate_batch(dataset: dict[str, Any]) -> None:
    from eval.claim_support_calibration import validate_dataset

    if dataset.get("cohort") != COHORT or dataset.get("labels_human_validated") is not False:
        raise ValueError("Unknown batch cohort or falsely human-validated labels")
    items = dataset.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Batch candidates are required")
    seen = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"id", "input", "expectedOutput", "metadata"}:
            raise ValueError("Invalid batch fields")
        ident = item["id"]
        if not isinstance(ident, str) or not ident or ident in seen:
            raise ValueError("Invalid batch identity")
        seen.add(ident)
        inputs = item["input"]
        if not isinstance(inputs, list) or not 2 <= len(inputs) <= 32:
            raise ValueError("Batches must contain 2-32 sentences")
        for sid, sentence in enumerate(inputs):
            if (
                not isinstance(sentence, dict)
                or type(sentence.get("sentence_id")) is not int
                or sentence["sentence_id"] != sid
            ):
                raise ValueError("Batch IDs must match runtime sentence positions")
        parse_verdict(json.dumps(item["expectedOutput"]), "stop", set(range(len(inputs))))
    validate_dataset(flattened(dataset))


def summarize_batch(dataset: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    from eval.claim_support_calibration import summarize

    validate_batch(dataset)
    if set(actual) - {i["id"] for i in dataset["items"]}:
        raise ValueError("Unknown batch result")
    values = {}
    case_correct = invalid = false_release = false_hold = 0
    for item in dataset["items"]:
        output = actual.get(item["id"])
        try:
            parsed = parse_verdict(json.dumps(output), "stop", set(range(len(item["input"]))))
            labels = {v["sentence_id"]: v["verdict"] for v in parsed["verdicts"]}
        except (TypeError, ValueError):
            labels = {}
            invalid += 1
        case_correct += int(bool(labels) and output == item["expectedOutput"])
        expected_release = all(
            v["verdict"] == "supported" for v in item["expectedOutput"]["verdicts"]
        )
        actual_release = bool(labels) and all(v == "supported" for v in labels.values())
        false_release += int(not expected_release and actual_release)
        false_hold += int(expected_release and not actual_release)
        for sentence in item["input"]:
            sid = sentence["sentence_id"]
            values[f"{item['id']}:{sid}"] = (
                {"verdicts": [{"sentence_id": 0, "verdict": labels[sid]}]} if labels else None
            )
    summary = summarize(flattened(dataset), values)
    return {
        **summary,
        "sentence_count": summary["case_count"],
        "sentence_correct": summary["correct"],
        "sentence_agreement": summary["agreement"],
        "sentence_invalid_or_missing": summary["invalid_or_missing"],
        "case_count": len(dataset["items"]),
        "correct": case_correct,
        "agreement": case_correct / len(dataset["items"]),
        "invalid_or_missing": invalid,
        "report_false_acceptances": false_release,
        "report_false_rejections": false_hold,
    }
