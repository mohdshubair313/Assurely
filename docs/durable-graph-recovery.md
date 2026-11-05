# Durable graph checkpoints and interrupted-turn recovery

Implemented checkpoint: 2026-11-03. This changes infrastructure and API boundaries;
no graph node or conditional edge is added or reordered.

## Execution and persistence

Development uses the existing in-memory graph. Staging/production startup requires
the official asynchronous Postgres saver and a verified checkpoint schema; there
is no fallback to memory. Dependencies are pinned to checkpoint-postgres 3.2.0,
checkpoint 4.3.1 and psycopg 3.3.7. The saver uses a managed connection pool,
autocommit, dictionary rows, disabled pickle fallback and an empty dynamic-module
allowlist. Graph writes use synchronous durability before advancing supersteps.

Every production turn has a distinct checkpoint thread derived from the configured
issuer, canonical database session UUID and server-generated turn UUID. Client
input never selects a checkpoint ID or resumes a pending task. New turns inherit
the last successfully completed graph state and append their message; they reset
approval, delivery hold and the explicitly selected comparison scenario as before.

Migration `009_turn_recovery` adds `report_heads.completed_turn_id` and immutable
owner/turn/request-bound recovery receipts. Only successful `finish_turn` advances
the completed checkpoint pointer. Failed or recovered turns retain the previous
completed pointer. Session reads use that pointer; advisor staging additionally
requires it to match the current complete turn. Each new request still invalidates
old report-release authority before graph execution.

An abandoned worker can only write its obsolete turn's checkpoint namespace. It
cannot advance the completed pointer or bind a report after recovery/new-turn
invalidation, because `finish_turn` checks the exact current running turn ID.

## Cross-worker lock and recovery

The message boundary acquires a nonblocking Postgres advisory transaction lock for
issuer/session before reading prior state, and holds its dedicated SQLAlchemy
connection through the graph call and completion. Another worker or recovery
request receives 409 while that lock is held. Lock release on connection/process
loss permits recovery; a slow live worker is never aborted based on elapsed time.
Connection loss is probed before publishing completion. Each running turn consumes
one SQLAlchemy connection in addition to node/database work; size deployment pools
and database connection limits for the expected concurrency.

Owner endpoint:

```http
POST /v1/sessions/{session_id}/recover-turn
Authorization: Bearer <verified owner token>
Content-Type: application/json

{"turn_id":"<current running turn UUID>","request_key":"<new UUID>"}
```

The endpoint requires the same configured issuer, verified owner, exact current
running turn and the execution lock. In one transaction it changes the turn to
failed, clears report/approval authority and appends an immutable receipt. The
receipt is returned only after commit. An exact retry returns its historical
receipt; another turn/session cannot reuse its request key. Replaying an old
receipt never changes a newer turn. Status metadata is available through the
existing owner-only `report-status` endpoint.

After recovery, send a new message. Recovery deliberately closes an interrupted
turn rather than replaying it: a model call, audit write or advisor notification
may already have happened before the last checkpoint. Mid-node automatic resume
and exactly-once external effects are not claimed. Anonymous users cannot obtain
owner recovery rights; they can start a new anonymous session after interruption.

## Setup, operations and data

After rebuilding dependencies, run these operator commands against the intended
database before changing the application's environment to staging/production:

```sh
alembic upgrade head
python -m app.db.setup_checkpoints
```

The second command explicitly runs the pinned saver package's migrations in its
own autocommit connection. It creates `checkpoint_migrations`, checkpoint/blob/write
tables and package-managed indexes; application startup only verifies the schema
version. Coordinate this command as one deployment migration job. Alembic downgrade
009 refuses when completed checkpoint pointers or recovery receipts exist. Native
checkpoint tables are not dropped by an application downgrade.

Existing in-memory conversations are not imported. Existing release heads without
a completed pointer do not acquire invented conversation history. Checkpoints store
full graph state, including conversation and health-profile data: restrict database
access, apply deployment encryption/TLS and include the native checkpoint tables
in backup and retention operations. This checkpoint does not implement a retention
purge job or regulatory/privacy sign-off. Application migrations, live identity and
advisor configuration, and real policy/calculator approval remain deployment gates.

## Validation

Disposable Postgres tests exercise pool/compiled-graph reconstruction, actual full
application graph topology with synthetic node implementations, checkpoint history,
issuer/turn isolation, signed two-turn HTTP continuation, owner-only recovery,
active-worker rejection, idempotent receipts, late completion rejection, rollback,
immutability and migration guards. Nodes, policy facts and identities in tests are
synthetic. Recreating pools/graphs models application restart; a database-server
restart and infrastructure failover were not exercised.

References: [LangGraph Postgres saver](https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-postgres),
[durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution),
[report release](report-release.md).
