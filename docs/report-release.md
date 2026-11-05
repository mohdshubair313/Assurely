# Durable current report and release decisions

Checkpoint: 2026-11-03. Migration 008 and boundary changes were flagged before
implementation. No graph node or routing edge changed.

## Current-turn binding

In non-development message execution, a transaction commits a new `report_heads`
turn ID and clears the previous report/approval **before** entering the graph.
Session ownership is checked against Postgres, including after checkpoint loss.
Concurrent turns for that session are rejected while the durable status is
`running`. Successful completion records only a freshly validated report snapshot
and the server guardrail result. Rejected/incomplete turns never restore previous
report authority. Ordinary graph failures mark the turn failed.

The pointer is scoped to issuer/session/owner, and late completion cannot overwrite
a newer turn. The snapshot uses the same digest as advisor review. No customer
request may write a report or guardrail approval into this store.

This release store is separate from the durable LangGraph checkpointer. Process
death/cancellation can leave a turn `running`, blocking another turn and release.
The verified owner
can close an interrupted turn through the verified-owner recovery endpoint, which
requires acquiring the same execution lock used by live workers. Durable full-graph
checkpoints and isolated turn namespaces now preserve completed conversation state;
see [checkpoint and recovery contract](durable-graph-recovery.md).
Development mode bypasses this lifecycle and cannot use the release endpoint.

## Release contract

An authenticated owner obtains `turn_id` and `report_digest` through
`GET /v1/sessions/{id}/report-status`, then submits those plus a UUID `request_key`
to `POST /v1/sessions/{id}/report-release`. The response commits before exposing
the original generated report; only `explanation_report` writes graph output.

Checks share one transaction and lock order: request key → current session head →
advisor report → publication scope. Release requires:

1. Exact current complete turn/report and matching authenticated database owner.
2. Independently recorded guardrail approval. Advisor approval cannot replace it.
3. Current nonexpired, nonrevoked advisor decision by a still-allowlisted subject
   who is not the report owner.
4. Fresh publication/representation approval, source-byte and imported-term
   integrity, scenario/condition applicability and unchanged report evidence.
5. An immutable receipt bound to this turn, report, owner and advisor event.

Expiry is checked again after receipt construction. Any failure rolls back receipt
creation and exposes no report. Every retry revalidates live authority, even if a
receipt already exists. Reusing a key for a different decision fails. Receipts
record transaction-time release decisions; they do not prove network delivery or
grant perpetual access after revocation. State changes after commit cannot retract
bytes already sent to a client.

The returned `output` is the original generated artifact, including its historical
`reviewed_report_held` generation status. The outer `delivery_hold=false` and
release receipt describe this specific authorized delivery, without rewriting the
report. Message and ordinary session-read endpoints continue to redact reviewed
reports; release is explicit and separately authenticated.

## Production boundary

The [scoped guardrail contract](reviewed-guardrail-contract.md) now validates the
selected reviewed facts with a fresh database lookup and mandatory escalation.
Customer release still requires independent advisor authorization and another
fresh transactional evidence check. Earlier release tests use synthetic server
guardrail flags; the newer guardrail integration cases exercise the actual node.
All policy and advisor fixtures remain synthetic; real-source and deployment
approval are outstanding.

Application migrations were not applied. Migration 008 creates `report_heads`
and append-only `report_release_receipts`, and refuses downgrade with records.
Immutable foreign-key references preserve audit evidence; deletion/retention needs
an explicit operational policy. No real auth configuration or source approval was
changed during this checkpoint.

## Verification

Focused evidence is recorded in `PROGRESS.md` and the ignored local XML artifacts.
Tests cover concurrent receipt retry, database reconnect, new-turn invalidation,
rejected turns, late completion, self/foreign ownership, guardrail rejection,
advisor revocation, rollback, signed HTTP release and migration lifecycle.

Example isolated setup from the repository root (Docker Linux engine):

```sh
docker build -t assurely-api:local ./backend
docker run -d --rm --name assurely-release-test --network none -e POSTGRES_DB=policy_review_test_terms -e POSTGRES_PASSWORD=synthetic-test-only postgres:16-alpine
docker exec assurely-release-test pg_isready -U postgres
docker run --rm --network container:assurely-release-test -e POLICY_REVIEW_TEST_DATABASE_URL=postgresql+asyncpg://postgres:synthetic-test-only@127.0.0.1:5432/policy_review_test_terms assurely-api:local python -m pytest tests/integration/test_report_release.py -q
docker stop assurely-release-test
```

Wait for `pg_isready` to succeed before running tests. This explicitly named
database is disposable and test fixtures reset its schema. Never substitute an
application database URL. Test failure requires cleanup of this disposable
container as well.
