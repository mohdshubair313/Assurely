"""Observed conflicting-citation failure must not depend on model cooperation."""

from unittest.mock import AsyncMock, patch

import pytest

from app.graph.claim_support import check_claim_support


@pytest.mark.asyncio
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("other", [
    "Synthetic Orchid excludes laboratory tests.",
    "Synthetic Orchid excludes cosmetic surgery.",
])
async def test_distinct_evidence_holds_even_with_supporting_exact_copy(other, reverse):
    claims = ["Synthetic Orchid includes laboratory tests.", other]
    if reverse:
        claims.reverse()
    citations = [{"id": f"E{i}", "claim": claim, "kind": "clause_wording"}
                 for i, claim in enumerate(claims)]
    with patch("app.graph.claim_support.llm_call", new=AsyncMock()) as llm:
        result = await check_claim_support([
            {"text": "Synthetic Orchid includes laboratory tests.", "citations": citations},
            {"text": "A faithful statement.", "citations": [{"claim": "A faithful statement."}]},
        ], "synthetic")
    assert not result["supported"]
    assert result["checks"][0]["method"] == "unresolved_citation_set"
    llm.assert_not_awaited()


@pytest.mark.asyncio
async def test_identical_evidence_from_two_citations_still_passes():
    with patch("app.graph.claim_support.llm_call", new=AsyncMock()) as llm:
        result = await check_claim_support([{
            "text": "Dental care is excluded.",
            "citations": [{"claim": "Dental care is excluded."},
                          {"claim": "Dental  care is excluded."}],
        }], "synthetic")
    assert result["supported"]
    llm.assert_not_awaited()
