"""Experiment reliability: strict parsing, snapshot parity and safe failed calls."""

import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.graph.support_verdict import parse_verdict
from eval.claim_support_calibration import load_dataset
from eval.claim_support_experiment import exact_match, infer, verify_remote_items


def remote_items():
    return [
        SimpleNamespace(
            input=i["input"],
            expected_output=i["expectedOutput"],
            metadata={**i["metadata"], "case_id": i["id"], "labels_human_validated": False},
        )
        for i in deepcopy(load_dataset()["items"])
    ]


@pytest.mark.parametrize(
    "content,finish,ids",
    [
        ('{"verdicts":[],"verdicts":[]}', "stop", set()),
        ('{"verdicts":[{"sentence_id":false,"verdict":"supported"}]}', "stop", {0}),
        ('{"verdicts":[{"sentence_id":0,"verdict":"supported","extra":1}]}', "stop", {0}),
        ('{"verdicts":[{"sentence_id":0,"verdict":"supported"}]}', "length", {0}),
        ('{"verdicts":[{"sentence_id":0,"verdict":"supported"}]}', "stop", {0, 1}),
        (
            '{"verdicts":[{"sentence_id":0,"verdict":"supported"},'
            '{"sentence_id":0,"verdict":"supported"}]}',
            "stop",
            {0, 1},
        ),
    ],
)
def test_strict_parser_rejects_invalid_contract(content, finish, ids):
    with pytest.raises(ValueError):
        parse_verdict(content, finish, ids)


def test_exact_score_rejects_bool_id_and_extra_keys():
    expected = load_dataset()["items"][0]["expectedOutput"]
    assert exact_match(expected, expected)
    bad = deepcopy(expected)
    bad["verdicts"][0]["sentence_id"] = False
    assert not exact_match(bad, expected)
    assert not exact_match({**expected, "error": "unexpected"}, expected)
    assert not exact_match(None, expected)


@pytest.mark.parametrize(
    "mutation",
    ["input", "label", "review", "missing", "duplicate", "bool_input_id", "bool_label_id"],
)
def test_cloud_drift_is_detected_before_inference(mutation):
    items = remote_items()
    verify_remote_items(load_dataset(), items)
    if mutation == "input":
        items[0].input[0]["text"] += " changed"
    elif mutation == "label":
        items[0].expected_output["verdicts"][0]["verdict"] = "uncertain"
    elif mutation == "review":
        items[0].metadata["labels_human_validated"] = True
    elif mutation == "missing":
        items.pop()
    elif mutation == "bool_input_id":
        items[0].input[0]["sentence_id"] = False
    elif mutation == "bool_label_id":
        items[0].expected_output["verdicts"][0]["sentence_id"] = False
    else:
        items.append(items[0])
    with pytest.raises(ValueError):
        verify_remote_items(load_dataset(), items)


@pytest.mark.asyncio
async def test_provider_exception_is_sanitized_and_not_retried(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-secret")
    with patch(
        "httpx.AsyncClient.post",
        new=AsyncMock(side_effect=RuntimeError("synthetic-secret private provider body")),
    ) as post:
        output, info = await infer("[]", "prompt")
    assert output is None and info["status"] == "failed"
    assert info["error_type"] == "RuntimeError"
    assert "synthetic-secret" not in json.dumps(info)
    post.assert_awaited_once()


@pytest.mark.asyncio
async def test_truncated_completion_cannot_score_as_success(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-secret")
    result = SimpleNamespace(
        status_code=200,
        raise_for_status=lambda: None,
        json=lambda: {
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {
                        "content": '{"verdicts":[{"sentence_id":0,"verdict":"supported"}]}'
                    },
                }
            ]
        },
    )
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=result)):
        output, info = await infer('[{"sentence_id":0}]', "prompt")
    assert output is None and info["finish_reason"] == "length"
    assert info["status"] == "failed"


def test_interrupted_experiment_preserves_completed_case_journal(tmp_path, monkeypatch):
    import asyncio

    from eval.claim_support_calibration import prompt_snapshot
    from eval.claim_support_experiment import MODEL, run

    item = remote_items()[0]
    items = remote_items()

    class Span:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def update(self, **kwargs):
            pass

    class Dataset:
        def __init__(self):
            self.items = items

        def run_experiment(self, *, task, **kwargs):
            asyncio.run(task(item=item))
            raise RuntimeError("simulated interruption after first case")

    fake = SimpleNamespace(
        get_dataset=lambda name: Dataset(),
        get_prompt=lambda *args, **kwargs: SimpleNamespace(
            prompt=prompt_snapshot()["text"],
            config={"model": MODEL, "temperature": 0, "max_tokens": 2048},
        ),
        start_as_current_observation=lambda **kwargs: Span(),
        flush=lambda: None,
    )
    monkeypatch.setattr("langfuse.Langfuse", lambda **kwargs: fake)
    monkeypatch.setattr(
        "eval.claim_support_experiment.infer",
        AsyncMock(return_value=(item.expected_output, {"status": "parsed"})),
    )
    output = tmp_path / "interrupted.json"
    with pytest.raises(RuntimeError, match="sanitized receipt"):
        run(
            {
                "output": str(output),
                "run_name": "interrupted",
                "prompt_version": 1,
                "interval_seconds": 0,
            }
        )
    journal = json.loads(output.with_suffix(".items.jsonl").read_text())
    assert journal["case_id"] == "S1" and journal["output"] == item.expected_output
    receipt = json.loads(output.read_text())
    assert receipt["status"] == "failed" and receipt["calls"]["S1"]["status"] == "parsed"
    assert "simulated interruption" not in output.read_text()
    with pytest.raises(FileExistsError):
        run({"output": str(output), "run_name": "duplicate", "prompt_version": 1})
