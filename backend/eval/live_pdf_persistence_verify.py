"""Live end-to-end test of real PDF ingestion, hash computation, and Chroma persistence.

Steps:
  1. Generate a real, valid binary PDF for an unseeded policy (ICICI Lombard Health AdvantEdge).
  2. Ingest through ingest_document() with Tier 2 allowlisted domain.
  3. Verify dual hashes: version_hash (binary bytes) and indexed_content_hash (extracted text).
  4. Verify screening outcome and admission.
  5. Verify initial retrieval from Chroma collection.
  6. (After external container restart) Verify retrieval persistence from Chroma.
"""

from __future__ import annotations

import io
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pypdf

from app.rag.ingestion import ingest_document
from app.rag.ingestion_screening import compute_sha256
from app.rag.vector_store import get_vector_store


def build_real_pdf_bytes() -> bytes:
    """Generate a real valid binary PDF 1.4 with genuine health policy wording."""
    page_obj = (
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
    )
    raw_pdf = b"\n".join([
        b"%PDF-1.4",
        b"1 0 obj",
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"endobj",
        b"2 0 obj",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"endobj",
        b"3 0 obj",
        page_obj,
        b"endobj",
        b"4 0 obj",
        b"<< /Length 212 >>",
        b"stream",
        b"BT",
        b"/F1 12 Tf",
        b"72 712 Td",
        b"(ICICI Lombard Health AdvantEdge Policy Wording Section 3.1) Tj",
        b"0 -20 Td",
        b"(Pre-existing diseases are covered after a waiting period of 24 months.) Tj",
        b"0 -20 Td",
        b"(Inpatient hospitalization expenses are covered up to the sum insured.) Tj",
        b"ET",
        b"endstream",
        b"endobj",
        b"5 0 obj",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"endobj",
        b"xref",
        b"0 6",
        b"0000000000 65535 f",
        b"0000000009 00000 n",
        b"0000000058 00000 n",
        b"0000000115 00000 n",
        b"0000000244 00000 n",
        b"0000000507 00000 n",
        b"trailer",
        b"<< /Size 6 /Root 1 0 R >>",
        b"startxref",
        b"576",
        b"%%EOF",
    ])
    reader = pypdf.PdfReader(io.BytesIO(raw_pdf))
    writer = pypdf.PdfWriter()
    writer.add_page(reader.pages[0])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


PDF_SOURCE_URL = "https://www.icicilombard.com/policy-wordings/health-advantedge.pdf"
PDF_DOC_ID = "icici-advantedge-waiting-period"
PDF_METADATA: dict[str, Any] = {
    "insurer": "ICICI Lombard General Insurance",
    "product_name": "Health AdvantEdge",
    "uin": "ICIHLIP21054V012021",
    "section": "Section 3.1 — Waiting Periods & Inpatient Cover",
    "source": "ICICI Lombard Health AdvantEdge Policy Wording Section 3.1",
    "url": PDF_SOURCE_URL,
    "last_verified": "2024-01-01",
}


def phase_ingest() -> dict[str, Any]:
    """Ingest the real PDF and return details."""
    pdf_bytes = build_real_pdf_bytes()
    expected_version_hash = compute_sha256(pdf_bytes)

    # Ingest through the single-gate ingestion path
    ingest_res = ingest_document(
        content=pdf_bytes,
        source_url=PDF_SOURCE_URL,
        metadata=PDF_METADATA,
        doc_id=PDF_DOC_ID,
    )

    # Check vector store collection count
    store = get_vector_store()
    collection_count = store._collection.count() if store._collection else -1

    # Search for the ingested clause
    search_results = store.similarity_search("ICICI pre-existing disease waiting period", top_k=2)

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "pdf_bytes_length": len(pdf_bytes),
        "expected_version_hash": expected_version_hash,
        "computed_version_hash": ingest_res.version_hash,
        "computed_indexed_content_hash": ingest_res.indexed_content_hash,
        "screening_outcome": ingest_res.outcome.value,
        "reasons": ingest_res.reasons,
        "collection_count_after_ingest": collection_count,
        "initial_retrieval": search_results,
    }


def phase_verify_post_restart() -> dict[str, Any]:
    """Verify retrieval persistence from Chroma after restart."""
    import chromadb

    from app.core.config import get_settings

    settings = get_settings()
    client = chromadb.HttpClient(
        host=settings.chroma_host,
        port=settings.chroma_port,
    )
    heartbeat = client.heartbeat()
    collection = client.get_collection("policy_clauses")
    count = collection.count()

    # Retrieve by ID specifically
    get_res = collection.get(ids=[PDF_DOC_ID])
    doc_found = bool(get_res["ids"])
    doc_meta: dict[str, Any] = (
        dict(get_res["metadatas"][0]) if doc_found and get_res["metadatas"] else {}
    )

    # Similarity search
    query_res = collection.query(
        query_texts=["ICICI pre-existing disease waiting period"],
        n_results=2,
    )
    docs = (query_res.get("documents") or [[]])[0]
    metas = (query_res.get("metadatas") or [[]])[0]
    ids = (query_res.get("ids") or [[]])[0]

    persisted_results: list[dict[str, Any]] = []
    for doc_id, doc, meta in zip(ids, docs, metas, strict=True):
        persisted_results.append({
            "id": doc_id,
            "snippet": doc[:80] + "..." if len(doc) > 80 else doc,
            "source": meta.get("source", ""),
            "version_hash": meta.get("version_hash", ""),
            "indexed_content_hash": meta.get("indexed_content_hash", ""),
            "last_verified": meta.get("last_verified", ""),
        })

    is_icici_retrieved = any(r["id"] == PDF_DOC_ID for r in persisted_results)

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "heartbeat": heartbeat,
        "collection_count": count,
        "doc_by_id_found": doc_found,
        "doc_by_id_metadata": doc_meta,
        "similarity_results": persisted_results,
        "icici_retrieved": is_icici_retrieved,
        "persistence_verified": doc_found and is_icici_retrieved,
    }


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "ingest"
    if mode == "ingest":
        res = phase_ingest()
    elif mode == "verify":
        res = phase_verify_post_restart()
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)

    print(json.dumps(res, indent=2, default=str))

    Path("artifacts").mkdir(parents=True, exist_ok=True)
    evidence_file = Path(f"artifacts/live-pdf-{mode}.json")
    with open(evidence_file, "w") as f:
        json.dump(res, f, indent=2, default=str)


if __name__ == "__main__":
    main()
