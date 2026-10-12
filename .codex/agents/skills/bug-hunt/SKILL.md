
---
name: bug-hunt
description: Use when investigating runtime bugs, failing tests, or regressions. Do not use for normal feature requests.
---

# Bug Hunt

## Objective
Find the root cause and deliver the smallest safe fix.

## Workflow
1. Understand the observed vs expected behavior.
2. Identify the execution path.
3. Reproduce the bug where possible.
4. Identify root cause using code evidence.
5. Add a regression test.
6. Implement a minimal fix.
7. Run targeted tests and relevant checks.
8. Review the diff for unrelated changes.

## Rules
- Do not guess the root cause.
- Do not silence exceptions to hide the failure.
- Preserve existing behavior.
- Avoid unnecessary refactoring.
- Report unverified assumptions.

## Output
- Root cause
- Files changed
- Tests executed and results
- Remaining risks
