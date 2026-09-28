# Restricted exception diagnostics

The API installs a separate `RestrictedExceptionHandler` at startup. It writes
JSON records to a private Docker volume, separate from stdout and container
logs. There is no HTTP read endpoint. The service account may write/read its own
records; the supported human read path requires the OS administrator role:

```sh
docker compose exec --user 0 api python -m app.core.exception_log ERROR_REFERENCE
```

The directory has mode `0700`, and every record has mode `0600`. Startup fails
when the destination cannot be secured or written. Native Windows execution
must use the Linux Docker service: Windows `chmod` cannot establish this boundary.
An unprivileged container identity must receive `PermissionError` on direct file
reads as well as on the admin reader. Docker administrators are root-equivalent;
application customer/advisor roles do not grant access to Docker or these files.

## Content and correlation

Each record has an `error_ref`, UTC timestamp, exception class, sanitized message,
structural traceback (file basename, function and line), node name, canonical
`session_id`, W3C `trace_id`, and preallocated `decision_trace_id`.

Exception messages are replaced with `[exception message redacted]`. Chained
exception classes and frames remain, but exception strings, notes, source lines,
locals, request bodies, profile fields and generated text are never serialized.
This uses the same content-exclusion policy as Langfuse, rather than assuming a
regular expression can identify every personal or provider-echoed value.
Debugging follows code locations, error class and correlated decision evidence;
there is intentionally no raw-message override, including in development.

General logs contain only `error_ref=...` for failures and code-location events
for other messages. Existing query/profile log arguments are discarded before
formatting. Uvicorn and third-party handlers present at startup pass through the
same boundary. Do not add raw logging handlers or enable independent HTTP wire,
request-body or model-prompt debug capture in deployment.

For `/v1/message`, the trace ID is also the actual Langfuse root trace ID. The
decision row uses the preallocated UUID as its primary key, and its existing
`rules_engine_output_json.correlation` field records those identifiers. No new
table or graph route was introduced. Non-UUID caller session IDs use the existing
stable database UUID mapping before entering either diagnostic destination.

The intentional storage split remains: Postgres `decision_trace` retains real
profile/clauses/citations/confidence evidence for evals; diagnostic logs and
Langfuse omit that content. A correlation ID is not an authorization credential.
A decision row exists only if the turn reaches and commits `persist_memory`.
Errors before that point still have an allocated ID but must not be represented
as persisted turns. Non-conversation API failures have no session or decision ID.

## Deployment controls and retention

| Setting | Default | Purpose |
| --- | --- | --- |
| `EXCEPTION_LOG_DIR` | `/var/log/insuranceai/private` | Private service-owned destination |
| `EXCEPTION_LOG_RETENTION_HOURS` | `168` | Record age limit; 1–720 hours |
| `EXCEPTION_LOG_MAX_RECORDS` | `1000` | Count cap; oldest records removed first |
| `EXCEPTION_LOG_CLEANUP_SECONDS` | `60` | Idle cleanup interval; 1–3600 seconds |

Age/count cleanup runs on startup, writes, and the periodic idle task. Expiration
can lag by at most the cleanup interval while running. When the service is
stopped, deployment must run an equivalent privileged cleanup job or expire the
volume/backups according to the same policy. A private sink/cleanup failure
never prints raw data as fallback and makes `/health` return 503 until restart.
Monitor readiness and general error references; alert on diagnostics failures.

Deployment must enforce: admin-only human reads (separate from general-log
readers), least-privilege service access, restricted Docker socket/host access,
encrypted storage and backups, bounded retention including backups, and an
audited operational read process. Do not mount this volume into the frontend,
serve it as static files, upload it to Git, or copy it to an unrestricted log
collector. Current Compose is a single-process development service running as
container root. Before multi-process deployment, provision one private directory
per writer or a centrally controlled collector; this file sink is not a shared
multi-writer log service.

## Synthetic verification

`backend/eval/exception_log_preflight.py` starts a temporary Uvicorn process on a
random loopback port and replaces only its report-provider call with an exception
containing two distinctive fake condition values. The normal app imports none of
this harness and has no environment-controlled injection or authentication bypass.
Other model calls, graph routing, policy reads, Postgres persistence and Langfuse
delivery run normally. The test asserts the failed report remains held, both
logs exclude the fake values, and the private record links to the actual decision
row containing the synthetic profile. Real personal data must never be used in
this harness. Only a sanitized copy of synthetic verification evidence may be
checked into `artifacts/`.
