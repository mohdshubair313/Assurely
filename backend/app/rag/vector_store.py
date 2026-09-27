"""Vector store interface — wraps ChromaDB for document storage and retrieval.

Provides a clean abstraction over the vector DB so we can swap
Chroma for pgvector or Qdrant if we outgrow it (per HLD/LLD § 4).

Features:
  - Similarity search for policy clause wording and conditions.
  - Every chunk carries citation metadata: insurer, product_name, UIN,
    section/clause, last_verified, source_url.
  - Robust offline / in-memory fallback for local unit tests.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Standard seeded clauses from verified insurer filings
DEFAULT_SEEDED_CLAUSES: list[dict[str, Any]] = [
    {
        "id": "hdfc-optima-secure-benefit",
        "insurer": "HDFC ERGO General Insurance",
        "product_name": "Optima Secure",
        "uin": "HDFHLIP21557V022021",
        "section": "Section 3.1 — 4X Coverage Benefit",
        "content": (
            "Under the Secure Benefit, the base sum insured doubles to 2X from day 1 "
            "for hospitalization. Plus Benefit adds 50% per claim-free year up to 100%, "
            "and Restore Benefit provides 100% instant recharge."
        ),
        "source": "HDFC ERGO Optima Secure Policy Wording Section 3.1 (UIN: HDFHLIP21557V022021)",
        "url": "https://www.hdfcergo.com/policy-wordings/optima-secure.pdf",
        "last_verified": "2024-01-01",
    },
    {
        "id": "hdfc-optima-waiting-period",
        "insurer": "HDFC ERGO General Insurance",
        "product_name": "Optima Secure",
        "uin": "HDFHLIP21557V022021",
        "section": "Section 4.2 — Waiting Periods",
        "content": (
            "Initial waiting period of 30 days applies for any illness except accident. "
            "Pre-existing disease (PED) waiting period is 36 months of continuous coverage. "
            "Specific named ailments carry a 24-month waiting period."
        ),
        "source": "HDFC ERGO Optima Secure Policy Wording Section 4.2 (UIN: HDFHLIP21557V022021)",
        "url": "https://www.hdfcergo.com/policy-wordings/optima-secure.pdf",
        "last_verified": "2024-01-01",
    },
    {
        "id": "hdfc-optima-room-rent",
        "insurer": "HDFC ERGO General Insurance",
        "product_name": "Optima Secure",
        "uin": "HDFHLIP21557V022021",
        "section": "Section 2.4 — Room Rent Limits",
        "content": (
            "No room rent capping or proportionate deduction applies across any sum insured tier. "
            "Covered up to Single Private A/C Room without co-payment."
        ),
        "source": "HDFC ERGO Optima Secure Policy Wording Section 2.4 (UIN: HDFHLIP21557V022021)",
        "url": "https://www.hdfcergo.com/policy-wordings/optima-secure.pdf",
        "last_verified": "2024-01-01",
    },
    {
        "id": "care-supreme-unlimited-recharge",
        "insurer": "Care Health Insurance",
        "product_name": "Care Supreme",
        "uin": "CHIHLIP22158V012122",
        "section": "Section 2.1 — Unlimited Automatic Recharge",
        "content": (
            "Provides unlimited automatic restoration of sum insured "
            "for same or different illnesses "
            "during the policy year upon exhaustion of base sum insured."
        ),
        "source": "Care Supreme Policy Wording Section 2.1 (UIN: CHIHLIP22158V012122)",
        "url": "https://www.careinsurance.com/policy-wordings/care-supreme.pdf",
        "last_verified": "2024-01-01",
    },
    {
        "id": "care-supreme-cumulative-bonus",
        "insurer": "Care Health Insurance",
        "product_name": "Care Supreme",
        "uin": "CHIHLIP22158V012122",
        "section": "Section 3.3 — Cumulative Bonus Booster",
        "content": (
            "50% increase in base sum insured for every claim-free year up to a maximum of 100% "
            "without reduction on claims."
        ),
        "source": "Care Supreme Policy Wording Section 3.3 (UIN: CHIHLIP22158V012122)",
        "url": "https://www.careinsurance.com/policy-wordings/care-supreme.pdf",
        "last_verified": "2024-01-01",
    },
    {
        "id": "star-comprehensive-hospitalization",
        "insurer": "Star Health and Allied Insurance",
        "product_name": "Star Comprehensive",
        "uin": "SHAHLIP21254V052021",
        "section": "Section B.1 — Inpatient & Day Care Cover",
        "content": (
            "Covers in-patient hospitalization expenses, pre-hospitalization (60 days), "
            "post-hospitalization (90 days), daycare procedures, and maternity delivery expenses "
            "subject to a 24-month waiting period."
        ),
        "source": "Star Health Comprehensive Policy Wording Section B.1 (UIN: SHAHLIP21254V052021)",
        "url": "https://www.starhealth.in/policy-wordings/comprehensive.pdf",
        "last_verified": "2024-01-01",
    },
]


class PolicyVectorStore:
    """Interface to ChromaDB vector store with in-memory fallback."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: Any = None
        self._collection: Any = None
        self._fallback_docs: list[dict[str, Any]] = list(DEFAULT_SEEDED_CLAUSES)
        self._init_chroma()

    def _init_chroma(self) -> None:
        """Attempt to connect to ChromaDB container."""
        try:
            import chromadb

            self._client = chromadb.HttpClient(
                host=self.settings.chroma_host,
                port=self.settings.chroma_port,
            )
            self._collection = self._client.get_or_create_collection(
                name="policy_clauses",
                metadata={"hnsw:space": "cosine"},
            )
            # Seed default clauses if empty
            if self._collection.count() == 0:
                self._seed_default_clauses()
            logger.info(
                "Connected to ChromaDB at %s:%s",
                self.settings.chroma_host,
                self.settings.chroma_port,
            )
        except Exception as e:
            logger.warning("ChromaDB unavailable (%s); using in-memory clause store", e)
            self._client = None
            self._collection = None

    def _seed_default_clauses(self) -> None:
        """Seed the ChromaDB collection with initial policy clauses."""
        if not self._collection:
            return
        ids = [doc["id"] for doc in DEFAULT_SEEDED_CLAUSES]
        documents = [doc["content"] for doc in DEFAULT_SEEDED_CLAUSES]
        metadatas = [
            {
                "insurer": doc["insurer"],
                "product_name": doc["product_name"],
                "uin": doc["uin"],
                "section": doc["section"],
                "source": doc["source"],
                "url": doc["url"],
                "last_verified": doc["last_verified"],
            }
            for doc in DEFAULT_SEEDED_CLAUSES
        ]
        self._collection.add(ids=ids, documents=documents, metadatas=metadatas)

    def similarity_search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        """Search policy clauses relevant to the user's query or profile."""
        results: list[dict[str, Any]] = []

        if self._collection is not None:
            try:
                query_res = self._collection.query(
                    query_texts=[query],
                    n_results=min(top_k, self._collection.count()),
                )
                docs = query_res.get("documents", [[]])[0]
                metas = query_res.get("metadatas", [[]])[0]
                for doc, meta in zip(docs, metas, strict=True):
                    results.append(
                        {
                            "claim": doc,
                            "source": meta.get("source", ""),
                            "url": meta.get("url", ""),
                            "last_verified": meta.get("last_verified", ""),
                            "retrieved_at": datetime.now(UTC).isoformat(),
                        }
                    )
                if results:
                    return results
            except Exception as e:
                logger.warning(
                    "Chroma similarity query failed: %s; falling back to memory store", e
                )

        # In-memory keyword match fallback
        q_tokens = [w.lower() for w in query.split() if len(w) > 3]
        scored_docs: list[tuple[int, dict[str, Any]]] = []
        for doc in self._fallback_docs:
            content_lower = doc["content"].lower() + " " + doc["section"].lower()
            score = sum(1 for token in q_tokens if token in content_lower)
            scored_docs.append((score, doc))

        scored_docs.sort(key=lambda x: x[0], reverse=True)
        selected = [doc for _, doc in scored_docs[:top_k]]
        if not selected:
            selected = self._fallback_docs[:top_k]

        for item in selected:
            results.append(
                {
                    "claim": item["content"],
                    "source": item["source"],
                    "url": item["url"],
                    "last_verified": item["last_verified"],
                    "retrieved_at": datetime.now(UTC).isoformat(),
                }
            )
        return results


# Global singleton vector store instance
_vector_store_instance: PolicyVectorStore | None = None


def get_vector_store() -> PolicyVectorStore:
    """Return or initialize the singleton vector store instance."""
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = PolicyVectorStore()
    return _vector_store_instance
