"""Security behavior for restricted diagnostics, retention and correlations."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import stat
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.correlation import correlation_scope, current_turn, database_session_id, node_scope
from app.core.exception_log import LoggingBoundary, admin_read
from app.core.tracing import request_trace, trace_node
from app.main import create_app

SENTINEL = "FAKE_PROFILE_ZEBRA_93741"


@pytest.fixture
def logs(tmp_path: Path):
    stream = io.StringIO()
    settings = Settings(
        _env_file=None, exception_log_dir=str(tmp_path / "private"), log_level="debug",
    )
    boundary = LoggingBoundary(settings, stream)
    try:
        yield boundary, stream
    finally:
        boundary.close()


def records(boundary: LoggingBoundary):
    return [json.loads(path.read_text()) for path in boundary.sink.directory.glob("*.json")]


def test_private_record_and_general_reference_never_include_content(logs) -> None:
    boundary, stream = logs
    logger = logging.getLogger("app.test_exception_log")
    with correlation_scope(SENTINEL) as turn, node_scope("explanation-report"):
        # Register SENTINEL as a known profile value so the scrubber removes it.
        turn.profile_snapshot = {"name": SENTINEL}
        try:
            try:
                raise ValueError(SENTINEL)
            except ValueError as cause:
                error = RuntimeError(f"profile={SENTINEL}")
                error.add_note(SENTINEL)
                raise error from cause
        except RuntimeError:
            logger.exception("Request=%s generated=%s", SENTINEL, SENTINEL, stack_info=True)
            logger.warning("Retry failed: %s", SENTINEL)
        logger.info("Query/profile: %s", SENTINEL)
        expected = turn.identifiers()
    rows = records(boundary)
    assert len(rows) == 1  # Same exception is not duplicated by nested handlers.
    row = rows[0]
    assert row["exception_class"] == "RuntimeError"
    assert row["causes"][0]["exception_class"] == "ValueError"
    assert row["traceback"] and row["node"] == "explanation-report"
    assert {key: row[key] for key in expected} == expected
    assert row["session_id"] == str(database_session_id(SENTINEL))
    # SENTINEL should be scrubbed from the exception record (profile scrubbing)
    # and from the general log stream (argument stripping).
    assert SENTINEL not in json.dumps(rows) + stream.getvalue()
    assert "RuntimeError" not in stream.getvalue()
    assert f"error_ref={row['error_ref']}" in stream.getvalue()
    assert stat.S_IMODE(boundary.sink.directory.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in boundary.sink.directory.iterdir())


def test_admin_reader_rejects_non_admin_and_path_traversal(logs, monkeypatch) -> None:
    boundary, _ = logs
    with pytest.raises(ValueError):
        admin_read(str(boundary.sink.directory), "../../etc/passwd")
    monkeypatch.setattr(os, "geteuid", lambda: 65534)
    with pytest.raises(PermissionError):
        admin_read(str(boundary.sink.directory), "0" * 32)


def test_expiry_and_record_count_limits_are_enforced(logs) -> None:
    boundary, _ = logs
    boundary.sink.max_records = 2
    for _ in range(3):
        try:
            raise RuntimeError(SENTINEL)
        except RuntimeError:
            logging.getLogger("app.test_exception_log").exception("Hidden")
    paths = list(boundary.sink.directory.glob("*.json"))
    assert len(paths) == 2
    expired = time.time() - boundary.sink.retention_seconds - 1
    os.utime(paths[0], (expired, expired))
    boundary.sink.prune()
    assert len(list(boundary.sink.directory.glob("*.json"))) == 1


def test_sink_failure_does_not_fall_back_to_raw_stderr(logs, monkeypatch) -> None:
    boundary, stream = logs
    monkeypatch.setattr(boundary.sink, "emit", Mock(side_effect=OSError(SENTINEL)))
    try:
        raise RuntimeError(SENTINEL)
    except RuntimeError:
        logging.getLogger("app.test_exception_log").exception(SENTINEL)
    assert boundary.sink.failed
    assert "error_ref=" in stream.getvalue()
    assert SENTINEL not in stream.getvalue()


def test_symlink_destination_fails_startup(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    link = tmp_path / "link"
    link.symlink_to(actual, target_is_directory=True)
    with pytest.raises(RuntimeError, match="symlinks"):
        LoggingBoundary(Settings(_env_file=None, exception_log_dir=str(link)))


@pytest.mark.asyncio
async def test_parallel_nodes_and_requests_keep_correct_correlations(logs) -> None:
    boundary, _ = logs

    async def failure(state):
        await asyncio.sleep(0)
        raise RuntimeError(SENTINEL)

    async def turn_run(session):
        with correlation_scope(session) as turn:
            results = await asyncio.gather(
                trace_node("risk-analysis", failure)({}),
                trace_node("health-domain-agent", failure)({}),
                return_exceptions=True,
            )
            assert all(isinstance(result, RuntimeError) for result in results)
            return turn.identifiers()

    turns = await asyncio.gather(turn_run("parallel-a"), turn_run("parallel-b"))
    rows = records(boundary)
    assert len(rows) == 4
    for turn in turns:
        matching = [row for row in rows if row["trace_id"] == turn["trace_id"]]
        assert len(matching) == 2
        assert {row["node"] for row in matching} == {"risk-analysis", "health-domain-agent"}
        assert all(row["session_id"] == turn["session_id"] for row in matching)
    assert current_turn.get() is None


def test_langfuse_root_uses_same_trace_and_decision_identifiers() -> None:
    client = MagicMock()
    with (
        patch("app.core.tracing._get_client", return_value=client),
        correlation_scope(SENTINEL) as turn,
        request_trace(SENTINEL, message_char_count=10),
    ):
        kwargs = client.start_as_current_observation.call_args.kwargs
        assert kwargs["trace_context"] == {"trace_id": turn.trace_id}
        assert kwargs["metadata"]["decision_trace_id"] == turn.decision_trace_id
        assert SENTINEL not in repr(kwargs)


@pytest.mark.asyncio
async def test_unhandled_node_failure_preserves_diagnostics_before_reraising(logs) -> None:
    boundary, _ = logs
    node = AsyncMock(side_effect=RuntimeError(SENTINEL))
    with correlation_scope("failure"), pytest.raises(RuntimeError, match=SENTINEL):
        await trace_node("persist-memory", node)({})
    assert records(boundary)[0]["node"] == "persist-memory"


def test_idle_retention_and_unhealthy_sink_readiness(tmp_path, monkeypatch) -> None:
    settings = Settings(
        _env_file=None, exception_log_dir=str(tmp_path / "private"),
        exception_log_cleanup_seconds=1,
    )
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    application = create_app()
    with TestClient(application) as client:
        sink = application.state.exception_sink
        try:
            raise RuntimeError(SENTINEL)
        except RuntimeError:
            logging.getLogger("app.test_exception_log").exception("Synthetic")
        path = next(sink.directory.glob("*.json"))
        expired = time.time() - sink.retention_seconds - 1
        os.utime(path, (expired, expired))
        deadline = time.monotonic() + 3
        while path.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not path.exists(), "Idle retention worker did not expire the record"
        assert client.get("/health").status_code == 200
        monkeypatch.setattr(sink, "emit", Mock(side_effect=OSError(SENTINEL)))
        try:
            raise RuntimeError(SENTINEL)
        except RuntimeError:
            logging.getLogger("app.test_exception_log").exception("Synthetic")
        assert client.get("/health").status_code == 503


def test_database_never_enables_parameter_logging_from_debug_setting() -> None:
    from app.db.session import async_engine

    assert async_engine.echo is False
    assert async_engine.sync_engine.hide_parameters is True


def test_allowlisted_exception_retains_useful_message(logs) -> None:
    """Allowlisted class (ConnectionError) keeps its diagnostic message in the record."""
    boundary, stream = logs
    with correlation_scope("allowlist-test"), node_scope("health-domain-agent"):
        try:
            raise ConnectionError(
                "Connection refused: localhost:5432 - cannot connect to Postgres"
            )
        except ConnectionError:
            logging.getLogger("app.test_exception_log").exception("DB down")
    rows = records(boundary)
    assert len(rows) == 1
    row = rows[0]
    assert row["exception_class"] == "ConnectionError"
    # The full infrastructure message is kept — this is the allowlisted behavior.
    assert "localhost:5432" in row["message"]
    assert "cannot connect to Postgres" in row["message"]
    # General logs still don't contain the message text.
    assert "localhost:5432" not in stream.getvalue()


def test_allowlisted_exception_scrubs_nested_profile_values(logs) -> None:
    """Infrastructure allowlisting must not bypass scrubbing of nested profile data."""
    boundary, stream = logs
    fake_condition = "FAKE_PED_CONDITION_8472"
    with correlation_scope("allowlist-profile-test") as turn, node_scope(
        "health-domain-agent"
    ):
        turn.profile_snapshot = {"pre_existing_conditions": [fake_condition]}
        try:
            raise ConnectionError(
                f"Database unavailable while evaluating {fake_condition}"
            )
        except ConnectionError:
            logging.getLogger("app.test_exception_log").exception("DB down")

    rows = records(boundary)
    assert len(rows) == 1
    assert rows[0]["exception_class"] == "ConnectionError"
    assert fake_condition not in rows[0]["message"]
    assert fake_condition not in stream.getvalue()
    assert "Database unavailable" in rows[0]["message"]


def test_free_form_exception_messages_are_redacted_without_profile_context(logs) -> None:
    """PII-free generated or request text is not safe merely because it lacks a pattern."""
    boundary, stream = logs
    fake_generated = "FAKE_GENERATED_SENTENCE_OR_USER_TEXT_59381"
    logger = logging.getLogger("app.test_exception_log")

    for error in (RuntimeError, ConnectionError):
        try:
            raise error(fake_generated)
        except error:
            logger.exception("Synthetic failure")

    rows = records(boundary)
    assert len(rows) == 2
    assert all(fake_generated not in row["message"] for row in rows)
    assert all(row["message"] == "[MESSAGE REDACTED]" for row in rows)
    assert fake_generated not in stream.getvalue()


def test_screening_exception_reuses_request_correlation_and_profile_context(
    logs, monkeypatch
) -> None:
    """Request-scoped screening errors inherit trace IDs and document scrub values."""
    from app.core import exception_log
    from app.rag import ingestion_screening

    boundary, stream = logs
    fake_profile = "FAKE_PROFILE_SCREENING_7842"
    fake_document = "FAKE_DOCUMENT_CONTENT_SCREENING_9281"
    captured_values: set[str] = set()
    original_safe_exception = exception_log.safe_exception

    def observe_scrub_context(exc: BaseException) -> dict[str, object]:
        captured_values.update(exception_log._get_profile_values())
        return original_safe_exception(exc)

    monkeypatch.setattr(exception_log, "safe_exception", observe_scrub_context)
    session_id = "11111111-2222-4333-8444-555555555555"
    with correlation_scope(session_id) as turn:
        original_profile = {"name": fake_profile}
        turn.profile_snapshot = original_profile
        with patch.object(
            ingestion_screening,
            "check_domain_allowlist",
            side_effect=RuntimeError(fake_document),
        ):
            result = ingestion_screening.screen_document(
                fake_document,
                "https://www.hdfcergo.com/policy.pdf",
            )
        assert result.outcome.value == "quarantine"
        assert turn.profile_snapshot == original_profile
        expected_trace_id = turn.trace_id

    rows = records(boundary)
    assert len(rows) == 1
    row = rows[0]
    assert row["session_id"] == str(database_session_id(session_id))
    assert row["trace_id"] == expected_trace_id
    assert row["node"] == "ingestion-screening"
    assert fake_profile in captured_values
    assert fake_document in captured_values
    assert fake_profile not in json.dumps(row) + stream.getvalue()
    assert fake_document not in json.dumps(row) + stream.getvalue()


def test_standalone_screening_creates_trace_context_for_exceptions(logs, monkeypatch) -> None:
    """Screening outside HTTP still gets a trace ID and document-aware scrub scope."""
    from app.core import exception_log
    from app.rag import ingestion_screening

    boundary, _ = logs
    captured_values: set[str] = set()
    original_safe_exception = exception_log.safe_exception

    def observe_scrub_context(exc: BaseException) -> dict[str, object]:
        captured_values.update(exception_log._get_profile_values())
        return original_safe_exception(exc)

    monkeypatch.setattr(exception_log, "safe_exception", observe_scrub_context)
    fake_document = "FAKE_STANDALONE_SCREENING_DOCUMENT_3872"
    with patch.object(
        ingestion_screening,
        "check_domain_allowlist",
        side_effect=RuntimeError(fake_document),
    ):
        ingestion_screening.screen_document(
            fake_document,
            "https://www.hdfcergo.com/policy.pdf",
        )

    rows = records(boundary)
    assert len(rows) == 1
    assert rows[0]["session_id"] is None
    assert rows[0]["trace_id"]
    assert rows[0]["node"] == "ingestion-screening"
    assert fake_document in captured_values
    assert fake_document not in json.dumps(rows)


def test_standalone_screening_logs_only_sanitized_exception(caplog, monkeypatch) -> None:
    """Without app lifespan logging handlers, direct screening still emits no raw error text."""
    from app.rag import ingestion_screening

    fake_document = "FAKE_STANDALONE_EXCEPTION_TEXT_72391"
    with (
        patch.object(
            ingestion_screening,
            "check_domain_allowlist",
            side_effect=RuntimeError(fake_document),
        ),
        caplog.at_level(logging.ERROR, logger="app.rag.ingestion_screening"),
    ):
        result = ingestion_screening.screen_document(
            fake_document,
            "https://www.hdfcergo.com/policy.pdf",
        )

    assert fake_document not in caplog.text
    assert "[MESSAGE REDACTED]" in caplog.text
    assert all(fake_document not in reason for reason in result.reasons)


def test_non_allowlisted_exception_scrubs_profile_values(logs, monkeypatch) -> None:
    """Non-allowlisted RuntimeError with fake profile values gets them scrubbed."""
    boundary, stream = logs
    fake_name = "Rahul Sharma"
    fake_phone = "+919876543210"
    fake_email = "rahul.sharma@example.com"
    fake_aadhaar = "1234 5678 9012"
    fake_pan = "ABCDE1234F"

    profile = {
        "name": fake_name,
        "phone": fake_phone,
        "email": fake_email,
        "aadhaar": fake_aadhaar,
        "pan": fake_pan,
        "age": 35,
        "city": "Mumbai",
    }

    with correlation_scope("scrub-test") as turn, node_scope("explanation-report"):
        # Attach profile snapshot for the scrubber to use.
        turn.profile_snapshot = profile
        try:
            raise RuntimeError(
                f"Failed for user {fake_name}, phone {fake_phone}, "
                f"email {fake_email}, aadhaar {fake_aadhaar}, PAN {fake_pan}, "
                f"age 35, city Mumbai, PIN 400001"
            )
        except RuntimeError:
            logging.getLogger("app.test_exception_log").exception("Processing error")

    rows = records(boundary)
    assert len(rows) == 1
    row = rows[0]
    assert row["exception_class"] == "RuntimeError"
    msg = row["message"]

    # All PII should be scrubbed.
    assert fake_name not in msg, f"Profile name '{fake_name}' was not scrubbed"
    assert fake_phone not in msg, f"Phone '{fake_phone}' was not scrubbed"
    assert fake_email not in msg, f"Email '{fake_email}' was not scrubbed"
    assert fake_aadhaar not in msg, f"Aadhaar '{fake_aadhaar}' was not scrubbed"
    assert fake_pan not in msg, f"PAN '{fake_pan}' was not scrubbed"
    assert "Mumbai" not in msg, "City 'Mumbai' was not scrubbed"

    # Structural content remains (replacement tokens present).
    assert "[PROFILE]" in msg or "[PHONE]" in msg or "[EMAIL]" in msg
    assert "Failed for user" in msg  # Non-PII structural text preserved.

    # General log stream never gets the original message either.
    assert fake_name not in stream.getvalue()
    assert fake_phone not in stream.getvalue()


@pytest.mark.asyncio
async def test_failing_database_insert_hides_parameters(logs) -> None:
    """SQLAlchemy's hidden-parameter error representation is tested without Postgres."""
    from sqlalchemy.exc import StatementError

    boundary, stream = logs
    fake_name = "SuperSecretPerson"
    fake_email = "supersecret@example.test"

    with correlation_scope("db-fail-test"), node_scope("persist-memory"):
        try:
            raise StatementError(
                "Database execution failed",
                "INSERT INTO users (name, email) VALUES (:name, :email)",
                {"name": fake_name, "email": fake_email},
                RuntimeError("driver error"),
                hide_parameters=True,
            )
        except Exception:
            logging.getLogger("app.test_exception_log").exception("DB insert failed")

    rows = records(boundary)
    assert len(rows) >= 1
    for r in rows:
        msg = r["message"]
        assert fake_name not in msg, f"Fake profile name leaked in DB error message: {msg}"
        assert fake_email not in msg, f"Fake email leaked in DB error message: {msg}"
    assert fake_name not in stream.getvalue()
    assert fake_email not in stream.getvalue()


def test_http_status_error_strips_query_string_from_url(logs) -> None:
    """HTTPStatusError with sensitive query parameters has query string stripped in sink."""
    import httpx

    boundary, stream = logs
    fake_key = "fake_provider_key_xyz123456"
    fake_token = "fake_jwt_token_abcdef98765"
    url = f"https://api.provider.test/v1/chat/completions?key={fake_key}&token={fake_token}"

    req = httpx.Request("POST", url)
    resp = httpx.Response(status_code=403, request=req)

    with correlation_scope("httpx-test"), node_scope("health-domain-agent"):
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            logging.getLogger("app.test_exception_log").exception("Provider call failed")

    rows = records(boundary)
    assert len(rows) == 1
    row = rows[0]
    assert row["exception_class"] == "HTTPStatusError"
    msg = row["message"]
    assert fake_key not in msg, f"Secret key leaked in HTTP error message: {msg}"
    assert fake_token not in msg, f"Secret token leaked in HTTP error message: {msg}"
    assert "?key=" not in msg, f"Query string was not stripped from URL in message: {msg}"
    assert "https://api.provider.test/v1/chat/completions" in msg
    assert fake_key not in stream.getvalue()


def test_allowlisted_exception_scrubs_connection_credentials(logs) -> None:
    """Allowlisted ConnectionError has DB passwords scrubbed from connection strings."""
    boundary, stream = logs
    secret_pass = "super_secret_db_password_987"
    raw_msg = f"Failed to connect to postgresql+asyncpg://insurance_user:{secret_pass}@postgres:5432/insurance_db"

    with correlation_scope("conn-test"), node_scope("health-domain-agent"):
        try:
            raise ConnectionError(raw_msg)
        except ConnectionError:
            logging.getLogger("app.test_exception_log").exception("DB connection failed")

    rows = records(boundary)
    assert len(rows) == 1
    msg = rows[0]["message"]
    assert secret_pass not in msg, f"Database password leaked in connection error: {msg}"
    assert "[REDACTED]" in msg
    assert "postgres:5432/insurance_db" in msg
    assert secret_pass not in stream.getvalue()


@pytest.mark.asyncio
async def test_concurrent_turns_isolate_profile_snapshots_and_scrubbing(logs) -> None:
    """Concurrent turns running simultaneously keep isolated TurnCorrelation contexts."""
    boundary, stream = logs
    alice_name = "Alice Wonderland"
    alice_phone = "+919876543211"
    bob_name = "Bob Builder"
    bob_phone = "+919876543222"

    async def turn_one() -> None:
        with correlation_scope("turn-1") as turn, node_scope("node-1"):
            turn.profile_snapshot = {"name": alice_name, "phone": alice_phone}
            await asyncio.sleep(0.02)
            try:
                raise RuntimeError(f"Turn 1 failure for {alice_name} phone {alice_phone}")
            except RuntimeError:
                logging.getLogger("app.test_exception_log").exception("Error in turn 1")

    async def turn_two() -> None:
        with correlation_scope("turn-2") as turn, node_scope("node-2"):
            turn.profile_snapshot = {"name": bob_name, "phone": bob_phone}
            await asyncio.sleep(0.02)
            try:
                raise RuntimeError(f"Turn 2 failure for {bob_name} phone {bob_phone}")
            except RuntimeError:
                logging.getLogger("app.test_exception_log").exception("Error in turn 2")

    await asyncio.gather(turn_one(), turn_two())

    assert current_turn.get() is None

    rows = records(boundary)
    assert len(rows) == 2

    row_1 = next(r for r in rows if r["node"] == "node-1")
    row_2 = next(r for r in rows if r["node"] == "node-2")

    # In turn 1, Alice's values must be scrubbed, and Bob's values must never appear
    assert alice_name not in row_1["message"]
    assert alice_phone not in row_1["message"]
    assert bob_name not in row_1["message"]
    assert bob_phone not in row_1["message"]

    # In turn 2, Bob's values must be scrubbed, and Alice's values must never appear
    assert bob_name not in row_2["message"]
    assert bob_phone not in row_2["message"]
    assert alice_name not in row_2["message"]
    assert alice_phone not in row_2["message"]
