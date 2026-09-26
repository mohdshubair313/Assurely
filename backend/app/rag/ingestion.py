"""Document ingestion — chunks and indexes policy documents into the vector store.

Handles:
  - PDF and HTML document parsing
  - Chunking with overlap for retrieval quality
  - Metadata extraction (insurer, product, version_hash, page/section refs)
  - Embedding generation
  - Upsert into the vector store (Chroma)

All documents pass through ingestion_screening BEFORE reaching
the vector store (distributed guardrail — AGENTS.md rule 3).

Phase 1: manual ingestion of 3–4 real health policy documents.
Automated scraping is deferred.
"""
