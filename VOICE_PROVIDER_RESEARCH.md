# Vaani provider research

**Current operational follow-up:** bounded read-only preflight still fails provider authentication;
key format/header/origin are correct and the agent setting is a placeholder. Public HTTPS tunnel
and synthetic signed ingress now pass; this does not establish vendor authentication, 101/audio
or termination. See [the current report](docs/VAANI_DOCKER_TUNNEL_REPORT.md).

## 2026-11-07 V2a update

The actual configured key was tested with a bounded read-only `GET /api/agents` request:
**HTTP 401**, so authentication failed and no owned agent could be identified. A second
read-only check through the implemented adapter returned only sanitized `authentication`
status. No dispatch, agent mutation or paid action occurred. Final local audit found an agent
value that is not a valid UUID; an owned development ID is still required.
Dedicated BYOL and webhook credentials were generated privately in ignored local configuration;
the receiver and authenticated synthetic-only socket are now implemented, not deployed.

Official dispatch/webhook/BYOL/SDK documentation was rechecked through direct HTTPS markdown
because the browsing fetch failed. SDK 0.3.1 wheel source was inspected without installation
or execution: agent listing uses `/api/agents`, detail `/api/agents/{id}`; request/response
models distinguish direct dispatch from managed sessions. The HTTP adapter uses fixed origin,
`token`/`room_name`/`connection_url`, safe bounds and no automatic dispatch retry. Current docs
state **seconds for both** terminal durations. Lifecycle signatures are bare HMAC-SHA256 hex;
postprocessing uses `sha256=`. BYOL appends call ID to a configured base URL and supports
Bearer authentication and `fallback=none`. All account-level behavior remains unverified.

Current evidence and exact setup: [V2a report](docs/VAANI_V2A_IMPLEMENTATION_REPORT.md),
[dashboard guide](docs/VAANI_V2A_SETUP.md). The sections dated November 5/6 below are historical;
their missing-key, unknown-signature, duration-unit and unimplemented-endpoint statements do
not describe the current code. Pricing/retention/security terms were not newly account-approved.

## 2026-11-06 update

API key presence is now confirmed; authentication/permissions were not tested. Agent ID and
webhook secret remain absent; live calls remain disabled. Re-fetched public docs now document
WebRTC `token`/`connection_url` response fields, raw-body HMAC-SHA256 webhook authentication
and **seconds for both terminal event durations**. These observations supersede the corresponding
missing-key/unknown-signature/milliseconds entries in the historical table below. They do not
prove the account's live behavior. The public SDK 0.3.1 wheel was inspected without installation
or execution: async dispatch and managed-session methods exist; managed tokens are distinct
from direct dispatch tokens. Its call-details path differs from the supplied guide and needs a
contract test. Full sources, readiness and manual setup: [implementation report](VOICE_IMPLEMENTATION_REPORT.md).

Checked 2026-11-05 against the Vaani developer, pricing, API reference, webhook guide and documentation index. This is a due-diligence snapshot, not a vendor approval.

## Findings

| Area | Publicly documented | Verified for Assurely | Unknown / required before live use |
|---|---|---|---|
| API and authentication | Backend API base is `https://api.vaanivoice.ai`; API key goes in `X-API-Key`. The API reference lists `POST /api/trigger-call/` and `POST /api/webrtc/token`. | No Vaani key, agent ID or Vaani account credentials are configured. No request was sent. | Account activation, API access, account region, exact WebRTC request/response contract and short-lived token scope/expiry. |
| Browser voice | Vaani describes in-app WebRTC through LiveKit and `medium="webrtc"`; it says the server must make the request and keep the API key private. | No browser connection or real audio turn was attempted. | Supported browsers/devices, exact session token response (including any `room_name`, `connection_url`, captions URL), LiveKit client SDK/version, disconnect/reconnect semantics and captions capability. |
| Tools / shared Assurely evidence | Developer materials say custom REST tools can call application endpoints. The docs index lists agent-training and BYOL guides; BYOL is described as a streaming WebSocket server. | No Vaani tool or BYOL session was configured. Assurely has no voice-scoped tool endpoint. | Tool-call auth/signatures, schema/version contract, timeouts, retry behavior, data residency, production plan entitlement and whether BYOL can preserve the needed turn-taking while routing every answer through Assurely. |
| Languages | Vaani materials show Hindi and English agent language/voice options. | Hindi, English and Hinglish speech quality were not tested. | Hinglish/code-switch quality on the exact selected STT/LLM/TTS stack, pronunciation, language switching and the availability of a complete tested model/voice combination. Treat Hinglish as unsupported until measured. |
| Webhooks | Public guide documents lifecycle events including `call_started`, `call_ended` (duration in seconds), `call_postprocessing` (duration in milliseconds), and transfer events. It says to verify the signature contract. | No endpoint, secret or webhook delivery is configured. | Signature algorithm/header/secret provisioning, timestamp/replay contract, retry policy and the exact event payload for WebRTC calls. Do not accept unsigned events. |
| Transcripts and recordings | Docs describe post-call transcript/summary and a recording stream endpoint. Pricing page lists 30-day standard retention and enterprise zero-data-retention. | No transcript/recording was requested or received. | Whether retention options apply to this exact account and WebRTC modality, deletion guarantees, subprocessors, DPA, incident terms, exact storage location and ability to turn off recording/transcription independently. |
| Pricing | Vaani currently lists a ₹1/minute pay-as-you-go platform fee, two concurrent calls, 99.50% SLA, and separate usage for STT, model, TTS and optional components. Its estimator says browser WebRTC has no telephony charge. Taxes, provider charges, billing pulses and account rates can change the total. | No account quote or invoice was available. | Actual account plan, effective rates, billing pulse and rounding, wallet/minimums, concurrency actually provisioned, overage behavior, tax and cancellation/failed-call credits. |
| Latency | Developer page describes full-turn P50 600 ms and P90 900–1200 ms and interruption stop time typically 100–200 ms, subject to model/network/telephony. | Not measured. | Assurely's actual end-to-end P50/P95 and language-specific latency. |
| Security | Docs require server-side API key handling. | No provider security review or credentials were available. | DPA, subprocessor list, security certifications, encryption/key handling, access audit, breach notice, deletion and DPDP transfer/retention review. |

## Billing provider decision

Do not use Clerk Billing for an India-first launch: the current Clerk documentation says Billing is unavailable in India and does not provide usage-metered billing. Razorpay Subscriptions is the plausible India-first candidate because its official product page documents recurring plans and subscription lifecycle webhooks. Razorpay's current gateway pricing page lists a 2% platform fee plus applicable GST (with eligibility-based promotions); its subscriptions page separately advertises a 0.5% add-on per subscription payment. Confirm the merchant's actual offer, applicable payment-mode fees and tax treatment directly in the account before quoting a price. No plans, payment gateway, checkout, or charge have been created.

Do not set a customer price yet. The current Vaani pay-as-you-go estimate's platform fee alone is ₹1/minute; provider model/STT/TTS consumption and billing pulse are extra. A viable price requires actual Hindi/English stack rates, test invoices, taxes, failure refunds, support and margin assumptions.

## Technical spike status

The requested `POST /api/trigger-call/` `medium="webrtc"` spike is **blocked**, not complete: no Vaani credentials or agent ID are present. No provider request was made. The static docs identify WebRTC and a token endpoint, but the exact endpoint contract could not be independently established from the accessible API reference content. We will not guess the response fields or issue browser connection material until the vendor contract is verified. A local mock slice can be built without representing it as a real call.

## Sources

- [Vaani developer guide](https://www.vaani.dev/developers)
- [Vaani pricing](https://www.vaani.dev/pricing)
- [Vaani documentation index](https://docs.vaani.dev/llms.txt)
- [Vaani API reference overview](https://docs.vaani.dev/api-reference/introduction)
- [Vaani webhook guide](https://docs.vaani.dev/guides/webhook-setup)
- [Clerk Billing overview](https://clerk.com/docs/guides/billing/overview)
- [Razorpay Subscriptions](https://razorpay.com/subscriptions/)
- [Razorpay pricing](https://razorpay.com/pricing/)
