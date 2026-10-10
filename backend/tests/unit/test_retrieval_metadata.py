"""Missing source evidence must remain visible to the existing guardrail.

Also verifies that version_hash propagates through the retrieval chain
from vector store metadata → retriever → persist_memory sources_per_claim.
"""

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
    empty_meta: dict[str, Any] = {}
    collection.query.return_value = {
        "documents": [["Synthetic clause"]],
        "metadatas": [[empty_meta]],
    }
    store._collection = collection
    facts = store.similarity_search("synthetic")
    assert facts[0]["source"] == ""
    assert facts[0]["last_verified"] == ""


# ── Version-hash propagation tests (Finding 6) ──────────────────────────────


FAKE_HASH = "abc123def456"
FAKE_IDX_HASH = "idx789ghi012"


def test_vector_store_chroma_propagates_version_hash() -> None:
    """Chroma search results include version_hash and indexed_content_hash."""
    with patch.object(PolicyVectorStore, "_init_chroma"):
        store = PolicyVectorStore()
    collection = MagicMock()
    collection.count.return_value = 1
    collection.query.return_value = {
        "documents": [["Some clause text"]],
        "metadatas": [[{
            "source": "Test Source",
            "url": "https://example.com",
            "last_verified": "2024-01-01",
            "version_hash": FAKE_HASH,
            "indexed_content_hash": FAKE_IDX_HASH,
        }]],
    }
    store._collection = collection
    results = store.similarity_search("test")
    assert results[0]["version_hash"] == FAKE_HASH
    assert results[0]["indexed_content_hash"] == FAKE_IDX_HASH


def test_vector_store_fallback_propagates_version_hash() -> None:
    """In-memory fallback search results include version_hash."""
    with patch.object(PolicyVectorStore, "_init_chroma"):
        store = PolicyVectorStore()
    store._collection = None  # Force fallback
    store._fallback_docs = [{
        "id": "test-doc",
        "content": "Coverage clause text",
        "insurer": "Test",
        "product_name": "Test Policy",
        "uin": "TEST123",
        "section": "Section 1",
        "source": "Test Source",
        "url": "https://example.com",
        "last_verified": "2024-01-01",
        "version_hash": FAKE_HASH,
        "indexed_content_hash": FAKE_IDX_HASH,
        "retrieved_at": "",
    }]
    results = store.similarity_search("coverage")
    assert results[0]["version_hash"] == FAKE_HASH
    assert results[0]["indexed_content_hash"] == FAKE_IDX_HASH


def test_retriever_passes_version_hash_through() -> None:
    """retrieve_health_facts preserves version_hash from vector store."""
    store = MagicMock()
    store.similarity_search.return_value = [{
        "claim": "PED waiting period clause",
        "source": "HDFC ERGO Policy",
        "url": "https://hdfcergo.com/test.pdf",
        "last_verified": "2024-01-01",
        "retrieved_at": "2026-10-01T00:00:00Z",
        "version_hash": FAKE_HASH,
        "indexed_content_hash": FAKE_IDX_HASH,
    }]
    with patch("app.rag.retriever.get_vector_store", return_value=store):
        facts = retrieve_health_facts("pre-existing disease")
    assert facts[0]["version_hash"] == FAKE_HASH
    assert facts[0]["indexed_content_hash"] == FAKE_IDX_HASH


def test_persist_memory_sources_include_version_hash() -> None:
    """sources_per_claim in decision trace must contain version_hash."""
    from app.graph.nodes.persist_memory import _sources_per_claim

    fake_state: dict[str, Any] = {
        "retrieved_facts": [{
            "claim": "36-month PED waiting period",
            "source": "HDFC ERGO Optima Secure Section 4.2",
            "url": "https://hdfcergo.com/test.pdf",
            "last_verified": "2024-01-01",
            "retrieved_at": "2026-10-01T00:00:00Z",
            "version_hash": FAKE_HASH,
        }],
        "draft_output": {},
        "hidden_clauses": [],
    }
    sources = _sources_per_claim(fake_state)  # type: ignore[arg-type]
    claim_sources = sources["36-month PED waiting period"]
    assert len(claim_sources) == 1
    assert claim_sources[0]["version_hash"] == FAKE_HASH


def test_persist_memory_sources_omit_absent_hash() -> None:
    """Claims without version_hash should still work without KeyError."""
    from app.graph.nodes.persist_memory import _sources_per_claim

    fake_state: dict[str, Any] = {
        "retrieved_facts": [{
            "claim": "Room rent clause",
            "source": "Test Source",
            "url": "https://example.com",
            "last_verified": "2024-01-01",
            "retrieved_at": "2026-10-01T00:00:00Z",
        }],
        "draft_output": {},
        "hidden_clauses": [],
    }
    sources = _sources_per_claim(fake_state)  # type: ignore[arg-type]
    claim_sources = sources["Room rent clause"]
    assert "version_hash" not in claim_sources[0]
