"""Source proposals cannot fabricate provenance or approve themselves."""

import hashlib
import io
import json
from copy import deepcopy
from datetime import date

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.db.source_review import FIELDS, validate_package


@pytest.fixture
def candidate():
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 10 100 Td (36 months of continuous coverage) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    buf = io.BytesIO()
    writer.write(buf)
    content = buf.getvalue()
    fields = [
        {"name": name, "status": "missing", "unresolved": ["Not reviewed"]}
        for name in sorted(FIELDS)
    ]
    next(f for f in fields if f["name"] == "ped_waiting_period").update(
        status="extracted",
        proposed_value="36",
        unit="calendar_months",
        references=[
            {
                "source_id": "wording",
                "pdf_page": 1,
                "clause": "PED",
                "quote": "36 months of continuous coverage",
            }
        ],
        conditions=["Continuity and policy schedule require review"],
    )
    package = {
        "format_version": "policy-source-review-v1",
        "insurer": "Synthetic",
        "product": "Synthetic",
        "review_status": "pending_human_review",
        "sources": [
            {
                "id": "wording",
                "url": "https://example.com/wording.pdf",
                "sha256": hashlib.sha256(content).hexdigest(),
                "accessed_on": "2026-10-24",
                "page_count": 1,
            }
        ],
        "fields": fields,
    }
    return package, {"wording": content}


def check(package, contents):
    return validate_package(json.dumps(package), contents, as_of=date(2026, 10, 25))


def test_review_validation_never_approves_import(candidate):
    package, contents = candidate
    receipt = check(package, contents)
    assert receipt["structurally_valid"]
    assert not receipt["approved_for_import"] and not receipt["production_approved"]
    assert "premium_table" in receipt["missing_fields"]
    assert "ped_waiting_period" in receipt["unresolved_fields"]
    assert "calendar_months" in json.dumps(package) and "1095" not in json.dumps(package)


@pytest.mark.parametrize(
    "mutation",
    [
        "approval",
        "hash",
        "unknown_source",
        "page",
        "page_count",
        "quote",
        "bool_page",
        "missing_reason",
        "missing_value",
        "duplicate_field",
        "future",
        "credentials",
        "unit",
    ],
)
def test_invalid_source_proposals_are_rejected(candidate, mutation):
    original, contents = candidate
    package = deepcopy(original)
    field = next(f for f in package["fields"] if f["name"] == "ped_waiting_period")
    if mutation == "approval":
        package["review_status"] = "approved"
    elif mutation == "hash":
        package["sources"][0]["sha256"] = "0" * 64
    elif mutation == "unknown_source":
        field["references"][0]["source_id"] = "other"
    elif mutation == "page":
        field["references"][0]["pdf_page"] = 2
    elif mutation == "page_count":
        package["sources"][0]["page_count"] = 200
    elif mutation == "quote":
        field["references"][0]["quote"] = "All claims are paid"
    elif mutation == "bool_page":
        field["references"][0]["pdf_page"] = True
    elif mutation == "missing_reason":
        package["fields"][0]["unresolved"] = []
    elif mutation == "missing_value":
        package["fields"][0]["proposed_value"] = "invented"
    elif mutation == "duplicate_field":
        package["fields"][0] = package["fields"][1]
    elif mutation == "future":
        package["sources"][0]["accessed_on"] = "2027-01-01"
    elif mutation == "credentials":
        package["sources"][0]["url"] = "https://secret@example.com/wording.pdf"
    else:
        field["unit"] = "INR"
    with pytest.raises(ValueError):
        check(package, contents)


def test_modified_document_and_extra_sources_fail(candidate):
    package, contents = candidate
    with pytest.raises(ValueError):
        check(package, {"wording": contents["wording"] + b"changed"})
    with pytest.raises(ValueError):
        check(package, {**contents, "unexpected": contents["wording"]})


def test_duplicate_json_fields_fail(candidate):
    package, contents = candidate
    raw = json.dumps(package).replace('"insurer": "Synthetic"', '"insurer": "A", "insurer": "B"')
    with pytest.raises(ValueError, match="Duplicate JSON"):
        validate_package(raw, contents, as_of=date(2026, 10, 25))


@pytest.mark.parametrize("password", ["", "private-password"])
def test_public_permission_encryption_and_private_password(candidate, password):
    package, contents = candidate
    writer = PdfWriter(clone_from=io.BytesIO(contents["wording"]))
    writer.encrypt(user_password=password, owner_password="owner-password")
    output = io.BytesIO()
    writer.write(output)
    content = output.getvalue()
    package["sources"][0]["sha256"] = hashlib.sha256(content).hexdigest()
    if password:
        with pytest.raises(ValueError, match="private read password"):
            check(package, {"wording": content})
    else:
        assert check(package, {"wording": content})["structurally_valid"]
