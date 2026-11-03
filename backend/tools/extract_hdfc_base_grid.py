"""Extract only the pinned Optima Secure base-plan grid into an offline candidate.

Run with --pdf PATH --output NEW_JSON. This has no database or application imports.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from pathlib import Path

from pypdf import PdfReader

SOURCE_HASH = "ff924d405c28e256fada87ce0bfc0b63816f06e87e2d9e9fdd91e115f4a01d32"
COVERS = [500000, 1000000, 1500000, 2000000, 2500000, 5000000, 10000000, 20000000]
AGES = [str(number) for number in range(90)] + [">=90"]


def extract(pdf: Path) -> dict[str, object]:
    with pdf.open("rb") as stream:
        content = stream.read(20 * 1024 * 1024 + 1)
    if hashlib.sha256(content).hexdigest() != SOURCE_HASH:
        raise ValueError(
            "Unsupported source bytes; review the new source before adapting extraction"
        )
    reader = PdfReader(io.BytesIO(content))
    if reader.is_encrypted and not reader.decrypt(""):
        raise ValueError("Private-password PDF is unsupported")
    if len(reader.pages) != 291:
        raise ValueError("Expected 291 physical pages")
    pages = {number: reader.pages[number - 1].extract_text() for number in range(69, 93)}
    rows = []
    tiers = []
    column_heading = " ".join(f"{value:,}".replace(",", "") for value in COVERS)
    for tier in range(1, 7):
        first = 69 + (tier - 1) * 4
        # A Tier 5 heading wraps across lines: never take just its first line.
        headings = list(
            re.finditer(
                r"my: Optima Secure - Optima Secure Gross Premium\s*-\s*Tier\s+"
                r"(\d)\s*(\(.*?\))\s*Age\s+Sum Insured\s*\n([^\n]+)",
                pages[first],
                re.DOTALL,
            )
        )
        if len(headings) != 1 or int(headings[0][1]) != tier:
            raise ValueError(f"Wrong or ambiguous base-plan heading on page {first}")
        match = headings[0]
        if " ".join(match[3].replace(",", "").split()) != column_heading:
            raise ValueError(f"Unexpected cover columns for tier {tier}")
        tiers.append(
            {
                "tier": tier,
                "pdf_page": first,
                "geography_source": " ".join(match[2].split()),
                "heading_quote": match[0],
            }
        )
        tier_rows = []
        for number in range(first, first + 4):
            for line in pages[number].splitlines():
                row = re.fullmatch(r"\s*(>=90|\d{1,2})\s+(.+?)\s*", line)
                if row is None:
                    continue
                tokens = row[2].split()
                if len(tokens) != 8 or any(re.fullmatch(r"\d[\d,]*", t) is None for t in tokens):
                    raise ValueError(f"Malformed price row at page {number}: {row[1]}")
                values = [int(token.replace(",", "")) for token in tokens]
                if any(value <= 0 for value in values):
                    raise ValueError(f"Non-positive price at page {number}")
                tier_rows.append(
                    {
                        "tier": tier,
                        "age_source": row[1],
                        "gross_premium_inr": values,
                        "pdf_page": number,
                        "source_row": line,
                    }
                )
        if [row["age_source"] for row in tier_rows] != AGES:
            raise ValueError(f"Missing, duplicate or reordered age coordinates in tier {tier}")
        rows.extend(tier_rows)
    return {
        "purpose": "offline_tariff_review_candidate",
        "source_sha256": SOURCE_HASH,
        "product_uin": "HDFHLIP26058V082526",
        "variant": "Optima Secure Plan",
        "sum_insured_columns_inr": COVERS,
        "premium_label_source": "Gross Premium",
        "tiers": tiers,
        "rows": rows,
        "row_count": len(rows),
        "cell_count": len(rows) * 8,
        "review_status": "pending_human_review",
        "approved_for_import": False,
        "production_approved": False,
        "limitations": [
            "Printed rates only; no tax or modifier composition is assumed.",
            "Geographic descriptions are source text, not an address resolver.",
            "Age definition, eligibility, source applicability, benefit overrides "
            "and underwriting require review.",
            "Grid coordinate completeness does not establish transcription accuracy "
            "or quote validity.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = extract(args.pdf)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(output, stream, indent=2, ensure_ascii=True)
        stream.write("\n")
    print(
        json.dumps(
            {
                "rows": output["row_count"],
                "cells": output["cell_count"],
                "output": str(args.output),
                "approved_for_import": False,
            }
        )
    )


if __name__ == "__main__":
    main()
