"""Runtime namespaces and fail-closed production graph selection."""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.v1.message import get_app_graph
from app.graph.runtime import turn_config


def test_namespaces_bind_exact_issuer_canonical_session_and_turn():
    session, turn = str(uuid.uuid4()), uuid.uuid4()
    first = turn_config("https://issuer.test", session, turn)
    assert first == turn_config("https://issuer.test", session.upper(), turn)
    assert first != turn_config("https://other.test", session, turn)
    assert first != turn_config("https://issuer.test", session, uuid.uuid4())
    assert first != turn_config("https://issuer.test", str(uuid.uuid4()), turn)


def test_production_runtime_never_falls_back_to_in_memory_graph():
    with (
        patch("app.api.v1.message.get_settings", return_value=SimpleNamespace(
            environment="production")),
        patch("app.api.v1.message._production_graph", None),
        pytest.raises(HTTPException) as unavailable,
    ):
        get_app_graph()
    assert unavailable.value.status_code == 503
