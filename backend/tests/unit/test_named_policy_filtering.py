"""Policy scope must hold across Chroma, empty results and local fallback."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.graph.nodes.health_domain_agent import health_domain_agent_node
from app.graph.state import create_initial_state
from app.rag.retriever import retrieve_health_facts
from app.rag.vector_store import PolicyVectorStore, _matching_products


@pytest.mark.parametrize(
    "query,expected",
    [
        ("HDFC OPTIMA-SECURE waiting periods", ["Optima Secure"]),
        ("Compare Optima Secure and Care Supreme", ["Care Supreme", "Optima Secure"]),
        ("Optima Securely is not a complete product name", []),
        ("General hospitalization cover", []),
        ("Optima Secure Plus waiting periods", ["Optima Secure Plus"]),
        (
            "Compare Optima Secure and Optima Secure Plus",
            ["Optima Secure", "Optima Secure Plus"],
        ),
    ],
)
def test_complete_product_names_are_resolved(query: str, expected: list[str]) -> None:
    metadata: list[dict[str, Any] | None] = [
        {"product_name": "Optima Secure"},
        {"product_name": "Care Supreme"},
        {"product_name": "Optima Secure Plus"},
        {"product_name": None},
        None,
    ]
    assert _matching_products(query, metadata) == expected


def _store() -> tuple[PolicyVectorStore, MagicMock]:
    with patch.object(PolicyVectorStore, "_init_chroma"):
        store = PolicyVectorStore()
    collection = MagicMock()
    collection.count.return_value = 9
    collection.get.return_value = {
        "metadatas": [
            {"product_name": "Optima Secure"},
            {"product_name": "Care Supreme"},
            {"product_name": "Health AdvantEdge"},
        ]
    }
    empty_query: dict[str, Any] = {"documents": [[]], "metadatas": [[]]}
    collection.query.return_value = empty_query
    store._collection = collection
    return store, collection


def test_chroma_filter_uses_requested_products_before_similarity_search() -> None:
    store, collection = _store()
    store.similarity_search("Optima Secure and Care Supreme waiting periods", top_k=2)
    assert collection.query.call_args.kwargs["where"] == {
        "product_name": {"$in": ["Care Supreme", "Optima Secure"]}
    }


def test_generic_question_has_no_product_filter() -> None:
    store, collection = _store()
    store.similarity_search("hospitalization room rent", top_k=2)
    assert "where" not in collection.query.call_args.kwargs


def test_profile_query_keeps_product_from_user_request() -> None:
    store, collection = _store()
    store.similarity_search("hospitalization room rent", scope_query="Explain Optima Secure cover")
    assert collection.query.call_args.kwargs["where"] == {
        "product_name": {"$in": ["Optima Secure"]}
    }


def test_scoped_empty_result_does_not_substitute_seeded_clauses() -> None:
    store, _ = _store()
    assert store.similarity_search("Optima Secure waiting period") == []


def test_out_of_scope_backend_result_is_rejected() -> None:
    store, collection = _store()
    collection.query.return_value = {
        "documents": [["Unrelated insurer clause"]],
        "metadatas": [[{"product_name": "Health AdvantEdge", "source": "ICICI fixture"}]],
    }
    assert store.similarity_search("Optima Secure waiting period") == []


def test_fallback_contains_only_requested_policy() -> None:
    store, _ = _store()
    store._collection = None
    result = store.similarity_search("Optima Secure waiting period", top_k=10)
    assert result
    assert all("HDFC ERGO Optima Secure" in fact["source"] for fact in result)


def test_query_failure_does_not_broaden_to_another_policy() -> None:
    store, collection = _store()
    collection.query.side_effect = ConnectionError("Synthetic Chroma query failure")
    # This indexed policy is absent from the local fallback corpus.
    assert store.similarity_search("Health AdvantEdge waiting period") == []


def test_catalog_failure_does_not_search_without_scope() -> None:
    store, collection = _store()
    collection.get.side_effect = ConnectionError("Synthetic catalog failure")
    assert store.similarity_search("Health AdvantEdge waiting period") == []
    collection.query.assert_not_called()


def test_retriever_forwards_policy_context() -> None:
    store = MagicMock()
    empty_facts: list[dict[str, Any]] = []
    store.similarity_search.return_value = empty_facts
    with patch("app.rag.retriever.get_vector_store", return_value=store):
        retrieve_health_facts("room rent", scope_query="Optima Secure")
    store.similarity_search.assert_called_once_with(
        query="room rent", top_k=3, scope_query="Optima Secure"
    )


@pytest.mark.asyncio
async def test_current_policy_question_discards_previous_turn_facts() -> None:
    question = "What is Optima Secure's waiting period?"
    state = create_initial_state("changed-policy", question)
    state["retrieved_facts"] = [{"source": "ICICI fixture", "claim": "Prior turn clause"}]
    current = {"source": "HDFC fixture", "claim": "Current turn clause"}
    with patch("app.graph.nodes.health_domain_agent.retrieve_health_facts", return_value=[current]):
        result = await health_domain_agent_node(state)
    assert result["retrieved_facts"] == [current]


@pytest.mark.asyncio
async def test_named_nonwaiting_request_scopes_general_profile_query() -> None:
    question = "Explain Optima Secure's room rent limits."
    state = create_initial_state("named-room", question)
    with patch(
        "app.graph.nodes.health_domain_agent.retrieve_health_facts", return_value=[]
    ) as retrieve:
        await health_domain_agent_node(state)
    retrieve.assert_called_once_with(
        query="hospitalization room rent single private room restoration recharge",
        top_k=2,
        scope_query=question,
    )
