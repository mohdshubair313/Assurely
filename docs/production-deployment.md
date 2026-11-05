# Deployment: Vercel and Back4App Containers

Updated 2026-11-03. Owner's frontend is already hosted on Vercel at
`https://assurely.shubair.in`. Back4App Containers is the proposed backend host;
no backend account, deployment, database or DNS change has been made by this work.
The [release gates](release-gates.md) still apply.

## Recommended first deployment

Use a staging backend with synthetic records before collecting real health data.
Keep the existing Vercel frontend. Run the existing FastAPI application in
**Back4App Containers**, using the repository's `backend` root directory and its
default `Dockerfile`. This does not replace the application with a Parse backend.
Keep automatic backend deployments disabled until the staging configuration and
release checks have been reviewed; later GitHub pushes must not silently cut over
an unqualified production service.
The default image is now non-root, installs production dependencies only and runs
without hot reload or HTTP access logs. Development Compose explicitly uses
`Dockerfile.development`, preserving its local workflow.

Back4App documents GitHub deployment and root-directory selection in its
[quickstart](https://www.back4app.com/docs-containers) and
[deployment settings](https://www.back4app.com/docs-containers/prepare-your-deployment).
Before choosing a plan, verify available RAM/CPU, cold starts/idle suspension,
request duration of at least 120 seconds, outbound connectivity, private persistent
diagnostic storage, backup support and region. Those plan-specific properties are
not certified by this repository. Do not assume its Parse database is a compatible
Postgres connection for our application/checkpointer.

## Backend dependencies and configuration

1. Provision an external PostgreSQL database and authenticated Redis endpoint.
   Use a direct or session-pooled Postgres endpoint compatible with session-level
   advisory locks and the checkpoint saver. Transaction-only poolers are not
   certified. Budget up to 30 application pool connections plus 10 checkpoint
   connections **per worker**, plus migrations and operational probes.
2. Supply the private values described in `deploy/backend.env.example` in the
   provider's secret/environment settings. No real secret belongs in GitHub or chat.
   Database URLs must use asyncpg's `?ssl=verify-full`; the checkpointer translates
   this into libpq's `sslmode=verify-full&sslrootcert=system`. Both drivers validate
   the certificate and hostname. This template assumes publicly trusted server
   certificates; private CAs require a separately reviewed trust configuration.
   Redis uses authenticated `rediss://`. URL-encode credential characters.
3. Configure a private Chroma service containing reviewed clause data. The existing
   legacy seed/fallback corpus is not qualified policy evidence. Source qualification
   and the delivered scoped-report boundary remain separate release gates.
4. Generate a random server-to-server `BACKEND_GATEWAY_TOKEN` of at least 32
   characters. Configure the same value on Vercel and the backend. Non-development
   API paths require this key before routing; `/health` and `/ready` expose only
   limited health state. This key **does not grant a customer/advisor/reviewer role**;
   JWT/owner/independent-review checks still apply. Duplicate key headers fail.
   Operator clients must supply this header as well as their own JWT when needed.
5. Set `ENVIRONMENT=production` and `CORS_ORIGINS=[]`. Customer requests go through
   the Vercel server gateway. Configure a genuine identity provider, UUID role
   allowlists and authorized advisor webhook; test their operation independently.
6. Mount a private persistent volume at `/var/log/insuranceai`, writable by UID
   10001, with encryption and restricted access. The app verifies the diagnostics
   directory. Ephemeral writable storage alone is not a durable incident record.
   If the proposed hosting plan cannot support this, this deployment gate remains
   open; do not bypass the mandatory diagnostic boundary.

After backup/migration review, run a one-off job **from the same image**, with the
intended private environment, in this order:

```sh
alembic upgrade head
python -m app.db.setup_checkpoints
python -m app.ops.preflight --database
```

No startup schema migration is automatic. The normal image entrypoint runs the
bounded read-only infrastructure preflight and refuses missing configuration or
schema before serving. Its temporary database pool is disposed before the ASGI
loop starts. Preflight success is never insurance approval. Liveness is `/health`;
use `/ready` for deployment readiness (diagnostics, durable runtime, application
schema and live Redis ping). Readiness returns no credentials or dependency error.
Native checkpoint schema is checked during runtime initialization. Configure the
platform's container port to **8000**, matching `EXPOSE` and the process listener.
Platform TLS terminates at the provider; `BACKEND_URL` must be the actual HTTPS URL.

## Vercel settings

Use `frontend` as the Vercel project root. Keep Node runtime support enabled;
authentication and the backend gateway are server routes, not a static export.
Set Production-scoped variables from `deploy/vercel.env.example`:

- `APP_ORIGIN=https://assurely.shubair.in`
- `BACKEND_URL` equal to the deployed HTTPS API origin, without a path.
- Matching server-only `BACKEND_GATEWAY_TOKEN` and `CLERK_SECRET_KEY`.
- `NEXT_PUBLIC_AUTH_PROVIDER=clerk` and the instance's
  `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` (the publishable key is intentionally public).
  `SESSION_SECRET` and OIDC settings are used only for an explicit legacy rollback.

Configure the owned domain, sign-in/up paths and allowed origins in Clerk, and set
the backend's exact issuer/JWKS/authorized parties per the
[Clerk guide](clerk-authentication.md). The old `/api/auth/callback` is disabled
in Clerk mode. Keep previews on a separate instance/origin and staging evidence;
never point untrusted previews at production health records. Redeploy after changes.

The gateway exports `maxDuration=150` and retains its 120-second upstream deadline.
Enable a compatible Vercel function-duration setting (Fluid Compute supports this
budget); legacy configurations may have lower limits. See
[Vercel function limits](https://vercel.com/docs/functions/limitations).
No long-running job/resume service is implied: an interrupted turn uses the existing
owner recovery protocol. Gateway requests use HTTPS outside the explicit portable
Compose private-network exception. Browser-supplied headers cannot replace the key.

Set Vercel/provider firewall request limits for sign-in and message ingress. The
optional nginx template below is **not** installed by a Vercel deployment. A shared
gateway key prevents direct backend bypass but does not rate-limit public frontend
traffic. Verify actual limits, alerting and account budgets before real-user launch.

## Portable container alternative

`deploy/compose.production.yml` is an alternative for an owned Docker host, not
instructions to migrate away from Vercel. It supplies non-root application images,
restricted/read-only filesystems, bounded memory/processes/logs, private API ports,
readiness ordering, TLS ingress and nginx per-IP limits for sign-in/messages/API.
Only ingress publishes ports; default binding is **127.0.0.1**, not public. A valid
certificate chain/private key and owned hostname must be provided privately.
The direct-ingress template overwrites forwarding headers; do not place it behind
a CDN/proxy without a reviewed real-IP trust policy. Rates are per-IP and per ingress,
not per-account global quotas. Defaults are starting budgets, not load-test results.

```sh
docker build -t assurely-api:release backend
docker build -t assurely-frontend:release frontend
docker build -f deploy/Dockerfile.backup -t assurely-backup:release deploy
# Populate private environment/TLS files before running Compose.
docker compose --env-file /secure/assurely/compose.env -f deploy/compose.production.yml config --quiet
docker compose --env-file /secure/assurely/compose.env -f deploy/compose.production.yml up -d
```

Before a release, record the built image digests and use those immutable references
for deployment/rollback. Runtime constraints capture the previously tested Linux
dependency versions; they are not a vulnerability scan or a hash-verified lock.
Review base-image updates and dependency/image scans before opening public ingress.
TLS renewal/reload, firewall rules, persistent storage encryption and off-host backup
storage are operator-managed. Do not open `BIND_ADDRESS` until the release checklist
has genuine evidence. Application/node source approval logic is unchanged.

## Encrypted backups and restore checks

The optional `backup` operations profile uses PostgreSQL 16 tools and native
**age public-key encryption**. Use a client matching the real server major version;
this image does not certify dumping newer servers. Supply a private environment
from `deploy/backup.env.example`, an age **public recipient**, and an output directory
writable by the image's postgres user. Keep the private decryption identity off the
application host and outside Git. A restricted `.pgpass` mount is preferable to a
password environment variable when the deployment supports file secrets.

```sh
docker compose --env-file /secure/assurely/compose.env -f deploy/compose.production.yml --profile operations run --rm backup
```

`pg_dump` streams directly into age; no plaintext dump is written to disk. The
script requires verified database TLS, hides provider errors, uses restrictive file
permissions and publishes a completed filename atomically only if both programs
succeed. It deletes an incomplete temporary encrypted file. It does not upload,
schedule, prune or select a legal retention period. Configure those responsibilities
with an owner, alerting and encrypted off-host storage before collecting real data.
The encryption format and recipient model follow the
[age project](https://github.com/FiloSottile/age).

On an isolated restore machine, decrypt and inspect the archive with `pg_restore
--list`, then restore into a **new disposable database**, never over the serving
database. Verify schema revisions, checkpoint reads, owner isolation, immutable
approvals/receipts and source publication counts; run the approval/revocation/release
journey. Record recovery time and retained snapshot age. Keep decryption keys and
connection credentials out of command history/logs. Synthetic backup/restart tests
are engineering evidence, not a production recovery drill.

## Cutover and rollback

Require genuine policy publication, qualified reviewer/advisor decisions, owned Clerk
login and webhook verification, approved/excluded calculator scope, restored backup,
record retention/deletion policy and measured capacity before real-user collection.
Run the held → independent review → release → revoke journey through the deployed
domain and actual identities. No script fabricates those approvals.

Keep the previous image digest and deployment environment revision. On a failure,
stop new ingress, preserve the database and logs, and redeploy the previous compatible
image. Do not automatically downgrade immutable audit/turn migrations or restore an
old backup into a live database. Database rollback requires a separate reviewed
recovery plan. This change does not perform a production deployment.
