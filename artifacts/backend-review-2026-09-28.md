# Backend review — September 28, 2026

Reviewed `f8377d0` plus the ingestion changes, which were committed during the
review as `ad7b1eb`; the cited implementation remained unchanged. This is a review,
not an implementation session. Application code, schema, graph routing and live
database/vector contents were not changed. Reproductions used synthetic content,
temporary files and isolated stores; the live Chroma check was read-only.

Verdict: useful implementation progress, but not ready for approval. The two P1
items below regress the established privacy and delivery contracts.

## Confirmed findings

### 1. P1 — Session reads bypass the delivery hold

`backend/app/api/v1/sessions.py:84` returns checkpoint messages, retrieved facts and
calculator outputs without checking `delivery_hold`, approval or escalation.
The ownership checks are useful but do not authorize releasing held advisory
content. A synthetic checkpoint with `delivery_hold=true`, `escalation=true` and
`approved=false` produced HTTP 200 with the held clause and calculator value from
`GET /v1/session/{id}`. The message-response builder hid both from the same state.

Apply the same delivery gate/redaction to every user-facing session read. Add a
regression comparing both response paths for held, unapproved and missing-gate
states. Preserve matching-subject authorization independently of delivery checks.

### 2. P1 — Exception-message handling retains private content

`backend/app/core/exception_log.py:237` bypasses profile/PII removal for allowlisted
exception classes after only credential-pattern scrubbing. A synthetic
`ConnectionError` retained a registered name and medical condition. Non-allowlisted
`RuntimeError` also retained the declared condition because `_get_profile_values`
at line 184 does not collect `pre_existing_conditions`; arbitrary generated text
was retained too. The general stream still correctly contained references only.
This is leakage into the restricted sink, not evidence of public log disclosure.

Restore a content-excluding default. Safe operational diagnostics should use
explicit templates/structured fields rather than treating an entire exception
class's free-form message as safe. Test provider-echoed content, nested health
fields, extraction failures before the profile exists and generated text.

### 3. P2 — Binary document ingestion does not preserve the screened representation

`backend/app/rag/ingestion.py:60` decodes binary input with UTF-8 replacement after
`screen_document` has hashed the original bytes. `PolicyVectorStore.add` then
checks the hash of the decoded string. A clean one-page PDF with a conventional
binary header was admitted by screening and then failed ingestion with
`ValueError` due to the changed hash. There is no actual PDF text extraction in
this path. ASCII-only PDF fixtures conceal the mismatch.

Also, `check_file_size_and_type` at `ingestion_screening.py:194` checks size, not
an allowed file-type set: an ELF executable header was admitted as text. Validate
the supported formats and screen/index a consistent extracted representation,
retaining the original-document hash separately where needed.

### 4. P2 — Quarantine records are raw, broadly readable and absent from the queue after restart

`backend/app/rag/ingestion_screening.py:404` copies the first 200 characters
directly into `document_snippet`. Synthetic private text and an email remained
unchanged. Lines 421–424 create the directory/file without restrictive modes;
both a controlled reproduction and the running container showed `0755`/`0644`,
unlike the restricted exception destination. The claimed sanitized snippet is
not implemented.

The JSONL file survives, but a fresh `QuarantineStore` starts with an empty
`_records`, so `list_records()` returns zero and `get_by_hash()` cannot locate
previously quarantined records. Persistence failures are also swallowed after an
in-memory append. Sanitize/restrict this destination and ensure the reviewer
queue actually recovers persisted records; test restart and write failure.

### 5. P2 — The live ingestion script does not establish Chroma persistence

`backend/eval/ingestion_screening_live_verify.py:65` and line 104 call the generic
search abstraction, which silently permits an in-memory fallback. Running the
script against a store with `_collection=None` still passed every assertion and
reported success. A similarity search over a small result set also cannot prove
that a rejected document is absent by ID.

The read-only live check reached Chroma successfully, but `get_collection` returned
`InvalidCollection: Collection policy_clauses does not exist.` Both v1 and v2
heartbeat endpoints returned 200. This establishes a missing current collection,
not a network outage, SDK incompatibility or proof about historical server state.

Require a live collection for this verification, check the exact inserted and
rejected IDs directly, and prove persistence using a new client/process. Report
fallback verification separately. Nine passing synthetic screening fixtures do
not establish broad injection-detection accuracy.

### 6. P2 — Document version provenance is dropped during retrieval

`PolicyVectorStore.add` saves the screening `version_hash`, but both result
projections in `backend/app/rag/vector_store.py:274` and line 308 omit it.
`backend/app/rag/retriever.py:48` likewise only forwards claim/source/URL/dates.
The synthetic check confirmed the hash existed in storage and was absent from
the returned fact. Consequently the actual retrieved document version cannot
travel through `retrieved_facts` into decision evidence. The separate
`policy_versions_evaluated` field describes evaluated policy-terms rows and does
not repair that missing clause-document link. Preserve and test the ingestion
hash through both storage backends, retrieval and decision persistence.

## Independent validation

| Check | Result |
| --- | --- |
| Complete suite, network-isolated Docker | 246 passed, 1 failed |
| Failure | `test_api_endpoints.py::test_session_endpoint` now accesses an unmocked live database |
| Same test with Compose database available | 1 passed |
| Ruff over app/tests/eval/alembic | 2 E501 errors at `eval/ingestion_screening_live_verify.py:66` and `:105` |
| Strict mypy over app | Passed, 72 source files |
| Eval runner | 8/8 cases passed; includes nine real screening fixtures |
| Chroma read-only check | Service reachable; expected collection absent |

The database-dependent test failure is a test-isolation regression, not proof
that the session endpoint fails against an available database. Conversely,
passing those tests does not cover the delivery/privacy defects reproduced here.
No fresh all-provider or frontend end-to-end claim is made. No frontend changes
were present relative to the previously reviewed publication baseline.

Evidence: `review-boundary-findings.json`, `review-chroma-presence.json`, and
`review-backend-tests.xml` in this directory. The earlier full-pass and live-proof
artifacts were preserved. Missing verification dates remain missing; the review
did not find the initially suspected date-fabrication issue in this change.

Next task: repair and independently verify the two P1 boundaries first, then the
ingestion/quarantine/provenance and verification defects. Do not treat this review
as approval to advance to another graph node.
