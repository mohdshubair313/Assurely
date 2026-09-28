"""Content-free request identifiers shared by logging, tracing and persistence."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

SESSION_NAMESPACE = uuid.UUID("3c8b8c8f-a4c5-4b19-9ec8-413f5a11c92e")


def database_session_id(value: str) -> uuid.UUID:
    """Use the existing database mapping; never log arbitrary caller ID text."""
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        return uuid.uuid5(SESSION_NAMESPACE, value)


@dataclass
class TurnCorrelation:
    session_id: str | None = None
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    decision_trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # Keep exception objects alive for the turn so Python cannot reuse their IDs.
    errors: list[tuple[BaseException, str, str]] = field(default_factory=list, repr=False)
    # Known profile values for PII scrubbing in exception messages.
    profile_snapshot: dict[str, object] | None = field(default=None, repr=False)

    def identifiers(self) -> dict[str, str | None]:
        return {
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "decision_trace_id": self.decision_trace_id if self.session_id else None,
        }


current_turn: ContextVar[TurnCorrelation | None] = ContextVar("turn_correlation", default=None)
current_node: ContextVar[str] = ContextVar("node_correlation", default="api")


@contextmanager
def correlation_scope(session_id: str | None = None) -> Iterator[TurnCorrelation]:
    turn = TurnCorrelation(
        session_id=str(database_session_id(session_id)) if session_id else None
    )
    token = current_turn.set(turn)
    try:
        yield turn
    finally:
        current_turn.reset(token)


@contextmanager
def node_scope(name: str) -> Iterator[None]:
    token = current_node.set(name)
    try:
        yield
    finally:
        current_node.reset(token)
