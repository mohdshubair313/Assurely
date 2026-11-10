# Assurely voice architecture (initial design)

V2a checkpoint, 2026-11-07: bounded REST adapter, signed durable event inbox/reconciliation,
authenticated synthetic-only BYOL and additive migration 013 are implemented. Customer dispatch
remains closed. No browser media, real provider termination or paid billing is claimed.
Current [implementation report](docs/VAANI_V2A_IMPLEMENTATION_REPORT.md) and
[setup guide](docs/VAANI_V2A_SETUP.md) supersede the historical V1 status below.

Updated V1 status, 2026-11-06: the separate `VoiceSessionService`, durable operation receipts,
additive migration 012, consistent locking, consented mock start/revocation and independent
expiry/recovery worker are implemented. Live Vaani media, events, BYOL and paid billing remain
unimplemented. [Implementation report](VOICE_IMPLEMENTATION_REPORT.md) records exact boundaries
and test results; the paired functional/technical specs are the implementation contract.

## Trust boundaries

1. The browser signs in with Clerk. FastAPI independently verifies the Clerk session and maps it to the internal UUID.
2. FastAPI owns consent receipts, subscription entitlements, reservations, session ownership, maximum duration and usage settlement. Browser values never grant minutes or payment status.
3. `VoiceProvider` is provider-neutral. A mock provider is permitted only for local/test fixtures. The Vaani adapter stays disabled until the account contract, credentials, browser client and webhook authentication are verified.
4. A voice answer may use only scoped, read-only Assurely tools. Tool responses must be grounded in verified policy publication/version evidence or deterministic calculator output, and must carry the existing delivery-hold state. No voice code writes a report, clears a hold or approves a source/case.
5. The existing graph remains unchanged. Voice session lifecycle is a separate service/API. Human policy approval and individual case review retain their existing authorization and audit path.

## V1 local mock boundary

The mock uses only a fixed synthetic policy fixture and a deterministic canned answer. It does not accept case IDs, policy documents, medical information or user-authored instructions; does not capture microphone audio; and does not persist a transcript. It is visibly marked as a no-audio prototype. Only explicitly allowlisted test identities may receive test minutes. No production checkout or customer entitlement is provisioned.

## Later live call lifecycle

`Clerk -> FastAPI identity -> current consent -> server subscription entitlement -> row-locked minute reservation and concurrency check -> provider session -> browser media -> scoped evidence/calculator tools -> final output safety check -> authenticated end/event reconciliation -> idempotent ledger settlement`.

The provider must be unable to retrieve arbitrary case data: internal tools bind user, session and case on the server, reject caller-selected owners, and return only minimal safe-to-speak facts with publication digest/source/date. A held report stays held across spoken answers, captions, transcript, summaries and reloads. A human-transfer callback records a connection event only; it cannot authorize a policy or case.

## Data minimization and retention

- No raw audio storage by Assurely. Provider recording must be disabled or explicitly consented and contractually approved.
- Transcript and summary retention are off until separately consented, minimized, owner-scoped and covered by a retention/deletion policy.
- Provider metadata contains only a random internal voice session reference and selected language; never identity, health details, policy documents or bearer tokens.
- All provider/webhook secrets stay in the server environment. Webhooks fail closed until Vaani's signing method is verified.
- Logs use internal session IDs and bounded event categories. No raw speech, transcript, audio URL or API secret in logs/traces.

## Failure behavior

Provider timeout, invalid signature, quota uncertainty, tool failure, unverified evidence, source conflict or delivery hold ends or pauses the voice turn with a safe explanation. A failed/unanswered call releases its reservation only after trusted provider state or a conservative server timeout/reconciliation rule. A browser end request alone is not proof of provider duration in the live integration.

## Production dependencies

Vaani account/contract and exact WebRTC + webhook contracts; real stack pricing and language evaluation; verified policy and calculator approvals; safe scoped tool endpoints; qualified human destination; billing merchant setup and webhook verification; privacy/DPA/DPDP review; observability/redaction; and staging end-to-end acceptance.
