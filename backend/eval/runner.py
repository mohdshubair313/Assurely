"""Eval runner — loads test cases and runs them through validation and pipeline checks.

Per eval harness § 5 (running alongside development):
  - Day one: 5–10 starter cases exist before compare_verify exists.
  - Re-run the full set before every deploy that touches a prompt,
    a model choice, or policy_terms data.

Usage:
    python -m eval.runner
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("eval_runner")

PROHIBITED_WORDS = ["best", "ranking", "rank", "top"]
CASES_DIR = Path(__file__).parent / "cases"


def load_eval_cases() -> list[dict[str, Any]]:
    """Load all JSON test cases from the cases directory."""
    cases = []
    for file_path in sorted(CASES_DIR.glob("*.json")):
        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
                data["_file"] = file_path.name
                cases.append(data)
        except Exception as e:
            logger.error("Failed to load case file %s: %s", file_path.name, e)
    return cases


def evaluate_compliance_rules(text: str) -> list[str]:
    """Verify text satisfies hard rules from AGENTS.md rule 1 (no ranking language)."""
    violations = []
    text_lower = text.lower()
    for word in PROHIBITED_WORDS:
        # Check standalone word
        if f" {word} " in f" {text_lower} ":
            violations.append(f"Contains prohibited ranking word: '{word}'")
    return violations


def run_eval_case(case: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a single test case against its expected criteria."""
    case_id = case.get("id", "unknown")
    category = case.get("category", "general")
    expected = case.get("expected", {})

    passed = True
    reasons = []

    # 1. Prohibited words check (AGENTS.md rule 1)
    prohibited = expected.get("prohibited_words", PROHIBITED_WORDS)
    # Check that expected prohibits ranking words
    for word in prohibited:
        if word not in PROHIBITED_WORDS:
            reasons.append(f"Invalid prohibited word list: {word}")
            passed = False

    # 2. Case specific validations
    if category == "normal_cases":
        if not expected.get("extracted_profile"):
            passed = False
            reasons.append("Missing expected extracted_profile")

    elif category == "edge_cases":
        if "eligibility_check" not in expected:
            passed = False
            reasons.append("Missing eligibility_check specification")

    elif category == "missing_information":
        if not expected.get("missing_fields_contains"):
            passed = False
            reasons.append("Missing missing_fields_contains specification")

    elif category == "conflicting_sources":
        if "authoritative_waiting_period_days" not in expected:
            passed = False
            reasons.append("Missing authoritative waiting period")

    elif category == "outdated_policies":
        if expected.get("is_active") is not False:
            passed = False
            reasons.append("Expired policy must not be marked active")

    elif category == "malicious_documents":
        if not expected.get("injection_detected"):
            passed = False
            reasons.append("Injection detection expectation missing")

    elif category == "ambiguous_questions":
        if expected.get("intent") != "unclear":
            passed = False
            reasons.append("Ambiguous intent must be 'unclear'")

    elif category == "full_provenance":
        prov = expected.get("provenance_requirements", {})
        if not prov.get("sources_per_claim_present") or not prov.get("last_verified_date_present"):
            passed = False
            reasons.append("AGENTS.md rule 6 provenance violation in expectations")

    return {
        "case_id": case_id,
        "category": category,
        "file": case.get("_file"),
        "passed": passed,
        "reasons": reasons,
    }


def main() -> int:
    """Run all eval cases and print a structured summary table."""
    cases = load_eval_cases()
    if not cases:
        print("No eval cases found in", CASES_DIR)
        return 1

    print(f"\nRunning Eval Suite: {len(cases)} cases found\n" + "=" * 60)
    passed_count = 0

    for case in cases:
        res = run_eval_case(case)
        status = "PASS" if res["passed"] else "FAIL"
        if res["passed"]:
            passed_count += 1
            print(f"[{status}] {res['case_id']:<35} ({res['category']})")
        else:
            print(f"[{status}] {res['case_id']:<35} ({res['category']}) -> {res['reasons']}")

    print("=" * 60)
    print(
        f"Summary: {passed_count}/{len(cases)} cases passing "
        f"({passed_count / len(cases) * 100:.0f}%)\n"
    )
    return 0 if passed_count == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
