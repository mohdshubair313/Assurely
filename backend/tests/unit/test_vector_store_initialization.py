"""Existing clause collections must be opened without creation metadata."""

from unittest.mock import MagicMock, patch

import chromadb.errors
import pytest

from app.rag.vector_store import PolicyVectorStore


def test_existing_collection_is_opened_without_creation_metadata() -> None:
    client = MagicMock()
    client.get_collection.return_value.count.return_value = 9
    with patch("chromadb.HttpClient", return_value=client):
        store = PolicyVectorStore()
    assert store._collection is client.get_collection.return_value
    client.get_collection.assert_called_once_with(name="policy_clauses")
    client.get_or_create_collection.assert_not_called()
    client.create_collection.assert_not_called()
    store._collection.add.assert_not_called()


class LegacyMissingCollectionError(Exception):
    """The missing-collection exception used by Chroma 0.6 clients."""


@pytest.mark.parametrize(
    "error_type", [LegacyMissingCollectionError, chromadb.errors.NotFoundError]
)
def test_missing_collection_is_created_and_seeded(error_type: type[Exception]) -> None:
    client = MagicMock()
    client.get_collection.side_effect = error_type("Missing fixture collection")
    client.create_collection.return_value.count.return_value = 0
    with (
        patch("chromadb.HttpClient", return_value=client),
        patch.object(
            chromadb.errors, "InvalidCollectionException", LegacyMissingCollectionError, create=True
        ),
        patch.object(PolicyVectorStore, "_seed_default_clauses") as seed,
    ):
        store = PolicyVectorStore()
    assert store._collection is client.create_collection.return_value
    client.create_collection.assert_called_once_with(
        name="policy_clauses", metadata={"hnsw:space": "cosine"}
    )
    seed.assert_called_once_with()


def test_connection_failure_does_not_create_replacement_collection() -> None:
    client = MagicMock()
    client.get_collection.side_effect = ConnectionError("Synthetic connection failure")
    with patch("chromadb.HttpClient", return_value=client):
        store = PolicyVectorStore()
    assert store._collection is None
    client.create_collection.assert_not_called()
