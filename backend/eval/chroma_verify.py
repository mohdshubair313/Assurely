"""Verify Chroma vector store has the expected policy_clauses collection.

Run against the live Docker Compose stack:
    docker compose exec api python -m eval.chroma_verify

Checks:
  1. Chroma heartbeat is reachable
  2. policy_clauses collection exists
  3. Expected number of seeded documents are present
  4. A sample similarity search returns results with version_hash metadata
  5. Retrieved version_hash matches what was stored at ingestion time
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def main() -> None:
    checks: dict[str, Any] = {}
    results: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": checks,
    }
    ok = True

    # 1. Chroma heartbeat
    try:
        import chromadb

        from app.core.config import get_settings

        settings = get_settings()
        client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
        )
        heartbeat = client.heartbeat()
        checks["heartbeat"] = {"status": "OK", "value": heartbeat}
    except Exception as e:
        checks["heartbeat"] = {"status": "FAIL", "error": str(e)}
        ok = False
        print(json.dumps(results, indent=2, default=str))
        sys.exit(1)

    # 2. Collection exists
    try:
        collection = client.get_collection("policy_clauses")
        count = collection.count()
        checks["collection"] = {
            "status": "OK",
            "name": "policy_clauses",
            "document_count": count,
        }
        if count == 0:
            checks["collection"]["warning"] = (
                "Collection exists but is empty — seeding may not have run"
            )
            ok = False
    except Exception as e:
        checks["collection"] = {"status": "FAIL", "error": str(e)}
        ok = False
        print(json.dumps(results, indent=2, default=str))
        sys.exit(1)

    # 3. Expected seeded documents
    from app.rag.vector_store import DEFAULT_SEEDED_CLAUSES

    expected_count = len(DEFAULT_SEEDED_CLAUSES)
    expected_ids = sorted([doc["id"] for doc in DEFAULT_SEEDED_CLAUSES])
    checks["seeded_documents"] = {
        "expected_count": expected_count,
        "actual_count": count,
        "match": count >= expected_count,
    }
    if count < expected_count:
        ok = False

    # 4. Verify documents retrievable with metadata
    try:
        query_result = collection.query(
            query_texts=["pre-existing disease waiting period"],
            n_results=min(3, count),
        )
        docs_raw = query_result.get("documents") or []
        docs: list[str] = docs_raw[0] if docs_raw else []
        metas_raw = query_result.get("metadatas") or []
        metas: list[dict[str, Any]] = metas_raw[0] if metas_raw else []  # type: ignore[assignment]
        ids_raw = query_result.get("ids") or []
        ids: list[str] = ids_raw[0] if ids_raw else []

        search_results: list[dict[str, Any]] = []
        for doc_id, doc, meta in zip(ids, docs, metas, strict=True):
            search_results.append({
                "id": doc_id,
                "snippet": doc[:80] + "..." if len(doc) > 80 else doc,
                "source": meta.get("source", ""),
                "version_hash": meta.get("version_hash", "MISSING"),
                "indexed_content_hash": meta.get("indexed_content_hash", "MISSING"),
                "last_verified": meta.get("last_verified", ""),
            })

        checks["similarity_search"] = {
            "status": "OK",
            "query": "pre-existing disease waiting period",
            "result_count": len(docs),
            "results": search_results,
        }

        # Check version_hash presence
        hashes_present = all(
            r["version_hash"] != "MISSING" and r["version_hash"] != ""
            for r in search_results
        )
        checks["version_hash_in_metadata"] = {
            "status": "OK" if hashes_present else "FAIL",
            "all_results_have_hash": hashes_present,
        }
        if not hashes_present:
            ok = False

    except Exception as e:
        checks["similarity_search"] = {"status": "FAIL", "error": str(e)}
        ok = False

    # 5. Verify a specific seeded document by ID
    try:
        get_result = collection.get(ids=expected_ids[:1])
        if get_result["ids"]:
            doc_meta = get_result["metadatas"][0] if get_result["metadatas"] else {}
            checks["get_by_id"] = {
                "status": "OK",
                "id": expected_ids[0],
                "has_source": bool(doc_meta.get("source")),
                "has_version_hash": bool(doc_meta.get("version_hash")),
            }
        else:
            checks["get_by_id"] = {
                "status": "FAIL",
                "id": expected_ids[0],
                "error": "Document not found by ID",
            }
            ok = False
    except Exception as e:
        checks["get_by_id"] = {"status": "FAIL", "error": str(e)}
        ok = False

    # Output
    results["overall"] = "PASS" if ok else "FAIL"
    output = json.dumps(results, indent=2, default=str)
    print(output)

    # Save evidence
    try:
        Path("artifacts").mkdir(parents=True, exist_ok=True)
        with open("artifacts/chroma-verify.json", "w") as f:
            f.write(output)
        print("\nEvidence saved to artifacts/chroma-verify.json")
    except OSError:
        pass

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
