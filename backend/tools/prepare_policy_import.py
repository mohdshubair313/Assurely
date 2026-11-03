"""Produce an offline normalized draft and blocked import preview from pinned PDFs."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.policy_rule_draft import assess_draft, build_draft  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--source", required=True, action="append", metavar="ID=PDF_PATH")
    parser.add_argument("--as-of", required=True, type=date.fromisoformat)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    sources: dict[str, bytes] = {}
    for item in args.source:
        key, separator, path = item.partition("=")
        if not separator or not key or not path or key in sources:
            parser.error("Each source requires a unique ID=PDF_PATH")
        with Path(path).open("rb") as stream:
            content = stream.read(20 * 1024 * 1024 + 1)
        if len(content) > 20 * 1024 * 1024:
            parser.error("PDF exceeds 20 MiB")
        sources[key] = content
    draft = build_draft(args.package.read_text(encoding="utf-8"), sources, as_of=args.as_of)
    raw = draft.model_dump_json()
    preview = assess_draft(raw, sources, as_of=args.as_of)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump({"draft": json.loads(raw), "import_preview": preview}, stream, indent=2)
        stream.write("\n")
    print(json.dumps({
        "output": str(args.output), "proposed_fields": len(preview["proposed_fields"]),
        "unavailable_fields": preview["unavailable_fields"],
        "interpretation_required": preview["interpretation_required"],
        "draft_sha256": preview["draft_sha256"], "approved_for_import": False,
    }))


if __name__ == "__main__":
    main()
