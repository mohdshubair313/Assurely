"""Batch calibration must match runtime payloads and expose partial false support."""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.graph.claim_support import check_claim_support
from app.llm.providers import LLMResult
from eval.claim_support_calibration import load_dataset, model_payload, summarize, validate_dataset

PATH = Path(__file__).resolve().parents[2] / "eval/claim_support_batch_candidates.json"


@pytest.mark.asyncio
@pytest.mark.parametrize("item", load_dataset(PATH)["items"], ids=lambda i: i["id"])
async def test_batch_uses_exact_runtime_semantic_payload_and_atomic_hold(item):
    result = LLMResult(content=json.dumps(item["expectedOutput"]), provider="mock", model="mock")
    with patch("app.graph.claim_support.llm_call", new=AsyncMock(return_value=result)) as llm:
        audit = await check_claim_support(
            [{"text": s["text"], "citations": s["citations"]} for s in item["input"]], "batch"
        )
    if item["id"] in {"B07", "B08"}:
        llm.assert_not_awaited()
        assert audit["supported"] is False
        assert any(c["method"] == "unresolved_citation_set" for c in audit["checks"])
        return
    llm.assert_awaited_once()
    assert llm.await_args.kwargs["messages"][0]["content"] == model_payload(item)
    assert audit["supported"] == all(
        v["verdict"] == "supported" for v in item["expectedOutput"]["verdicts"]
    )


def test_sentence_false_accept_is_exposed_even_when_another_sentence_holds_report():
    data = load_dataset(PATH)
    actual = {i["id"]: deepcopy(i["expectedOutput"]) for i in data["items"]}
    actual["B08"]["verdicts"][1]["verdict"] = "supported"
    report = summarize(data, actual)
    assert report["false_acceptances"] == 1
    assert report["report_false_acceptances"] == 0
    assert report["correct"] == 7 and report["sentence_correct"] == 17
    actual["B08"]["verdicts"][2]["verdict"] = "supported"
    assert summarize(data, actual)["report_false_acceptances"] == 1


def test_malformed_batch_invalidates_all_sentences_not_just_missing_id():
    data = load_dataset(PATH)
    actual = {i["id"]: deepcopy(i["expectedOutput"]) for i in data["items"]}
    actual["B01"]["verdicts"].pop()
    report = summarize(data, actual)
    assert report["invalid_or_missing"] == 1 and report["sentence_invalid_or_missing"] == 2
    assert report["false_rejections"] == 2 and report["report_false_rejections"] == 1


@pytest.mark.parametrize("mutation", ["duplicate_id", "bool_id", "missing_label", "reviewed"])
def test_invalid_batch_is_rejected(mutation):
    data = load_dataset(PATH)
    if mutation == "duplicate_id":
        data["items"][0]["input"][1]["sentence_id"] = 0
    elif mutation == "bool_id":
        data["items"][0]["input"][0]["sentence_id"] = False
    elif mutation == "missing_label":
        data["items"][0]["expectedOutput"]["verdicts"].pop()
    else:
        data["labels_human_validated"] = True
    with pytest.raises(ValueError):
        validate_dataset(data)
