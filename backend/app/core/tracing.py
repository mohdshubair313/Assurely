"""Privacy-conscious Langfuse tracing for API turns and graph operations.

The application sends health-related profile data to model providers. Trace
observations therefore record operation names, field counts, provider/model,
latency, token usage, and outcomes, but never message, prompt, profile, or report
content.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar, Token
from functools import lru_cache, wraps
from typing import Any, Protocol

from app.core.config import get_settings
from app.core.correlation import correlation_scope, current_turn, node_scope
from app.graph.state import SessionState

logger = logging.getLogger(__name__)

_active_trace: ContextVar[bool] = ContextVar("langfuse_active_trace", default=False)
_turn_llm_metadata: ContextVar[dict[str, list[str]] | None] = ContextVar(
    "turn_llm_metadata", default=None
)


def record_llm_metadata(
    provider: str, model: str, task_type: str, system_prompt: str | None
) -> None:
    """Retain non-content model/prompt identifiers for the current decision trace."""
    metadata = _turn_llm_metadata.get()
    if metadata is None:
        return
    model_id = f"{provider}:{model}"
    prompt_hash = hashlib.sha256((system_prompt or "").encode("utf-8")).hexdigest()[:12]
    prompt_id = f"{task_type}:{prompt_hash}"
    if model_id not in metadata["models"]:
        metadata["models"].append(model_id)
    if prompt_id not in metadata["prompts"]:
        metadata["prompts"].append(prompt_id)


def current_llm_metadata() -> dict[str, str | None]:
    """Return actual model IDs and task prompt versions used during this turn."""
    metadata = _turn_llm_metadata.get() or {"models": [], "prompts": []}
    return {
        "model_version": ",".join(metadata["models"])[:100] or None,
        "prompt_version": ",".join(metadata["prompts"])[:100] or None,
    }


class Observation(Protocol):
    """Small structural interface for a Langfuse observation wrapper."""

    def update(self, **kwargs: Any) -> Any: ...


@lru_cache(maxsize=1)
def _get_client() -> Any | None:
    """Create the process client only when both project keys are configured."""
    settings = get_settings()
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return None
    try:
        from langfuse import get_client

        return get_client()
    except Exception as exc:  # tracing must never break advisory requests
        logger.warning("Langfuse initialization failed; tracing disabled (%s)", type(exc).__name__)
        return None


@contextmanager
def observation(
    name: str,
    *,
    as_type: str = "span",
    input: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    model: str | None = None,
    model_parameters: dict[str, Any] | None = None,
    trace_context: dict[str, str] | None = None,
) -> Iterator[Observation | None]:
    """Create a nested observation when this request has an active trace."""
    if not _active_trace.get():
        yield None
        return

    client = _get_client()
    if client is None:
        yield None
        return

    error: Exception | None = None
    traceback = None
    with client.start_as_current_observation(
        as_type=as_type,
        name=name,
        input=input,
        metadata=metadata,
        model=model,
        model_parameters=model_parameters,
        trace_context=trace_context,
    ) as span:
        try:
            yield span
        except Exception as exc:
            # Keep provider/API error messages and tracebacks out of observability.
            span.update(level="ERROR", status_message=type(exc).__name__)
            error = exc
            traceback = exc.__traceback__

    if error is not None:
        raise error.with_traceback(traceback)


@contextmanager
def request_trace(session_id: str, *, message_char_count: int) -> Iterator[Observation | None]:
    """Start one trace per web-chat turn and group turns by app session ID."""
    context = current_turn.get()
    scope = nullcontext(context) if context else correlation_scope(session_id)
    with scope as turn:
        assert turn is not None
        with _request_trace(turn.identifiers(), message_char_count=message_char_count) as span:
            yield span


@contextmanager
def _request_trace(
    identifiers: dict[str, str | None], *, message_char_count: int
) -> Iterator[Observation | None]:
    settings = get_settings()
    client = _get_client()
    model_token = _turn_llm_metadata.set({"models": [], "prompts": []})
    if client is None:
        try:
            yield None
        finally:
            _turn_llm_metadata.reset(model_token)
        return

    from langfuse import propagate_attributes

    token: Token[bool] = _active_trace.set(True)
    try:
        with (
            propagate_attributes(
                session_id=identifiers["session_id"],
                trace_name="insurance-advisory-turn",
                tags=["web-chat", "phase-1"],
                environment=settings.environment,
                metadata={"route": "/v1/message"},
            ),
            observation(
                "insurance-advisory-turn",
                as_type="agent",
                input={"channel": "web-chat", "message_char_count": message_char_count},
                metadata={
                    "route": "/v1/message", "environment": settings.environment,
                    "decision_trace_id": identifiers["decision_trace_id"],
                },
                trace_context={"trace_id": str(identifiers["trace_id"])},
            ) as span,
        ):
            yield span
    finally:
        _active_trace.reset(token)
        _turn_llm_metadata.reset(model_token)


def trace_node(
    name: str,
    node: Callable[[SessionState], Awaitable[dict[str, Any]]],
) -> Any:
    """Wrap an existing async graph node without changing its state or routing."""

    @wraps(node)
    async def traced(state: SessionState) -> dict[str, Any]:
        turn = current_turn.get()
        if turn is not None and isinstance(state.get("user_profile"), dict):
            turn.profile_snapshot = state["user_profile"]
        with node_scope(name), observation(
            name,
            as_type="span",
            input={"state_fields": sorted(state.keys())},
            metadata={"operation": "graph-node"},
        ) as span:
            try:
                result = await node(state)
            except Exception:
                logger.exception("Graph node failed")
                raise
            if turn is not None and isinstance(result.get("user_profile"), dict):
                turn.profile_snapshot = result["user_profile"]
            if span is not None:
                safe_result: dict[str, Any] = {"result_fields": sorted(result.keys())}
                for field in ("intent", "approved", "escalation", "delivery_hold"):
                    value = result.get(field)
                    if isinstance(value, (str, bool, int, float)):
                        safe_result[field] = value
                if isinstance(result.get("missing_fields"), list):
                    safe_result["missing_field_count"] = len(result["missing_fields"])
                report = result.get("output")
                if isinstance(report, dict):
                    status = report.get("report_status")
                    if isinstance(status, str):
                        safe_result["report_status"] = status
                    if isinstance(report.get("evidence_count"), int):
                        safe_result["evidence_count"] = report["evidence_count"]
                    sentences = report.get("sentences")
                    if isinstance(sentences, list):
                        safe_result["report_sentence_count"] = len(sentences)
                span.update(output=safe_result)
                turn = current_turn.get()
                error_refs = [ref for _, ref, node_name in turn.errors if node_name == name] \
                    if turn else []
                if error_refs:
                    span.update(
                        level="ERROR", status_message="Exception content redacted",
                        metadata={"error_refs": error_refs},
                    )
            return result

    return traced


def flush_langfuse() -> None:
    """Flush queued telemetry during application shutdown, if initialized."""
    client = _get_client()
    if client is not None:
        client.flush()
