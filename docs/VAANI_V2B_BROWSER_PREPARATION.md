# V2b browser media preparation

**2026-11-08 implementation update:** managed lifecycle APIs/worker, mounted private LiveKit
development UI, current-report/follow-up evidence tools, consented encrypted report excerpts,
signed test billing and gated test-period spending/rollover are implemented. Customer calls
and paid billing remain disabled. This does not close live-provider or all V3?V5 acceptance.
The earlier 401/invalid-agent and unmounted-control statements are historical; account reads
passed on November 7. See [the phase implementation checkpoint](VAANI_PHASES_IMPLEMENTATION_20261108.md)
for exact completed work, tests, deviations and remaining software/approval gates.


Checked 2026-11-07. This is independent browser implementation, **not live-provider acceptance**.
Customer voice calls, paid billing and existing mock behavior are unchanged.

## Implemented

- Pinned official `livekit-client` **2.23.0** and a small adapter in
  `frontend/lib/voice/livekit-room.ts`. It connects a supplied scoped room token, attaches
  remote audio, handles autoplay restrictions, monitors local connection quality, bounds
  SDK reconnect attempts, and disconnects with local track cleanup. It never calls Vaani
  REST, receives BYOL credentials or requests camera/screen access.
- A testable browser-media controller in `frontend/lib/voice/controller.ts`. A connection
  must have an exact session UUID, synthetic marker, bounded room name, scoped token,
  recognized Vaani WSS hostname and expiry within five minutes. Credentials remain in
  controller memory, are cleared on disconnect, and never enter logs/browser storage/URLs.
  The media URL itself must contain no query token or embedded credentials.
- Explicit AI-disclosure, microphone and vendor-processing consent guards. Initial connection
  leaves the microphone muted. Only an explicit enable action requests microphone permission.
  Server authorization is checked before connection, after connection, before microphone enable,
  every five seconds, and after SDK reconnection. Receipts must bind both session and room.
- Reconnect uses the existing SDK room; it never dispatches a replacement call. Reconnect
  immediately mutes the microphone, rechecks authorization, and requires an explicit microphone
  resume. Permission failure, expired material, failed authorization/network checks and consent
  withdrawal close local audio. Asynchronous connect/microphone completions cannot reactivate
  an abandoned controller generation. A late successful operation is cleaned up again.
- An accessible reusable CreateUI `VoiceAudioControls` component with AI disclosure, connection
  and quality status, guarded connect, microphone mute/enable, autoplay permission action and
  explicitly local disconnect. Buttons and status wrap for narrower layouts. No new public route
  mounts it. Existing `VoiceDemo` remains honestly text-only and does not open a microphone.

The controller has **no** API for entitlement reservation, ledger mutation, report approval,
provider termination or settlement. Browser/BYOL disconnect is never treated as an ended provider
call, never releases reserved seconds and never infers usage from a browser timer.

## Integration contract still required

The caller must construct a stable controller using an authenticated `authorize(sessionId)`
callback, plus `createLiveKitRoom(audioContainer)`. This callback is an injected contract,
**not an invented or implemented backend route**. It must freshly validate the verified owner,
synthetic allowlist, exact provider-room binding, current voice-purpose consents, open authorized
session and authorization deadline. Its response is `{ sessionId, roomName, allowed, expiresAt }`
with numeric epoch-millisecond expiry. A five-second polling interval is a local defense;
server-side BYOL revocation and termination remain authoritative.

Future server-issued `VoiceConnection` material is `{ sessionId, roomName, url, token,
expiresAt, synthetic: true }`. The token must grant only the intended room/media privileges;
client field validation is not a replacement for server authorization or scoped vendor grants.
No token-minting endpoint, dispatch endpoint or automatic token refresh was added. Reconnecting
with expired material fails closed; a future refresh must preserve the same session/room and
must not reserve/dispatch again. The current adapter accepts only the two existing verified
Vaani connection hostnames; a different genuine response requires reviewed contract changes.

Parent UI must record real microphone/vendor consent on the server before passing affirmative
consent props. On revocation it must call the durable server workflow and request provider
termination/reconciliation separately. Passing false props or unmounting stops local media,
but is not evidence that server revocation or provider termination succeeded. Secrets/connection
material must not be supplied in rendered HTML or server/client-component serialization.

## Validation

- `npm run test:voice-media`: **14 passed** using injected synthetic room/authorization
  interfaces. Covers hostile URLs/tokens/expiry, all three consents, denied/mismatched owner
  receipt/session/room, duplicate connect, initially muted capture, explicit microphone enable,
  same-room reconnect with muted resume, heartbeat denial/expiry/network failure, withdrawal
  while authorizing, late room connection, late microphone enable, microphone denial, autoplay,
  safe quality labels and SDK disconnect cleanup. These are mock media tests, not real audio.
- Existing `npm run test:contracts`: **23 passed**.
- Full `npx tsc --noEmit`, targeted ESLint for all three new TypeScript/TSX files, and
  production `npm run build`: **passed**. Build still lists the existing `/voice-demo` route;
  it does not expose or enable the new controls.
- Dependency installation added 13 packages. Full npm audit reports **8 moderate** findings
  in the existing ESLint/TypeScript-ESLint/minimatch development-tooling chain. None names
  LiveKit or its newly added packages. Runtime-only `npm audit --omit=dev` reports **0**
  vulnerabilities. No blanket dependency upgrade/downgrade was applied.
  Audit receipts: `artifacts/vaani-v2b-npm-audit.json` and
  `artifacts/vaani-v2b-npm-runtime-audit.json`.

## Remaining acceptance gates

**NOT IMPLEMENTED:** customer mounting, authenticated scoped-token delivery and refresh,
real dispatch-to-binding orchestration, server-authorized browser reconnect endpoint,
provider hard termination and duration-cap evidence, server consent-stop propagation,
device selection, real summaries or subscriptions. The reusable media controls do not
independently fulfill these server/product requirements.

**BLOCKED / NOT VERIFIED:** genuine Vaani API/owned agent acceptance, public staging gates,
vendor token grants, actual browser media interoperability, echo/latency/network changes,
mobile/device/microphone accessibility behavior, browser visual verification, language quality,
audio playback and termination. No real microphone, customer data, synthetic provider call or
paid interaction was used to produce these test results. Unmounted controls have no visual
acceptance claim. Once dispatch/binding/termination and current release gates pass, mount this
only in an allowlisted synthetic staging journey and collect actual browser/provider evidence.

Official contracts checked:
[LiveKit connection and reconnect lifecycle](https://docs.livekit.io/intro/basics/connect/),
[room events and connection quality](https://docs.livekit.io/intro/basics/rooms-participants-tracks/webhooks-events/),
[JavaScript Room API](https://docs.livekit.io/reference/client-sdk-js/classes/Room.html),
[microphone controls](https://docs.livekit.io/reference/client-sdk-js/classes/LocalParticipant.html).
