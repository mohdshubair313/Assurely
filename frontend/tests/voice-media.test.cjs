const test = require("node:test");
const assert = require("node:assert/strict");
const { VoiceMediaController, validateConnection } = require("../../artifacts/voice-media/controller.js");
const sessionId = "01a67318-7dd7-44ac-b6dd-e11bcb7add40";
const now = 1_800_000_000_000;
const connection = { sessionId, roomName: "synthetic-room", url: "wss://rtc.vaanivoice.ai", token: "synthetic-scoped-room-token-only", expiresAt: now + 60_000, synthetic: true };
const consent = { aiDisclosureAccepted: true, microphone: true, vendorProcessing: true };
const flush = () => new Promise(resolve => setImmediate(resolve));
function fixture() {
  const state = { now, authorized: true, sameSession: true, connects: 0, disconnects: 0, mic: [], listener: null, heartbeat: null, cancel: false };
  const room = {
    connect: async (url, token) => { assert.equal(url, connection.url); assert.equal(token, connection.token); state.connects++; },
    disconnect: async () => { state.disconnects++; },
    microphone: async enabled => { state.mic.push(enabled); },
    startAudio: async () => {},
    subscribe: listener => { state.listener = listener; return () => { state.listener = null; }; },
  };
  const dependencies = { createRoom: () => room, now: () => state.now,
    authorize: async id => { assert.equal(id, sessionId); return { allowed: state.authorized, sessionId: state.sameSession ? id : "wrong", roomName: connection.roomName, expiresAt: state.now + 10000 }; },
    schedule: callback => { state.heartbeat = callback; return () => { state.cancel = true; }; },
  };
  return { state, room, dependencies, controller: new VoiceMediaController(dependencies) };
}
test("rejects hostile connection material before media creation", async () => {
  for (const patch of [ { url: "ws://rtc.vaanivoice.ai" }, { url: "wss://attacker.test" }, { url: "wss://rtc.vaanivoice.ai?token=hidden" }, { synthetic: false }, { expiresAt: now - 1 }, { expiresAt: now + 301000 }, { sessionId: "invalid" }, { token: "short" } ]) {
    const f = fixture(); await f.controller.connect({ ...connection, ...patch }, consent);
    assert.equal(f.state.connects, 0); assert.equal(f.controller.getSnapshot().state, "blocked");
  }
});
test("all three explicit consents required; unauthorized server receipt cannot connect", async () => {
  for (const field of Object.keys(consent)) {
    const f = fixture(); await f.controller.connect(connection, { ...consent, [field]: false }); assert.equal(f.state.connects, 0);
  }
  const f = fixture(); f.state.authorized = false; await f.controller.connect(connection, consent); assert.equal(f.state.connects, 0);
});
test("cross-session receipt rejected without media", async () => {
  const f = fixture(); f.state.sameSession = false; await f.controller.connect(connection, consent); assert.equal(f.state.connects, 0);
});
test("authorization for a different room cannot authorize connection material", async () => {
  const f = fixture(); f.dependencies.authorize = async () => ({ allowed: true, sessionId, roomName: "different-room", expiresAt: now + 10000 });
  await f.controller.connect(connection, consent); assert.equal(f.state.connects, 0);
});
test("starts muted, explicitly enables mic, duplicate connect never duplicates dispatch", async () => {
  const f = fixture(); await f.controller.connect(connection, consent); await f.controller.connect(connection, consent);
  assert.equal(f.controller.getSnapshot().microphone, false); assert.deepEqual(f.state.mic, []); assert.equal(f.state.connects, 1);
  await f.controller.setMicrophone(true); assert.equal(f.controller.getSnapshot().microphone, true);
  await f.controller.setMicrophone(false); assert.deepEqual(f.state.mic, [true, false]); await f.controller.disconnect();
});
test("reconnect stays on same room/session, immediately mutes and needs explicit microphone resume", async () => {
  const f = fixture(); await f.controller.connect(connection, consent); await f.controller.setMicrophone(true);
  f.state.listener("reconnecting"); assert.equal(f.controller.getSnapshot().microphone, false);
  f.state.listener("connected"); await flush(); assert.equal(f.controller.getSnapshot().state, "connected");
  assert.equal(f.controller.getSnapshot().microphone, false); assert.equal(f.state.connects, 1); assert.equal(f.state.mic.at(-1), false);
  await f.controller.disconnect();
});
test("heartbeat revocation disconnects media and preserves uncertain provider status", async () => {
  const f = fixture(); await f.controller.connect(connection, consent); await f.controller.setMicrophone(true);
  f.state.authorized = false; await f.controller.checkAuthorization();
  assert.equal(f.controller.getSnapshot().state, "blocked"); assert.equal(f.state.disconnects, 1); assert.equal(f.state.cancel, true);
  assert.match(f.controller.getSnapshot().message, /provider status remains pending/);
});
test("expiry fails closed without interpreting elapsed browser time as provider settlement", async () => {
  const f = fixture(); await f.controller.connect(connection, consent); f.state.now += 60001; await f.controller.checkAuthorization();
  assert.equal(f.controller.getSnapshot().state, "blocked"); assert.equal(f.state.disconnects, 1);
});
test("local withdrawal while pending server authorization cannot later open microphone or room", async () => {
  const f = fixture(); let resolve;
  f.dependencies.authorize = () => new Promise(r => { resolve = r; });
  const pending = f.controller.connect(connection, consent); await f.controller.revokeConsent();
  resolve({ allowed: true, sessionId, roomName: connection.roomName, expiresAt: now + 10000 }); await pending;
  assert.equal(f.state.connects, 0); assert.equal(f.controller.getSnapshot().state, "blocked");
});
test("late room connect completion after local disconnect is cleaned up, never activated", async () => {
  const f = fixture(); let resolve;
  f.room.connect = () => new Promise(r => { resolve = r; });
  const pending = f.controller.connect(connection, consent); await flush(); await f.controller.disconnect(); resolve(); await pending;
  assert.equal(f.controller.getSnapshot().state, "disconnected"); assert.equal(f.controller.getSnapshot().microphone, false);
  assert.ok(f.state.disconnects >= 1);
});
test("microphone enable completing after revocation is muted again", async () => {
  const f = fixture(); let resolve;
  f.room.microphone = async enabled => { f.state.mic.push(enabled); if (enabled) await new Promise(r => { resolve = r; }); };
  await f.controller.connect(connection, consent); const pending = f.controller.setMicrophone(true); await flush();
  await f.controller.revokeConsent(); resolve(); await pending;
  assert.equal(f.controller.getSnapshot().microphone, false); assert.equal(f.state.mic.at(-1), false); assert.equal(f.state.disconnects, 1);
});
test("permission failure is safe and never reflects provider credentials/errors", async () => {
  const f = fixture(); f.room.microphone = async enabled => { if (enabled) throw new Error("secret raw provider detail"); };
  await f.controller.connect(connection, consent); await f.controller.setMicrophone(true);
  assert.equal(f.controller.getSnapshot().state, "blocked"); assert.equal(f.state.disconnects, 1);
  assert.doesNotMatch(JSON.stringify(f.controller.getSnapshot()), /secret raw|scoped-room-token/);
});
test("SDK disconnected event cleans resources; quality and autoplay are bounded safe states", async () => {
  const f = fixture(); await f.controller.connect(connection, consent);
  f.state.listener("quality", "hostile provider content"); assert.equal(f.controller.getSnapshot().quality, "unknown");
  f.state.listener("playback-blocked"); assert.equal(f.controller.getSnapshot().playbackBlocked, true);
  await f.controller.enablePlayback(); assert.equal(f.controller.getSnapshot().playbackBlocked, false);
  f.state.listener("disconnected"); await flush(); assert.equal(f.state.disconnects, 1);
  assert.match(f.controller.getSnapshot().message, /reserved usage require server confirmation/);
});
test("heartbeat network failure rejects audio even if earlier authorization succeeded", async () => {
  const f = fixture(); await f.controller.connect(connection, consent);
  f.dependencies.authorize = async () => { throw new Error("untrusted failure"); };
  await f.controller.checkAuthorization(); assert.equal(f.controller.getSnapshot().state, "blocked"); assert.equal(f.state.disconnects, 1);
});
