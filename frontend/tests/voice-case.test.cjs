const { test, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const contracts = require('../../artifacts/voice-next/voice/case-contracts.js');
const api = require('../../artifacts/voice-next/voice/case-api.js');
const { CaptionDisplayController } = require('../../artifacts/voice-next/voice/caption-display.js');
const { caseBindingAttempt } = require('../../artifacts/voice-next/voice/binding-attempt.js');
const { attachCaptionLifecycle } = require('../../artifacts/voice-next/voice/caption-lifecycle.js');
const originalFetch = global.fetch;
afterEach(() => { global.fetch = originalFetch; });
const voice = '00000000-0000-4000-8000-000000000123', caseId = '00000000-0000-4000-8000-000000000456';
const key = '00000000-0000-4000-8000-000000000789';
const binding = () => ({ binding_id: key, voice_session_id: voice, case_id: caseId, turn_id: voice, report_digest: 'a'.repeat(64), requested_at: '2026-11-08T10:00:00Z', delivery_authorized: false });
function packet(now = Date.now()) {
  const reference = { url: 'https://source.invalid/synthetic.pdf', pdf_page: 2, clause: 'Synthetic condition', quote: 'Synthetic complete condition.' };
  return { ...binding(), expires_at: new Date(now + 9999).toISOString(), safe_for_display: true,
    caption_scope: 'authorized_report_excerpt', realtime_transcript: false, external_speech_enabled: false,
    sentences: [{ id: 'sentence-1', index: 0, text: 'Synthetic full sentence with its condition.', citations: [{ id: 'synthetic-source', source: 'Synthetic source', url: reference.url, last_verified: new Date(now).toISOString().slice(0, 10), expires_at: new Date(now + 86400000).toISOString(), references: [reference], applicability_evidence: [], condition_evidence: [] }] }] };
}
const settle = () => new Promise(resolve => setImmediate(resolve));
test('binding command rejects extra authority and duplicate escaped JSON members', () => {
  const valid = { case_id: caseId, idempotency_key: key };
  assert.deepEqual(contracts.bindCaseJSONCommand(JSON.stringify(valid)), valid);
  assert.deepEqual(contracts.bindCaseJSONCommand(`{"idempotency_key":"${key}","case_id":"${caseId}"}`), valid);
  for (const field of ['owner_id', 'report_digest', 'turn_id', 'approved', 'release_receipt']) assert.throws(() => contracts.bindCaseCommand({ ...valid, [field]: key }));
  for (const raw of [`{"case_id":"${caseId}","case_\\u0069d":"${caseId}"}`, `{"case_id":"${caseId}","idempotency_key":"${key}","idempotency_key":"${key}"}`, '{"case_id":{},"idempotency_key":"invalid"}']) assert.throws(() => contracts.bindCaseJSONCommand(raw));
});
test('uncertain binding keys survive reload and reject silent case/account mixing', () => {
  const rows = new Map(), storage = { getItem: path => rows.get(path) ?? null, setItem: (path, value) => rows.set(path, value) };
  const first = caseBindingAttempt('synthetic-owner', voice, caseId, storage, () => key);
  assert.deepEqual(caseBindingAttempt('synthetic-owner', voice, caseId, storage, () => { throw new Error('new key'); }), first);
  assert.throws(() => caseBindingAttempt('synthetic-owner', voice, key, storage));
  assert.equal(caseBindingAttempt('different-owner', voice, caseId, storage, () => voice).idempotency_key, voice);
  assert.throws(() => caseBindingAttempt('blocked-owner', voice, caseId, { getItem: () => null, setItem: () => { throw new Error('blocked storage'); } }, () => key));
});
test('companion preserves full condition and source references without claiming spoken output', () => {
  const input = packet(), decoded = contracts.captionPacket(input, binding());
  assert.equal(decoded.sentences[0].text, input.sentences[0].text);
  assert.deepEqual(decoded.sentences[0].citations[0].references, input.sentences[0].citations[0].references);
  assert.equal(decoded.realtime_transcript, false); assert.equal(decoded.external_speech_enabled, false);
});
test('caption decode rejects mismatched binding, unsafe output states, bad sequence and overlong leases', () => {
  const now = Date.now();
  for (const patch of [{ case_id: voice }, { voice_session_id: caseId }, { report_digest: 'b'.repeat(64) }, { turn_id: caseId }, { binding_id: voice }, { delivery_authorized: true }, { safe_for_display: false }, { realtime_transcript: true }, { external_speech_enabled: true }, { caption_scope: 'live_transcript' }, { expires_at: new Date(now - 1).toISOString() }, { expires_at: new Date(now + 60000).toISOString() }]) assert.throws(() => contracts.captionPacket({ ...packet(now), ...patch }, binding(), now));
  const invalid = packet(now); invalid.sentences[0].index = 1;
  assert.throws(() => contracts.captionPacket(invalid, binding(), now));
});
test('every displayed sentence needs dated unexpired evidence and a safe source link', () => {
  for (const change of [c => { c.references[0].url = 'javascript:alert(1)'; }, c => { c.references[0].url = 'https://source.invalid:0/document'; }, c => { c.references[0].url = 'https://source.invalid/back\\slash'; }, c => { c.url = ' https://source.invalid/document'; }, c => { c.url = 'https://private:token@source.invalid'; }, c => { c.references = []; }, c => { c.last_verified = '2099-01-01'; }, c => { c.expires_at = '2020-01-01T00:00:00Z'; }]) {
    const value = packet(); change(value.sentences[0].citations[0]); assert.throws(() => contracts.captionPacket(value, binding()));
  }
  const uncited = packet(); uncited.sentences[0].citations = [];
  assert.throws(() => contracts.captionPacket(uncited, binding()));
});
test('binding POST retains caller key, checks exact returned case and never retries uncertain writes', async () => {
  let calls = 0;
  global.fetch = async (url, options) => {
    calls++; assert.equal(url, `/api/backend/voice/development/sessions/${voice}/case-binding`);
    assert.deepEqual(JSON.parse(options.body), { case_id: caseId, idempotency_key: key });
    assert.equal(options.credentials, 'same-origin'); return Response.json(binding());
  };
  assert.equal((await api.bindVoiceCase(voice, caseId, key)).case_id, caseId); assert.equal(calls, 1);
  global.fetch = async () => Response.json({ ...binding(), case_id: voice });
  await assert.rejects(api.bindVoiceCase(voice, caseId, key));
  calls = 0; global.fetch = async () => { calls++; throw new Error('uncertain network'); };
  await assert.rejects(api.bindVoiceCase(voice, caseId, key)); assert.equal(calls, 1);
});
test('case reads are same-voice scoped, GET-only and held errors never reveal upstream report text', async () => {
  global.fetch = async (url, options) => { assert.equal(options.method, 'GET'); assert.ok(url.endsWith('/captions')); return Response.json(packet()); };
  assert.equal((await api.readReviewedCaptions(binding())).sentences.length, 1);
  global.fetch = async () => Response.json({ ...binding(), voice_session_id: caseId });
  await assert.rejects(api.readCaseBinding(voice));
  global.fetch = async () => Response.json({ detail: 'private medical content' }, { status: 409 });
  await assert.rejects(api.readReviewedCaptions(binding()), error => !error.message.includes('private medical'));
});
test('display controller clears on stop and ignores late authorization responses', async () => {
  let finish, cancelled = false;
  const display = new CaptionDisplayController(binding(), { read: () => new Promise(resolve => { finish = resolve; }), schedule: () => () => { cancelled = true; } });
  display.start(); assert.equal(display.getSnapshot().state, 'checking');
  display.stop(); finish(packet()); await settle();
  assert.equal(display.getSnapshot().packet, null); assert.equal(display.getSnapshot().state, 'idle'); assert.equal(cancelled, true);
});
test('blurred, hidden or offline hosts never resume private text until focus and fresh authorization return', async () => {
  const documentEvents = new EventTarget(), windowEvents = new EventTarget();
  let focused = true, visible = true, online = true, reads = 0;
  const display = new CaptionDisplayController(binding(), { read: async () => { reads++; return packet(); }, schedule: () => () => {} });
  const detach = attachCaptionLifecycle(display, { documentEvents, windowEvents, focused: () => focused, visible: () => visible, online: () => online });
  await settle(); assert.equal(reads, 1); assert.ok(display.getSnapshot().packet);
  focused = false; windowEvents.dispatchEvent(new Event('blur')); assert.equal(display.getSnapshot().packet, null);
  online = false; windowEvents.dispatchEvent(new Event('offline'));
  online = true; windowEvents.dispatchEvent(new Event('online'));
  documentEvents.dispatchEvent(new Event('visibilitychange')); await settle();
  assert.equal(reads, 1); assert.equal(display.getSnapshot().packet, null);
  focused = true; windowEvents.dispatchEvent(new Event('focus')); await settle(); assert.equal(reads, 2);
  visible = false; documentEvents.dispatchEvent(new Event('visibilitychange')); assert.equal(display.getSnapshot().packet, null);
  visible = true; documentEvents.dispatchEvent(new Event('visibilitychange')); await settle(); assert.equal(reads, 3);
  detach(); assert.equal(display.getSnapshot().packet, null);
  windowEvents.dispatchEvent(new Event('focus')); await settle(); assert.equal(reads, 3);
});
test('periodic GET removes old content before checking a newer delivery hold', async () => {
  let now = Date.now(), tick, reads = 0;
  const display = new CaptionDisplayController(binding(), { now: () => now, schedule: fn => { tick = fn; return () => {}; }, read: async () => { if (reads++) throw new Error('new human request'); return packet(now); } });
  display.start(); await settle(); assert.ok(display.getSnapshot().packet);
  now += 4000; tick(); assert.equal(display.getSnapshot().packet, null); await settle();
  assert.equal(display.getSnapshot().state, 'blocked'); display.stop();
});
test('expired or hanging reads cannot extend display authority or revive a stopped view', async () => {
  let now = Date.now(), tick, calls = 0, pendingSignal;
  const display = new CaptionDisplayController(binding(), { now: () => now, schedule: fn => { tick = fn; return () => {}; }, read: async (_, signal) => { if (!calls++) return packet(now); pendingSignal = signal; return new Promise(() => {}); } });
  display.start(); await settle(); now += 4000; tick(); await settle();
  assert.equal(display.getSnapshot().packet, null);
  now += 8000; tick(); assert.equal(pendingSignal.aborted, true); assert.equal(display.getSnapshot().packet, null);
  display.stop();
});
