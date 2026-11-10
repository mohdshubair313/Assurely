# Voice subscription and minute entitlement specification

V1 implementation update (2026-11-06): current entitlement periods are never reset by the mock
service; paid period history/rollover remains V4 work. Mock start/end keys are user/operation
scoped, reservations and settlement are transactional, ledger history is immutable and expiry
is independently recovered from persisted deadlines. Active expiry settles bounded simulated
elapsed seconds; an interrupted reserved start settles zero and releases its allowance. No
mock usage is a provider measurement or customer charge. Real duration/event reconciliation
and cancellation terms below remain a future contract, not implemented billing behavior.

## Source of truth

FastAPI/Postgres is authoritative for voice access and minute usage. A verified billing webhook (once a provider is selected) changes subscription state; a browser checkout result cannot. Plan identifiers, included seconds, effective dates, concurrency and single-call cap are server configuration or reconciled billing facts, never client inputs.

## Reservation and settlement

Starting a call locks the user's active entitlement row, verifies active status/current period/consents and counts active sessions while holding that lock. It reserves the configured maximum call duration from available seconds before contacting a provider, so concurrent starts cannot double-spend. Provider failure before a call starts releases the reservation idempotently. A trusted terminal event settles measured provider usage and releases the unused reserve. Duplicate events are idempotent by provider event ID. Provider billing pulse rounding is separate from included customer minutes and must be measured/configured explicitly.

User-initiated end is a request to stop; in live mode it does not itself establish billable duration. Reconciliation handles missing terminal events and does not refund uncertain minutes until provider state or timeout policy proves that the call did not occur. Cancellation stops new calls immediately; active calls are bounded by their reserved maximum and a verified provider disconnect.

## Local test entitlement

The V1 mock can create/use only a non-billable test entitlement for explicit server allowlisted test UUIDs. This is not a trial, plan, production subscription or payment state. Customer-facing products remain unavailable until real signed billing state is implemented.

## Provider evaluation

Clerk Billing is not suitable for this launch: official docs currently say it is unavailable for Indian merchants and usage-based metering is not supported. Razorpay Subscriptions is the candidate for an India merchant, subject to account/KYC, recurring-payment method eligibility, fees, webhook signature verification, tax and cancellation/refund review. Do not configure or charge until the merchant owner completes those steps.

## Cost model (not a retail price)

Per connected minute:

`Vaani platform fee + STT + LLM input/output + TTS + optional add-ons + payment fee allocation + applicable taxes + support/infra`.

Current public Vaani page lists ₹1/minute platform fee for pay-as-you-go; the vendor estimator's component rates are illustrative and depend on model, voice, token/character use, account plan and billing pulse. WebRTC removes the telephony charge only. Margin/pricing stays blank until we have a quote, exact stack, real test-call usage and actual invoices. No promise of unlimited calls or overage is made.
