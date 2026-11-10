const test = require("node:test");
const assert = require("node:assert/strict");
const { sessionStatus, startDevelopment, connectDevelopment, authorizeDevelopment } = require("../../artifacts/voice-next/voice/api.js");
const session = "01a67318-7dd7-44ac-b6dd-e11bcb7add40";
const value = () => ({ session_id: session, room_name: "synthetic_room", phase: "connected", state: "reserved", allowed: true,
  synthetic: true, expires_at: new Date(Date.now()+60000).toISOString(), end_requested: false, reserved_seconds: 120, consumed_seconds: 0 });
test("rejects corrupt, non-synthetic and malformed lifecycle responses", () => {
  for (const patch of [{synthetic:false},{phase:"invented"},{state:"invented"},{reserved_seconds:-1},{consumed_seconds:121},{allowed:"true"},{expires_at:"invalid"},{room_name:"room/hostile"}]) {
    assert.throws(() => sessionStatus({...value(),...patch}));
  }
});
test("start retains caller idempotency key and uses authenticated same-origin BFF", async () => {
  const original=global.fetch;
  global.fetch=async (url,options) => {
    assert.equal(url,"/api/backend/voice/development/sessions");
    assert.equal(options.credentials,"same-origin"); assert.equal(options.cache,"no-store");
    assert.deepEqual(JSON.parse(options.body),{idempotency_key:session});
    return Response.json(value());
  };
  try { assert.equal((await startDevelopment(session)).sessionId,session); }
  finally {global.fetch=original;}
});
test("only room-scoped connection material is accepted; mismatched owner session fails", async () => {
  const original=global.fetch;
  try {
    for (const patch of [{url:"wss://attacker.test"},{allowed:false},{end_requested:true},{session_id:"00000000-0000-4000-8000-000000000123"}]) {
      global.fetch=async () => Response.json({...value(),url:"wss://livekit.vaanivoice.ai",token:"synthetic.scoped.room.token",...patch});
      await assert.rejects(connectDevelopment(session));
    }
    global.fetch=async (url,options) => {
      assert.ok(url.endsWith("/authorization")); assert.equal(options.method,"GET");
      return Response.json(value());
    };
    assert.equal((await authorizeDevelopment(session)).allowed,true);
  } finally {global.fetch=original;}
});
