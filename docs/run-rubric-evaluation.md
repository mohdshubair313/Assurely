# Run the rubric evaluation on Windows

The scorer and local tests are implemented. This guide runs the live pipeline and free judge;
the eight-case matrix is now scored and provenance-verified across two runs. No key needs to be pasted anywhere, and the
runner does not open or change `.env`. It privately uses credentials already loaded in the
running `insurance-api` container. Existing application containers and data are retained;
each evaluation uses a separate temporary container that is removed when it exits.

## October 13: current-code evaluation after maintenance

The October 12 matrix remains a historical baseline. Named-policy retrieval, report request
scope, and exact waiting-period units have changed since then. A fresh case-04 run passes
all six rubric criteria (retrieval 1.00, generation 1.00), with Postgres/Langfuse verification.
Other cases have not been evaluated under this report prompt. Do not merge the new case-04
score into the older matrix: their pipeline fingerprints differ.

**October 15 CASE05 status run:** the current status-only path uses deterministic
`policy_terms` evidence and intentionally skips clause RAG. Rubric v4 records both clause
retrieval criteria as not applicable for this path; generation and citation checks still
run. The isolated run artifact `case05-isolated-rubric-v4-390a9954cf82.json` uses an
explicitly synthetic expired record in the dedicated database
`insurance_case05_eval_390a9954cf82`. Its judge candidate label is unreviewed and the data
does not verify any real insurer product. Treat this as a targeted fixture result, not as
the complete current-code eight-case matrix or a calibration result.

Following your preference to run larger token-consuming batches yourself, run this **once**
when ready. Keep Docker Desktop running. No `.env` edits or pasted keys are needed.

```powershell
Set-Location D:\Projects\InsuranceAI
$env:PYTHONUTF8 = "1"
python backend/eval/rubric_live.py --preflight
```

Proceed only if the result is `preflight_passed`. Then:

```powershell
python backend/eval/rubric_live.py --output-name rubric-postfix-full-2026-10-13.json 2>&1 | Tee-Object -FilePath artifacts/rubric-postfix-full-2026-10-13.log
```

Allow roughly 25?35 minutes or longer for provider latency. Eight judge calls have at most
32,768 completion tokens, plus judge input and pipeline calls. Existing 60-second post-pipeline
and 180-second between-case cooldowns remain. The pinned judge is the free OpenRouter model;
no model, token-limit or billing changes are requested. This is a changed-code regression run,
not a blind retry of the completed baseline. Do not rerun if an error occurs.

Share the new JSON and log. Only final `status: complete` confirms scores and provenance.
`verification_incomplete` or `run_failed` requires inspecting the exact error first.
Human correctness labels and confidence calibration remain separate; passing this batch
will not substitute for them. Existing filenames are protected from overwrite.

## October 12 historical checkpoint: all eight baseline cases scored


The three scored cases in `rubric-live-v3-2026-10-11.json` and the five scored cases in
`rubric-live-v3-remaining-2026-10-11.json` use identical rubric, prompt, model, source and
reference hashes. The latter initially reported `verification_incomplete` because one
Langfuse CLI lookup timed out. Read-only rechecking found all eight continuation traces;
Postgres had already verified all eight rows. Original artifacts and statuses are preserved.

The current matrix is `artifacts/rubric-v3-complete-matrix-2026-10-12.json` and `.md`.
Verification evidence is `artifacts/rubric-v3-langfuse-recheck-2026-10-12.json`.
No judge or pipeline rerun was needed. The commands below are historical instructions,
not requests to repeat the completed evaluation. Review the matrix before further work.

Historical v1/v2 attempts, including the earlier case-04 contract failure and its successful
targeted rerun, are preserved in the artifacts. They are not the current run instructions.
PowerShell may display Python stderr warnings as `NativeCommandError`; use the saved JSON's
final status to determine whether the evaluator completed.

## 1. Open the project in PowerShell

Open Docker Desktop and wait until its engine is running. Open PowerShell and paste:

```powershell
Set-Location -LiteralPath 'D:\Projects\InsuranceAI'
python --version
node --version
docker --version
```

Each command should print a version. Python 3.11 or later works; the host script needs only
the Python standard library. If `python` is unavailable but `py` works, use `py -3` instead
of `python` in the following commands. Node.js provides `npx` for Langfuse verification.
There is no need to install Python packages, create a virtual environment, or edit `.env`.

## 2. Start the existing services

```powershell
docker start insurance-postgres insurance-redis insurance-chroma insurance-api
docker ps
Invoke-RestMethod -Uri 'http://localhost:8000/health'
```

Wait until Postgres and Redis show healthy and the health request succeeds. If a container
name is missing or the request keeps failing, stop and share that error. Do not recreate
containers with Compose or edit configuration for this run.

## 3. Run the zero-LLM-call preflight

```powershell
python backend/eval/rubric_live.py --preflight
```

Expected output includes `"status": "preflight_passed"`, five successful checks,
`"dotenv_accessed": false`, and `"llm_calls": 0`. It checks configured credentials, Postgres,
Redis, the existing clause collection, and a zero-price judge endpoint. It does not prove
the judge account currently has unused quota. If it fails, send the output and stop.

## 4. Historical five-case continuation command ? completed

The existing `rubric-live-v3-2026-10-11.json` scored cases 04, 01 and 08. Case 02 has a live
pipeline record but no rubric score. Cases 03, 05, 06 and 07 were not run. After confirming
network connectivity, run just these five cases with a fresh artifact name. Repeated `--case`
options are supported:

```powershell
python backend/eval/rubric_live.py --case case_02_edge_entry_age_cap --case case_03_missing_info_loop --case case_05_outdated_policy --case case_06_malicious_injection --case case_07_ambiguous_intent --output-name rubric-live-v3-remaining-2026-10-11.json 2>&1 | Tee-Object -FilePath artifacts/rubric-live-v3-remaining-2026-10-11.log
```

Keep PowerShell open and the computer awake. Allow roughly 20–25 minutes, potentially longer
for provider latency or the initial retrieval embedding-model download. Long pauses are
intentional: 60 seconds before each judge call and 180 seconds between cases. The judge uses
five calls with at most 20,480 total completion tokens, plus input and pipeline tokens.
Only the pinned free judge is used; the pipeline retains the project's existing free-tier
provider configuration with OpenRouter fallbacks pinned to the same free model.

You will see `running_case`, `case_scored`, cooldown messages, and a final result-file status.
Only a final `"status": "complete"` means every selected case was scored and its database/
Langfuse provenance was verified. `run_failed`, `bootstrap_failed`, or
`verification_incomplete` is not a completed run. Preserve the JSON and log, and send both;
do not retry blindly. If the result filename already exists, the runner refuses to overwrite
it. Stop and share it rather than deleting previous evidence.

## 5. Review the compiled results

The runner already compiles the results into:

```text
artifacts/rubric-live-v3-2026-10-11.json
artifacts/rubric-live-v3-2026-10-11.log
artifacts/rubric-live-v3-remaining-2026-10-11.json
artifacts/rubric-live-v3-remaining-2026-10-11.log
```

Send all four files here. The first pair contains the three already-scored cases and the
case-02 transport failure; the second pair contains the continuation. To inspect the
continuation JSON in PowerShell, run:

```powershell
Get-Content -LiteralPath artifacts/rubric-live-v3-remaining-2026-10-11.json -Raw
```

These artifacts contain scores, fixed reasons, token counts and correlation IDs, without
profile/answer bodies or API keys. Do not send `.env`, `docker inspect` output, or credentials.
I will check all eight cases, judge failures/disagreements, the case-04 topic gap, and the
01/08 coverage results before proposing any scorer changes or confidence calibration.

The v2 case-01 request hit its 4,096-token completion limit (3,981 prompt tokens,
4,096 completion tokens, finish reason `length`, returned cost $0). V3 keeps that limit and
shortens generation-criterion verdicts while retaining all judge input evidence and
retrieval clause indices. The case-01 v3 check passed with 3,306 prompt and 2,444 completion
tokens. Its console also showed a sanitized `error_ref`; the saved artifact does not include
the exception detail, and the temporary eval container is removed after the run. Preserve
the console log as part of matrix review; the warning did not prevent this run from scoring
or completing provenance verification. The v3 full-batch attempt then stopped at case 02
with `ConnectError` / `judge_transport_error`: no HTTP status or judge response was received
from OpenRouter, so this is a transport failure rather than a rate-limit response. Do not
repeat the full batch; the five-case continuation above has now completed scoring and its Langfuse verification gap has been resolved separately.
