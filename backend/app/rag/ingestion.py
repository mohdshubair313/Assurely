"""Document ingestion — screens, chunks, and indexes policy documents into the vector store.

All documents pass through ingestion_screening BEFORE reaching
the vector store (distributed guardrail — AGENTS.md rule 3).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.rag.ingestion_screening import (
    ScreeningOutcome,
    ScreeningResult,
    get_quarantine_store,
    screen_document,
)
from app.rag.vector_store import get_vector_store

logger = logging.getLogger(__name__)


def ingest_document(
    content: str | bytes,
    source_url: str,
    metadata: dict[str, Any] | None = None,
    doc_id: str | None = None,
) -> ScreeningResult:
    """Ingest a policy document into the vector store through the screening gate.

    1. Executes deterministic screening (domain allowlist, PDF active content,
       hidden text, instruction injection, ranking language).
    2. If QUARANTINE:
       - Records in QuarantineStore for human reviewer queue.
       - Does NOT touch the vector store.
       - Returns ScreeningResult(outcome=QUARANTINE, ...).
    3. If ADMIT:
       - Calls vector_store.add(...) with the verified ScreeningResult.
       - Returns ScreeningResult(outcome=ADMIT, ...).
    """
    meta = dict(metadata or {})
    screening_result = screen_document(content=content, source_url=source_url, metadata=meta)

    if screening_result.outcome == ScreeningOutcome.QUARANTINE:
        quarantine_store = get_quarantine_store()
        quarantine_store.add_quarantine(screening_result, content)
        logger.warning(
            "Ingestion blocked: document quarantined (hash=%s, source=%s, reasons=%s)",
            screening_result.version_hash[:12],
            source_url,
            screening_result.reasons,
        )
        return screening_result

    # ADMIT: add to vector store
    vector_store = get_vector_store()
    assigned_id = doc_id or f"doc-{uuid.uuid4()}"
    text_content = (
        content if isinstance(content, str) else content.decode("utf-8", errors="replace")
    )

    vector_store.add(
        documents=[text_content],
        metadatas=[meta],
        ids=[assigned_id],
        screening_results=[screening_result],
    )
    logger.info(
        "Ingestion successful: document admitted and indexed (id=%s, hash=%s, source=%s)",
        assigned_id,
        screening_result.version_hash[:12],
        source_url,
    )
    return screening_result
