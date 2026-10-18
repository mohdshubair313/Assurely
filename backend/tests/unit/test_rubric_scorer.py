"""Rubric privacy, typed failures, layer separation, and citation integrity."""

import copy
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from eval.rubric_scorer import (
    CRITERIA,
    JUDGE_MODEL,
    RubricJudgeError,
    build_packet,
    control_scores,
    judge_packet,
    parse_verdict,
    summarize,
    verdict_schema,
)


def fixture():
    evidence = [
        {
            "id": "fact_1",
            "claim": "Fixture waiting period: 1095 days",
            "source": "Seed Section 4.2",
            "last_verified": "2024-01-01",
        }
    ]
    state = {
        "user_profile": {"age": 40, "confidence_inputs": "PRIVATE_MARKER"},
        "confidence_score": 0.46,
        "guardrail_notes": ["PRIVATE_MARKER"],
        "output": {"sentences": [{"text": evidence[0]["claim"], "citations": evidence}]},
    }
    sample = {
        "answer": evidence[0]["claim"],
        "answer_source": "generated_report",
        "retrieved_chunks": [
            {"claim": "Room-rent fixture", "source": "Section 2.4", "last_verified": "2024-01-01"}
        ],
    }
    case = {"id": "case_04_conflicting_sources", "category": "conflicting_sources"}
    packet = build_packet(case, sample, state, evidence, "Waiting-period clause fixture")
    return sample, state, evidence, packet


def verdict(packet):
    return {
        name: (
            {
                "passed": True,
                "reason": "supported",
                "retrieved_indices": [],
            }
            if CRITERIA[name][0] == "retrieval"
            else {
                "passed": True,
                "reason": "supported",
            }
        )
        for name in packet["rubric"]
    }


def test_confidence_and_internal_notes_never_change_judge_input():
    sample, state, evidence, packet = fixture()
    state.update(confidence_score=1.0, guardrail_notes=["OTHER_PRIVATE_VALUE"], approved=True)
    other = build_packet(
        {"id": "case_04_conflicting_sources", "category": "conflicting_sources"},
        sample,
        state,
        evidence,
        "Waiting-period clause fixture",
    )
    assert packet == other
    assert "PRIVATE_MARKER" not in json.dumps(packet)
    assert "confidence_score" not in json.dumps(packet)


def test_retrieval_miss_cannot_disappear_inside_generation_average():
    sample, state, evidence, packet = fixture()
    scores = verdict(packet)
    for name in ("query_topic_coverage", "reference_clause_coverage"):
        scores[name].update(passed=False, reason=CRITERIA[name][2], retrieved_indices=[0])
    parsed = parse_verdict(json.dumps({"scores": scores}), packet)
    result = summarize(parsed, control_scores(sample, state, evidence))
    assert result["layer_scores"] == {"retrieval": 0.0, "generation": 1.0}
    assert result["credibility_score"] == 1.0
    assert result["review_candidate"] is True
    assert result["label_status"] == "unreviewed_fixture_judge_candidate"


@pytest.mark.parametrize("case_id", ["case_03_missing_info_loop", "case_07_ambiguous_intent"])
def test_clarification_uses_separate_rubric(case_id):
    sample, state, evidence, _ = fixture()
    sample.update(
        answer="Please clarify your age or insurance type.",
        answer_source="clarification_response",
        retrieved_chunks=[],
    )
    case = {"id": case_id, "input": {"user_message": "Please help"}}
    packet = build_packet(case, sample, state, evidence, "irrelevant reference")
    assert set(packet["rubric"]) == {"appropriate_clarification", "no_premature_advice"}
    controls = control_scores(sample, state, evidence)
    assert controls["citations_complete"]["status"] == "not_applicable"
    assert summarize(verdict(packet), controls)["layer_scores"]["retrieval"] is None


@pytest.mark.parametrize("mutation", ["float", "missing", "extra", "echo", "index", "bool_index"])
def test_invalid_or_content_leaking_judge_verdict_is_not_scored(mutation):
    packet = fixture()[3]
    scores = verdict(packet)
    first = scores["query_topic_coverage"]
    if mutation == "float":
        first["passed"] = 1.0
    elif mutation == "missing":
        scores.pop("question_answered")
    elif mutation == "extra":
        first["explanation"] = "PRIVATE_PROFILE_VALUE"
    elif mutation == "echo":
        first["reason"] = "PRIVATE_PROFILE_VALUE"
    elif mutation == "index":
        first["retrieved_indices"] = [99]
    else:
        first["retrieved_indices"] = [True]
    with pytest.raises(RubricJudgeError, match="invalid_judge_schema"):
        parse_verdict(json.dumps({"scores": scores}), packet)


def test_duplicate_json_keys_rejected():
    with pytest.raises(RubricJudgeError):
        parse_verdict('{"scores":{},"scores":{}}', fixture()[3])


def test_generation_fact_volume_does_not_expand_retrieval_indices():
    packet = fixture()[3]
    # A catalog can contain many deterministic facts but only one retrieved clause.
    packet["generation_evidence"] += [
        {"id": f"E{i}", "claim": "Structured fixture fact"} for i in range(2, 20)
    ]
    scores = verdict(packet)
    assert parse_verdict(json.dumps({"scores": scores}), packet) == scores
    scores["query_topic_coverage"]["retrieved_indices"] = [18]
    with pytest.raises(RubricJudgeError) as failed:
        parse_verdict(json.dumps({"scores": scores}), packet)
    assert failed.value.details == {
        "code": "invalid_judge_schema",
        "validation_step": "retrieved_indices",
        "criterion": "query_topic_coverage",
        "allowed_item_count": 1,
        "received_count": 1,
        "validation_reason": "out_of_range",
    }


def test_deterministic_policy_status_does_not_receive_a_clause_retrieval_score():
    evidence = [{
        "id": "status_1",
        "kind": "policy_record_status",
        "claim": "Stored terms expired on the recorded date.",
        "source": "Synthetic isolated policy_terms record",
        "last_verified": "2026-10-15",
    }]
    state = {
        "user_profile": {"age": 40},
        "output": {"sentences": [{"text": evidence[0]["claim"]}]},
    }
    sample = {
        "answer": evidence[0]["claim"],
        "answer_source": "generated_report",
        "retrieved_chunks": [],
    }
    case = {"id": "case_05_outdated_policy", "category": "outdated_policies"}
    packet = build_packet(case, sample, state, evidence, None)

    assert "query_topic_coverage" not in packet["rubric"]
    assert "reference_clause_coverage" not in packet["rubric"]
    assert packet["not_applicable_criteria"] == {
        "query_topic_coverage": "policy_terms_database_lookup_no_clause_retrieval",
        "reference_clause_coverage": "policy_terms_database_lookup_no_clause_retrieval",
    }
    scores = parse_verdict(json.dumps({"scores": verdict(packet)}), packet)
    summary = summarize(scores, {"citations_complete": {"status": "scored", "value": 1}})
    assert summary["layer_scores"] == {"retrieval": None, "generation": 1.0}


@pytest.mark.parametrize(
    "extra_key", ["generation_evidence_ids", "sentence_indices", "explanation"]
)
def test_generation_verdict_rejects_unneeded_or_untrusted_output_fields(extra_key):
    packet = fixture()[3]
    scores = verdict(packet)
    scores["claims_grounded"][extra_key] = "PRIVATE_PROFILE_VALUE"
    with pytest.raises(RubricJudgeError) as failed:
        parse_verdict(json.dumps({"scores": scores}), packet)
    assert failed.value.details["validation_step"] == "score_shape_or_boolean"
    assert "PRIVATE_PROFILE_VALUE" not in json.dumps(failed.value.details)


@pytest.mark.parametrize("damage", ["not_array", "non_integer", "out_of_range", "duplicate"])
def test_index_failure_diagnostics_explain_shape_without_echoing_values(damage):
    packet = fixture()[3]
    scores = verdict(packet)
    scores["query_topic_coverage"]["retrieved_indices"] = {
        "not_array": "PRIVATE_PROFILE_VALUE",
        "non_integer": ["PRIVATE_PROFILE_VALUE"],
        "out_of_range": [2],
        "duplicate": [0, 0],
    }[damage]
    with pytest.raises(RubricJudgeError) as failed:
        parse_verdict(json.dumps({"scores": scores}), packet)
    assert failed.value.details["validation_reason"] == damage
    assert "PRIVATE_PROFILE_VALUE" not in json.dumps(failed.value.details)


def test_schema_requires_indices_only_for_retrieval_criteria():
    packet = fixture()[3]
    schema = verdict_schema(packet)
    properties = schema["properties"]["scores"]["properties"]
    assert set(properties) == set(packet["rubric"])
    generation = properties["claims_grounded"]["properties"]
    assert set(generation) == {"passed", "reason"}
    retrieval = properties["query_topic_coverage"]["properties"]
    assert retrieval["retrieved_indices"]["items"]["enum"] == [0]
    packet.update(retrieved_clauses=[], sentences=[])
    empty = verdict_schema(packet)["properties"]["scores"]["properties"]
    assert empty["query_topic_coverage"]["properties"]["retrieved_indices"]["maxItems"] == 0
    assert parse_verdict(json.dumps({"scores": verdict(packet)}), packet)


@pytest.mark.parametrize("damage", ["missing", "unknown_id", "source", "date", "invalid_date"])
def test_citation_control_rejects_missing_or_tampered_provenance(damage):
    sample, state, evidence, _ = fixture()
    state = copy.deepcopy(state)
    citation = state["output"]["sentences"][0]["citations"][0]
    if damage == "missing":
        state["output"]["sentences"][0]["citations"] = []
    elif damage == "unknown_id":
        citation["id"] = "unknown"
    elif damage == "source":
        citation["source"] = "Other source"
    elif damage == "date":
        citation["last_verified"] = "2025-01-01"
    else:
        citation["last_verified"] = "2024-01-01invalid"
        evidence = copy.deepcopy(evidence)
        evidence[0]["last_verified"] = citation["last_verified"]
    assert control_scores(sample, state, evidence)["citations_complete"]["value"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "problem", ["rate_limit", "empty", "truncated", "paid", "cost_missing", "model", "schema"]
)
async def test_provider_failure_never_becomes_quality_zero_or_retries(problem):
    packet = fixture()[3]
    payload = {
        "model": JUDGE_MODEL,
        "usage": {"cost": 0, "prompt_tokens": 10, "completion_tokens": 20},
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": json.dumps({"scores": verdict(packet)})},
            }
        ],
    }
    if problem == "empty":
        payload["choices"][0]["message"]["content"] = ""
    elif problem == "truncated":
        payload["choices"][0]["finish_reason"] = "length"
    elif problem == "paid":
        payload["usage"]["cost"] = 0.01
    elif problem == "cost_missing":
        payload["usage"].pop("cost")
    elif problem == "model":
        payload["model"] = "unexpected/model"
    elif problem == "schema":
        payload["choices"][0]["message"]["content"] = "{}"
    response = httpx.Response(429 if problem == "rate_limit" else 200, json=payload)
    with patch("eval.rubric_scorer.httpx.AsyncClient") as factory:
        client = factory.return_value.__aenter__.return_value
        client.post = AsyncMock(return_value=response)
        with pytest.raises(RubricJudgeError):
            await judge_packet(packet, "FAKE_TEST_KEY")
        client.post.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("finish_reason", "completion_tokens", "expected_reason", "include_tokens"),
    [
        ("length", 4096, "length", True),
        ("content_filter", 123, "content_filter", True),
        ("PRIVATE_PROFILE_VALUE", True, "other", False),
        ({"private": "PRIVATE_PROFILE_VALUE"}, 4096, "other", True),
    ],
)
async def test_incomplete_judge_failure_records_only_safe_provider_metadata(
    finish_reason, completion_tokens, expected_reason, include_tokens
):
    packet = fixture()[3]
    response_body = {
        "model": JUDGE_MODEL,
        "usage": {
            "cost": 0,
            "prompt_tokens": 234,
            "completion_tokens": completion_tokens,
        },
        "choices": [
            {"finish_reason": finish_reason, "message": {"content": "SENSITIVE_RAW_RESPONSE"}}
        ],
    }
    with patch("eval.rubric_scorer.httpx.AsyncClient") as factory:
        client = factory.return_value.__aenter__.return_value
        client.post = AsyncMock(return_value=httpx.Response(200, json=response_body))
        with pytest.raises(RubricJudgeError) as caught:
            await judge_packet(packet, "FAKE_TEST_KEY")

    details = caught.value.details
    assert details["code"] == "incomplete_judge_response"
    assert details["finish_reason"] == expected_reason
    assert details["completion_limit_tokens"] == 4096
    assert details["prompt_tokens"] == 234
    if include_tokens:
        assert details["completion_tokens"] == completion_tokens
    else:
        assert "completion_tokens" not in details
    assert "SENSITIVE_RAW_RESPONSE" not in json.dumps(details)
    assert "PRIVATE_PROFILE_VALUE" not in json.dumps(details)


@pytest.mark.asyncio
async def test_success_uses_pinned_free_model_and_content_free_result():
    packet = fixture()[3]
    payload = {
        "model": JUDGE_MODEL,
        "usage": {"cost": 0, "prompt_tokens": 100, "completion_tokens": 200},
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": json.dumps({"scores": verdict(packet)})},
            }
        ],
    }
    with patch("eval.rubric_scorer.httpx.AsyncClient") as factory:
        client = factory.return_value.__aenter__.return_value
        client.post = AsyncMock(return_value=httpx.Response(200, json=payload))
        scores, usage = await judge_packet(packet, "FAKE_TEST_KEY")
        request = client.post.call_args.kwargs["json"]
        assert request["model"] == JUDGE_MODEL and request["max_tokens"] == 4096
        assert "fallbacks" not in request and "FAKE_TEST_KEY" not in json.dumps((scores, usage))
        assert request["provider"] == {"require_parameters": True}
        assert request["response_format"] == {
            "type": "json_schema",
            "json_schema": {
                "name": "health_rubric_verdict",
                "strict": True,
                "schema": verdict_schema(packet),
            },
        }


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ["quota", "index_schema"])
async def test_live_runner_keeps_failed_judge_separate_from_quality_and_hides_content(
    monkeypatch,
    tmp_path,
    capsys,
    failure_kind,
):
    from contextlib import asynccontextmanager
    from pathlib import Path
    from types import SimpleNamespace

    from eval import ragas_live as pipeline
    from eval import rubric_live

    @asynccontextmanager
    async def lifespan(_):
        yield

    sample, state, _, _ = fixture()
    sample.update(
        answer="DISTINCTIVE_PRIVATE_PROFILE_VALUE",
        retrieved_fact_count=1,
        session_id="fixture-session",
        delivery_hold=True,
        turns=[{"trace_id": "fixture-trace", "decision_trace_id": "fixture-decision"}],
    )
    monkeypatch.setattr(rubric_live, "preflight", AsyncMock(return_value=True))
    monkeypatch.setattr(
        rubric_live,
        "postgres_versions",
        AsyncMock(
            return_value={
                "all_present": True,
                "expected": 1,
                "found": 1,
            }
        ),
    )
    monkeypatch.setattr(
        rubric_live, "Path", lambda name: tmp_path if name == "/artifacts" else Path(name)
    )
    monkeypatch.setattr(pipeline.app.router, "lifespan_context", lifespan)
    monkeypatch.setattr(pipeline, "run_pipeline_case", AsyncMock(return_value=sample))
    monkeypatch.setattr(
        pipeline._app_graph, "aget_state", AsyncMock(return_value=SimpleNamespace(values=state))
    )
    monkeypatch.setattr(rubric_live.asyncio, "sleep", AsyncMock())
    failure = (
        RubricJudgeError("judge_http_error", http_status=429)
        if failure_kind == "quota"
        else RubricJudgeError(
            "invalid_judge_schema",
            validation_step="retrieved_indices",
            criterion="claims_grounded",
            validation_reason="out_of_range",
            allowed_item_count=1,
            received_count=1,
        )
    )
    monkeypatch.setattr(
        "eval.rubric_scorer.judge_packet",
        AsyncMock(side_effect=failure),
    )
    result = await rubric_live.execute(
        {"preflight": False, "cases": ["case_04_conflicting_sources"], "output_name": "result.json"}
    )
    artifact = json.loads((tmp_path / "result.json").read_text())
    assert result == 2 and artifact["run_status"] == "failed"
    assert artifact["failure"] == {"error_class": "RubricJudgeError", **failure.details}
    assert artifact["postgres_verification"]["all_present"] is True
    assert artifact["cases"][0]["status"] == "pipeline_complete_pending_judge"
    assert "scores" not in artifact["cases"][0]
    assert artifact["cases"][0]["judge_input_counts"]["retrieved_clauses"] == 1
    assert "DISTINCTIVE_PRIVATE_PROFILE_VALUE" not in json.dumps(artifact)
    assert "DISTINCTIVE_PRIVATE_PROFILE_VALUE" not in capsys.readouterr().out


@pytest.mark.asyncio
async def test_provenance_query_uses_existing_json_column_without_database_dependency():
    import uuid
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from eval.rubric_live import postgres_versions

    identifier = uuid.uuid4()
    row = SimpleNamespace(
        id=identifier,
        model_version="fixture-model",
        prompt_version="fixture-v1",
        policy_versions_evaluated_json=[{"policy_id": "fixture-policy"}],
    )
    result = MagicMock()
    result.all.return_value = [row]
    with patch("app.db.session.AsyncSessionLocal") as factory:
        database = factory.return_value.__aenter__.return_value
        database.execute = AsyncMock(return_value=result)
        verified = await postgres_versions([{"decision_trace_ids": [str(identifier)]}])
    assert verified["all_present"] is True
    assert (
        verified["versions"][0]["policy_versions_evaluated"] == row.policy_versions_evaluated_json
    )
    assert "policy_versions_evaluated_json" in str(database.execute.call_args.args[0])
