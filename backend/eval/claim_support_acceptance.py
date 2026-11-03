"""Recompute exploratory acceptance from evidence, never a self-reported score."""

from typing import Any

from eval.claim_support_calibration import summarize


def assess(dataset: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    summary = summarize(dataset, actual)
    checks = {
        "complete_valid_outputs": summary["invalid_or_missing"] == 0,
        "no_sentence_false_acceptance": summary["false_acceptances"] == 0,
        "no_report_false_release": summary.get("report_false_acceptances", 0) == 0,
        "exact_agreement_at_least_85_percent": summary["agreement"] >= 0.85,
        "each_label_agreement_at_least_80_percent": all(
            summary["by_label"].get(label, {}).get("total", 0) > 0
            and summary["by_label"][label]["correct"] / summary["by_label"][label]["total"] >= 0.8
            for label in ("supported", "unsupported", "uncertain")
        ),
    }
    return {
        "criteria_version": "exploratory-v1",
        "checks": checks,
        "decision": "eligible_for_further_validation" if all(checks.values()) else "reject",
        "summary": summary,
        "production_approved": False,
        "labels_human_validated": False,
    }
