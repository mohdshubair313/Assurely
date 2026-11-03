"""Calibration preparation must preserve runtime inputs and expose false accepts."""

import json
from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest

from app.graph.claim_support import _PROMPT, PROMPT_VERSION, check_claim_support
from app.llm.providers import LLMResult
from eval.claim_support_calibration import (
    load_dataset,
    model_payload,
    prompt_snapshot,
    review_manifest,
    summarize,
    validate_dataset,
)


def test_reviewed_candidate_preserves_human_review_status_and_runtime_prompt():
    manifest = review_manifest(load_dataset())
    assert manifest["distribution"] == {"supported": 4, "unsupported": 5, "uncertain": 3}
    assert manifest["labels_human_validated"] is False
    assert manifest["production_approved"] is False and manifest["live_calls"] == 0
    assert prompt_snapshot()["text"] == _PROMPT
    assert prompt_snapshot()["version"] == PROMPT_VERSION
    assert load_dataset()["review"]["reviewer_type"] == "AI"
    u3 = next(item for item in load_dataset()["items"] if item["id"] == "U3")
    assert u3["expectedOutput"]["verdicts"][0]["verdict"] == "unsupported"


@pytest.mark.asyncio
@pytest.mark.parametrize("item", load_dataset()["items"], ids=lambda item: item["id"])
async def test_each_candidate_matches_actual_runtime_verifier_input_without_labels(item):
    response = LLMResult(content=json.dumps(item["expectedOutput"]), provider="mock", model="mock")
    sentences = [{"text": value["text"], "citations": value["citations"]}
                 for value in item["input"]]
    with patch("app.graph.claim_support.llm_call", new=AsyncMock(return_value=response)) as llm:
        audit = await check_claim_support(sentences, "calibration-input-contract")
    if item["id"] == "U1":
        llm.assert_not_awaited()
        assert not audit["supported"]
        assert audit["checks"][0]["method"] == "unresolved_citation_set"
        return
    llm.assert_awaited_once()
    payload = llm.await_args.kwargs["messages"][0]["content"]
    assert payload == model_payload(item)
    assert json.loads(payload) == item["input"]
    assert item["metadata"]["rationale"] not in payload
    assert '"expectedOutput"' not in payload and '"metadata"' not in payload


def test_all_agreement_still_never_implies_human_or_production_approval():
    dataset = load_dataset()
    result = summarize(dataset, {item["id"]: item["expectedOutput"] for item in dataset["items"]})
    assert result["agreement"] == 1
    assert result["false_acceptances"] == 0 and result["false_rejections"] == 0
    assert result["labels_human_validated"] is False and result["production_approved"] is False


def test_false_acceptances_rejections_and_missing_results_are_separate():
    dataset = load_dataset()
    actual = {item["id"]: deepcopy(item["expectedOutput"]) for item in dataset["items"]}
    actual["N1"]["verdicts"][0]["verdict"] = "supported"
    actual["U1"]["verdicts"][0]["verdict"] = "supported"
    actual["S1"]["verdicts"][0]["verdict"] = "uncertain"
    del actual["S2"]
    result = summarize(dataset, actual)
    assert result["false_acceptances"] == 2
    assert result["false_rejections"] == 2
    assert result["invalid_or_missing"] == 1
    assert result["correct"] == 8 and len(result["mismatches"]) == 4
    assert result["by_label"]["supported"] == {"total": 4, "correct": 2}


@pytest.mark.parametrize("change", ["label_leak", "duplicate_id", "reviewed", "bad_label"])
def test_invalid_or_falsely_reviewed_dataset_is_rejected(change):
    dataset = load_dataset()
    if change == "label_leak":
        dataset["items"][0]["input"][0]["expected"] = "supported"
    elif change == "duplicate_id":
        dataset["items"][1]["id"] = dataset["items"][0]["id"]
    elif change == "reviewed":
        dataset["labels_human_validated"] = True
    else:
        dataset["items"][0]["expectedOutput"]["verdicts"][0]["verdict"] = "approve"
    with pytest.raises(ValueError):
        validate_dataset(dataset)


def test_unknown_result_id_is_not_silently_ignored():
    with pytest.raises(ValueError):
        summarize(load_dataset(), {"unknown": {}})


def test_boolean_sentence_id_and_extra_keys_are_invalid_results():
    dataset = load_dataset()
    actual = {item["id"]: deepcopy(item["expectedOutput"]) for item in dataset["items"]}
    actual["S1"]["verdicts"][0]["sentence_id"] = False
    actual["S2"]["approved"] = True
    result = summarize(dataset, actual)
    assert result["invalid_or_missing"] == 2
    assert result["correct"] == 10
