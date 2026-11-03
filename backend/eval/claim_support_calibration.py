"""Offline preparation/scoring for the candidate claim-support calibration set.

No settings import, dotenv access, provider call or cloud mutation occurs here.
This does not substitute for a real Langfuse SDK experiment or human label review.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

DEFAULT_DATASET = Path(__file__).with_name("claim_support_candidates.json")
RUNTIME = Path(__file__).resolve().parents[1] / "app/graph/claim_support.py"
LABELS = {"supported", "unsupported", "uncertain"}


def prompt_snapshot(path: Path = RUNTIME) -> dict[str, str]:
    """Read literal prompt constants without importing runtime/provider settings."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"_PROMPT", "PROMPT_VERSION"}:
                    constants[target.id] = ast.literal_eval(node.value)
    if set(constants) != {"_PROMPT", "PROMPT_VERSION"} or not all(
        isinstance(value, str) and value for value in constants.values()
    ):
        raise ValueError("Runtime prompt constants are missing or not literal strings")
    return {
        "version": constants["PROMPT_VERSION"],
        "text": constants["_PROMPT"],
        "sha256": hashlib.sha256(constants["_PROMPT"].encode()).hexdigest(),
    }


def validate_dataset(dataset: dict[str, Any]) -> None:
    if dataset.get("cohort"):
        from eval.claim_support_batch import validate_batch

        validate_batch(dataset)
        return
    if dataset.get("name") != "judge-calibration/claim-support":
        raise ValueError("Unexpected dataset identity")
    if dataset.get("labels_human_validated") is not False:
        raise ValueError("This preparation tool handles unreviewed candidates only")
    items = dataset.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Dataset must contain candidate cases")
    seen = set()
    labels = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"id", "input", "expectedOutput", "metadata"}:
            raise ValueError("Invalid dataset item fields")
        if not isinstance(item["id"], str) or not item["id"] or item["id"] in seen:
            raise ValueError("Case IDs must be nonempty and unique")
        seen.add(item["id"])
        metadata = item["metadata"]
        if (
            not isinstance(metadata, dict)
            or metadata.get("label_status") != "candidate_unreviewed"
            or metadata.get("source_type") != "synthetic"
            or not metadata.get("category")
            or not metadata.get("rationale")
        ):
            raise ValueError("Candidate metadata must identify source, category and label status")
        inputs = item["input"]
        if not isinstance(inputs, list) or len(inputs) != 1:
            raise ValueError("Each initial candidate must contain one semantic sentence")
        sentence = inputs[0]
        if (
            not isinstance(sentence, dict)
            or set(sentence) != {"sentence_id", "text", "citations"}
            or type(sentence["sentence_id"]) is not int
            or sentence["sentence_id"] != 0
            or not isinstance(sentence["text"], str)
            or not sentence["text"].strip()
        ):
            raise ValueError("Input must match the runtime semantic payload")
        citations = sentence["citations"]
        if not isinstance(citations, list) or not citations:
            raise ValueError("Citations are required")
        for citation in citations:
            if (
                not isinstance(citation, dict)
                or set(citation) != {"id", "claim", "kind", "source", "last_verified"}
                or not all(isinstance(v, str) and v for v in citation.values())
                or citation["kind"] != "clause_wording"
            ):
                raise ValueError("Initial semantic candidates use synthetic clause citations")
        expected = item["expectedOutput"]
        if not isinstance(expected, dict) or set(expected) != {"verdicts"}:
            raise ValueError("Expected output must use the runtime verdict shape")
        verdicts = expected["verdicts"]
        if not isinstance(verdicts, list) or len(verdicts) != 1:
            raise ValueError("Expected output must contain one verdict")
        verdict = verdicts[0]
        if (
            not isinstance(verdict, dict)
            or set(verdict) != {"sentence_id", "verdict"}
            or type(verdict["sentence_id"]) is not int
            or verdict["sentence_id"] != 0
            or not isinstance(verdict["verdict"], str)
            or verdict["verdict"] not in LABELS
        ):
            raise ValueError("Invalid expected verdict")
        labels.add(verdict["verdict"])
    if labels != LABELS:
        raise ValueError("The draft must cover supported, unsupported and uncertain outcomes")


def load_dataset(path: Path = DEFAULT_DATASET) -> dict[str, Any]:
    dataset = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(dataset, dict):
        raise ValueError("Dataset root must be an object")
    validate_dataset(dataset)
    return dataset


def model_payload(item: dict[str, Any]) -> str:
    """Serialize only runtime input, never labels, categories or rationales."""
    return (
        json.dumps(item["input"], ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def summarize(dataset: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    """Score exact verdict agreement; invalid/missing outputs are failures, not passes."""
    if dataset.get("cohort"):
        from eval.claim_support_batch import summarize_batch

        return summarize_batch(dataset, actual)
    validate_dataset(dataset)
    ids = {item["id"] for item in dataset["items"]}
    if set(actual) - ids:
        raise ValueError("Result contains an unknown case ID")
    counts: Counter[str] = Counter()
    mismatches = []
    by_label: dict[str, dict[str, int]] = {
        label: {"total": 0, "correct": 0} for label in sorted(LABELS)
    }
    for item in dataset["items"]:
        expected = item["expectedOutput"]
        label = expected["verdicts"][0]["verdict"]
        value = actual.get(item["id"])
        # Explicit Boolean ID rejection: Python's True == 1 must not validate JSON IDs.
        valid = (
            isinstance(value, dict)
            and set(value) == {"verdicts"}
            and isinstance(value["verdicts"], list)
            and len(value["verdicts"]) == 1
            and isinstance(value["verdicts"][0], dict)
            and set(value["verdicts"][0]) == {"sentence_id", "verdict"}
            and type(value["verdicts"][0]["sentence_id"]) is int
            and value["verdicts"][0]["sentence_id"] == 0
            and isinstance(value["verdicts"][0]["verdict"], str)
            and value["verdicts"][0]["verdict"] in LABELS
        )
        predicted = (
            value["verdicts"][0]["verdict"]
            if valid and isinstance(value, dict)
            else "invalid_or_missing"
        )
        correct = valid and value == expected
        counts["correct"] += int(correct)
        counts["invalid_or_missing"] += int(not valid)
        counts["false_acceptances"] += int(label != "supported" and predicted == "supported")
        counts["false_rejections"] += int(label == "supported" and predicted != "supported")
        by_label[label]["total"] += 1
        by_label[label]["correct"] += int(correct)
        if not correct:
            mismatches.append(
                {
                    "id": item["id"],
                    "expected": label,
                    "actual": predicted,
                    "category": item["metadata"]["category"],
                }
            )
    return {
        "case_count": len(ids),
        **counts,
        "agreement": counts["correct"] / len(ids),
        "by_label": by_label,
        "mismatches": mismatches,
        "labels_human_validated": False,
        "production_approved": False,
    }


def review_manifest(dataset: dict[str, Any]) -> dict[str, Any]:
    validate_dataset(dataset)
    return {
        "dataset": dataset["name"],
        "case_count": len(dataset["items"]),
        "distribution": dict(
            Counter(
                v["verdict"]
                for item in dataset["items"]
                for v in item["expectedOutput"]["verdicts"]
            )
        ),
        "dataset_sha256": hashlib.sha256(
            json.dumps(dataset, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "prompt": prompt_snapshot(),
        "labels_human_validated": False,
        "live_calls": 0,
        "production_approved": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    manifest = review_manifest(load_dataset(args.dataset))
    # Preserve earlier review artifacts rather than silently replacing a snapshot.
    with args.manifest.open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    print(json.dumps({key: value for key, value in manifest.items() if key != "prompt"}))


if __name__ == "__main__":
    main()
