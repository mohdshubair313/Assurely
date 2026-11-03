"""Safety criteria cannot hide a false acceptance behind aggregate agreement."""

from copy import deepcopy
from pathlib import Path

import pytest

from eval.claim_support_acceptance import assess
from eval.claim_support_calibration import load_dataset
from eval.provider_diagnostics import verdict_format

PATH = Path(__file__).resolve().parents[2] / "eval/claim_support_batch_candidates.json"


def test_perfect_synthetic_labels_never_authorize_production():
    data = load_dataset(PATH)
    result = assess(data, {i["id"]: i["expectedOutput"] for i in data["items"]})
    assert result["decision"] == "eligible_for_further_validation"
    assert not result["production_approved"] and not result["labels_human_validated"]


def test_conflicting_citation_false_acceptance_rejects_despite_report_hold():
    data = load_dataset(PATH)
    actual = {i["id"]: deepcopy(i["expectedOutput"]) for i in data["items"]}
    actual["B08"]["verdicts"][1]["verdict"] = "supported"
    result = assess(data, actual)
    assert result["summary"]["agreement"] == 0.875
    assert result["checks"]["no_report_false_release"]
    assert not result["checks"]["no_sentence_false_acceptance"]
    assert result["decision"] == "reject"


def test_unavailable_case_is_not_removed_from_denominator():
    data = load_dataset(PATH)
    actual = {i["id"]: i["expectedOutput"] for i in data["items"] if i["id"] != "B01"}
    result = assess(data, actual)
    assert not result["checks"]["complete_valid_outputs"]
    assert result["summary"]["case_count"] == 8
    assert result["decision"] == "reject"


@pytest.mark.parametrize("value,expected", [
    (None, "non_text"), (" ", "empty"), ("```json secret", "code_fence"),
    ('{"secret":', "malformed_json"), ("secret prose", "non_json_prefix"),
    ('{"verdicts":[]}', "json"),
])
def test_format_diagnostic_never_retains_response_text(value, expected):
    assert verdict_format(value) == expected
