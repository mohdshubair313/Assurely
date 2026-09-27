"""Missing source evidence must remain visible to the existing guardrail."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.graph.nodes.guardrail import check_provenance_and_citations
from app.rag.retriever import retrieve_health_facts
from app.rag.vector_store import PolicyVectorStore


@pytest.mark.parametrize("metadata", [{}, {"source": None, "last_verified": None}])
def test_retrieval_preserves_missing_provenance(metadata: dict[str, Any]) -> None:
    store = MagicMock()
    store.similarity_search.return_value = [{"claim": "Synthetic clause", **metadata}]
    with patch("app.rag.retriever.get_vector_store", return_value=store):
        facts = retrieve_health_facts("synthetic")
    assert facts[0]["source"] == ""
    assert facts[0]["last_verified"] == ""
    assert check_provenance_and_citations({"cited_facts": facts}, [])


def test_vector_query_does_not_invent_source_or_verification_date() -> None:
    with patch.object(PolicyVectorStore, "_init_chroma"):
        store = PolicyVectorStore()
    collection = MagicMock()
    collection.count.return_value = 1
    collection.query.return_value = {"documents": [["Synthetic clause"]], "metadatas": [[{}]]}
    store._collection = collection
    facts = store.similarity_search("synthetic")
    assert facts[0]["source"] == ""
    assert facts[0]["last_verified"] == ""
