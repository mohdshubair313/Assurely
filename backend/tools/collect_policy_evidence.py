"""Collect bounded passages from pinned PDFs for offline human review.

This command never imports terms, computes quotes, or approves sources. It keeps
page boundaries and complete intermediate pages so conditions survive extraction.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from datetime import date
from pathlib import Path
from typing import Any

from pypdf import PdfReader


def _unique_anchor(text: str, anchor: str) -> int:
    if not anchor or text.count(anchor) != 1:
        raise ValueError(f"Expected one exact boundary anchor: {anchor!r}")
    return text.index(anchor)


def collect(plan: dict[str, Any], files: dict[str, Path]) -> list[dict[str, Any]]:
    """Return source slices; no interpretation of the extracted policy wording."""
    source_ids = [source["id"] for source in plan["sources"]]
    if len(set(source_ids)) != len(source_ids) or set(files) != set(source_ids):
        raise ValueError("Provide each declared source exactly once")
    readers: dict[str, PdfReader] = {}
    pages: dict[tuple[str, int], str] = {}
    for source in plan["sources"]:
        with files[source["id"]].open("rb") as stream:
            content = stream.read(20 * 1024 * 1024 + 1)
        if len(content) > 20 * 1024 * 1024 or not content.startswith(b"%PDF-"):
            raise ValueError("Expected PDF source no larger than 20 MiB")
        if hashlib.sha256(content).hexdigest() != source["sha256"]:
            raise ValueError(f"Source hash mismatch: {source['id']}")
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("Source requires a private read password")
        if len(reader.pages) != source["page_count"]:
            raise ValueError(f"Source page-count mismatch: {source['id']}")
        readers[source["id"]] = reader

    results: list[dict[str, Any]] = []
    section_ids: set[str] = set()
    for section in plan["sections"]:
        section_id = section["id"]
        if section_id in section_ids:
            raise ValueError(f"Duplicate section id: {section_id}")
        section_ids.add(section_id)
        source_id = section["source_id"]
        first, last = section["first_page"], section["last_page"]
        if source_id not in readers:
            raise ValueError(f"Unknown source: {source_id}")
        if (
            type(first) is not int
            or type(last) is not int
            or not 1 <= first <= last <= len(readers[source_id].pages)
        ):
            raise ValueError(f"Invalid physical page range: {section_id}")
        fragments = []
        for number in range(first, last + 1):
            key = (source_id, number)
            if key not in pages:
                pages[key] = readers[source_id].pages[number - 1].extract_text()
            original = pages[key]
            start = _unique_anchor(original, section["start"]) if number == first else 0
            end = (
                _unique_anchor(original, section["end"])
                if number == last and section.get("end")
                else len(original)
            )
            if end <= start or not original[start:end].strip():
                raise ValueError(f"Empty or reversed section boundary: {section_id}")
            quote = original[start:end]
            fragments.append(
                {
                    "source_id": source_id,
                    "pdf_page": number,
                    "start_character": start,
                    "end_character": end,
                    "quote": quote,
                    "text_sha256": hashlib.sha256(quote.encode()).hexdigest(),
                }
            )
        results.append(
            {
                "id": section_id,
                "purpose": section["purpose"],
                "fragments": fragments,
                "unresolved": section.get("unresolved", []),
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--source", action="append", required=True, metavar="ID=PDF_PATH")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--extracted-on", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    files: dict[str, Path] = {}
    for item in args.source:
        source_id, separator, path = item.partition("=")
        if not separator or not source_id or not path or source_id in files:
            parser.error("Each source requires a unique ID=PDF_PATH")
        files[source_id] = Path(path)
    raw_plan = args.plan.read_bytes()
    plan = json.loads(raw_plan)
    sections = collect(plan, files)
    output = {
        "purpose": "offline_source_passages_for_review",
        "plan_sha256": hashlib.sha256(raw_plan).hexdigest(),
        "extracted_on": args.extracted_on.isoformat(),
        "product_uin": plan["product_uin"],
        "variant": plan["variant"],
        "sources": plan["sources"],
        "sections": sections,
        "review_status": "pending_human_review",
        "approved_for_import": False,
        "production_approved": False,
        "limitations": [
            "Exact text slices preserve source conditions, not verified interpretations.",
            "Intermediate pages retain source headers and footers.",
            "PDF table reading order may differ from the visible layout.",
            "Source applicability and contract overrides require independent review.",
        ],
    }
    # An existing receipt must remain immutable; use a new output name for a revision.
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(output, stream, indent=2, ensure_ascii=True)
        stream.write("\n")
    print(
        json.dumps(
            {
                "sections": len(sections),
                "page_fragments": sum(len(s["fragments"]) for s in sections),
                "output": str(args.output),
                "approved_for_import": False,
            }
        )
    )


if __name__ == "__main__":
    main()
