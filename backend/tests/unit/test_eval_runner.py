"""Unit test for the eval suite and case runner."""

from eval.runner import load_eval_cases, run_eval_case, evaluate_compliance_rules


def test_eval_cases_loaded() -> None:
    cases = load_eval_cases()
    assert len(cases) >= 8


def test_eval_cases_pass() -> None:
    cases = load_eval_cases()
    for case in cases:
        res = run_eval_case(case)
        assert res["passed"] is True, f"Eval case {res['case_id']} failed: {res['reasons']}"


def test_prohibited_words_detection() -> None:
    violations = evaluate_compliance_rules("This is the best health policy in India.")
    assert len(violations) > 0
    assert "best" in violations[0]
