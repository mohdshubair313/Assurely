const { test, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const { activityRecap, readActivityRecap } = require('../../artifacts/voice-next/voice/activity.js');
const { ActivityRecapController } = require('../../artifacts/voice-next/voice/activity-display.js');
const { attachCaptionLifecycle } = require('../../artifacts/voice-next/voice/caption-lifecycle.js');
const originalFetch = global.fetch;
afterEach(() => { global.fetch = originalFetch; });
const voice = '00000000-0000-4000-8000-000000000123';
const caseId = '00000000-0000-4000-8000-000000000456';
const bindingId = '00000000-0000-4000-8000-000000000789';
const settle = () => new Promise(resolve => setImmediate(resolve));
function packet(now = Date.now(), report = true) {
  const stamp = new Date(now).toISOString(), expiry = new Date(now + 9000).toISOString();
  const reference = { url: 'https://source.invalid/synthetic.pdf', pdf_page: 2, clause: 'Synthetic scope', quote: 'Only this complete synthetic condition applies.' };
  return { kind: 'voice_session_activity_recap', voice_session_id: voice, session_state: 'ended',
    generated_at: stamp, display_expires_at: expiry, transcript_stored: false, audio_delivery_verified: false,
    events: [{ response_id: 1, intent: report ? 'report_read' : 'unsupported', status: 'response_sent', answer_kind: report ? 'report' : 'operational', created_at: stamp, completed_at: stamp }],
    report_availability: report ? 'available' : 'not_sent', reviewed_report: report ? {
      binding_id: bindingId, case_id: caseId, turn_id: voice, report_digest: 'a'.repeat(64), authorized_at: stamp,
      display_expires_at: expiry, sentences: [{ id: 'sentence-1', index: 0, text: 'Synthetic sentence, only when the complete condition applies.',
        citations: [{ id: 'synthetic-source', source: 'Synthetic fixture source', url: reference.url,
          last_verified: stamp.slice(0, 10), expires_at: new Date(now + 86400000).toISOString(),
          references: [reference], applicability_evidence: [], condition_evidence: [] }] }] } : null };
}

test('activity preserves complete conditional report and references without claiming audible delivery', () => {
  const value = packet(), result = activityRecap(value, voice);
  assert.equal(result.reviewed_report.sentences[0].text, value.reviewed_report.sentences[0].text);
  assert.deepEqual(result.reviewed_report.sentences[0].citations, value.reviewed_report.sentences[0].citations);
  assert.equal(result.audio_delivery_verified, false); assert.equal(result.transcript_stored, false);
});

test('receipt states distinguish uncertain send, unsupported request and pending work', () => {
  const now = Date.now(), value = packet(now, false), stamp = value.generated_at;
  value.events = [
    { response_id: 1, intent: 'report_read', status: 'delivery_uncertain', answer_kind: 'report', created_at: stamp, completed_at: null },
    { response_id: 2, intent: 'unsupported', status: 'response_sent', answer_kind: 'operational', created_at: stamp, completed_at: stamp },
    { response_id: 3, intent: 'report_read', status: 'pending', answer_kind: null, created_at: stamp, completed_at: null },
    { response_id: 4, intent: 'report_read', status: 'interrupted', answer_kind: null, created_at: stamp, completed_at: null },
    { response_id: 5, intent: 'report_read', status: 'failed', answer_kind: null, created_at: stamp, completed_at: null },
  ];
  assert.equal(activityRecap(value, voice, now).events.length, 5);
  assert.equal(activityRecap(value, voice, now).reviewed_report, null);
});

test('wrong voice, unknown fields, raw content, audio assertions and invalid lifecycle are rejected', () => {
  for (const patch of [{ voice_session_id: caseId }, { transcript_stored: true }, { audio_delivery_verified: true },
    { session_state: 'provider-approved' }, { transcript: 'private health words' }, { owner_id: caseId }, { usage_seconds: 10 }]) {
    assert.throws(() => activityRecap({ ...packet(), ...patch }, voice));
  }
  const value = packet(); value.events[0].content = 'private speech';
  assert.throws(() => activityRecap(value, voice));
});

test('report content requires a matching factual sent receipt and available state', () => {
  const noReceipt = packet(); noReceipt.events = [];
  assert.throws(() => activityRecap(noReceipt, voice));
  const uncertain = packet(); uncertain.events[0].status = 'delivery_uncertain'; uncertain.events[0].completed_at = null;
  assert.throws(() => activityRecap(uncertain, voice));
  for (const state of ['not_sent', 'unavailable']) {
    assert.throws(() => activityRecap({ ...packet(), report_availability: state }, voice));
  }
  const held = packet(); held.reviewed_report = null; held.report_availability = 'unavailable';
  assert.equal(activityRecap(held, voice).reviewed_report, null);
});

test('duplicate or reordered response IDs, fabricated statuses and event overflow fail closed', () => {
  for (const mutate of [
    v => { v.events.push({ ...v.events[0] }); },
    v => { v.events[0].response_id = 0; },
    v => { v.events[0].response_id = 2147483648; },
    v => { v.events[0].status = 'audio_verified'; },
    v => { v.events[0].intent = 'unsupported'; },
    v => { v.events[0].answer_kind = null; },
    v => { v.events = Array.from({ length: 129 }, (_, i) => ({ ...v.events[0], response_id: i + 1 })); },
  ]) { const value = packet(); mutate(value); assert.throws(() => activityRecap(value, voice)); }
});

test('expired, overlong and malformed presentation leases cannot display report text', () => {
  const now = Date.now();
  for (const patch of [{ display_expires_at: new Date(now - 1).toISOString() },
    { display_expires_at: new Date(now + 10001).toISOString() },
    { generated_at: new Date(now + 3000).toISOString() }, { generated_at: '2026-02-31T00:00:00Z' }]) {
    assert.throws(() => activityRecap({ ...packet(now), ...patch }, voice, now));
  }
  const mismatch = packet(now); mismatch.reviewed_report.display_expires_at = new Date(now + 8000).toISOString();
  assert.throws(() => activityRecap(mismatch, voice, now));
});

test('unsafe or expired source references and uncited sentences fail closed', () => {
  for (const change of [
    c => { c.references[0].url = 'javascript:alert(1)'; },
    c => { c.references[0].url = 'https://private:secret@source.invalid'; },
    c => { c.references = []; }, c => { c.last_verified = '2099-01-01'; },
    c => { c.expires_at = '2020-01-01T00:00:00Z'; },
  ]) { const value = packet(); change(value.reviewed_report.sentences[0].citations[0]); assert.throws(() => activityRecap(value, voice)); }
  const missing = packet(); missing.reviewed_report.sentences[0].citations = [];
  assert.throws(() => activityRecap(missing, voice));
});

test('activity API is same-origin GET, abortable, voice-scoped and redacts upstream errors', async () => {
  const controller = new AbortController(); let called = 0;
  global.fetch = async (url, options) => {
    called++; assert.equal(url, `/api/backend/voice/development/sessions/${voice}/activity-recap`);
    assert.equal(options.method, 'GET'); assert.equal(options.credentials, 'same-origin');
    assert.equal(options.cache, 'no-store'); assert.ok(options.signal);
    return Response.json(packet());
  };
  assert.equal((await readActivityRecap(voice, controller.signal)).voice_session_id, voice);
  assert.equal(called, 1);
  global.fetch = async () => Response.json({ ...packet(), voice_session_id: caseId });
  await assert.rejects(readActivityRecap(voice));
  global.fetch = async () => Response.json({ detail: 'private medical words' }, { status: 409 });
  await assert.rejects(readActivityRecap(voice), e => !e.message.includes('private medical'));
  controller.abort(); await assert.rejects(readActivityRecap(voice, controller.signal));
});

test('stopped recap controller aborts work and ignores late private responses', async () => {
  let finish, signal, cancelled = false;
  const display = new ActivityRecapController(voice, { read: (_, s) => { signal = s; return new Promise(resolve => { finish = resolve; }); }, schedule: () => () => { cancelled = true; } });
  display.start(); assert.equal(display.getSnapshot().state, 'checking');
  display.stop(); assert.equal(signal.aborted, true); finish(packet()); await settle();
  assert.equal(display.getSnapshot().packet, null); assert.equal(display.getSnapshot().state, 'idle'); assert.equal(cancelled, true);
});

test('periodic recap authorization clears old material before new holds or consent failures', async () => {
  let now = Date.now(), tick, calls = 0;
  const display = new ActivityRecapController(voice, { now: () => now, schedule: fn => { tick = fn; return () => {}; },
    read: async () => { if (calls++) throw new Error('summary consent revoked'); return packet(now); } });
  display.start(); await settle(); assert.ok(display.getSnapshot().packet);
  now += 4000; tick(); assert.equal(display.getSnapshot().packet, null); await settle();
  assert.equal(display.getSnapshot().state, 'blocked'); display.stop();
});

test('hanging refresh cannot extend an earlier recap lease', async () => {
  let now = Date.now(), tick, calls = 0, signal;
  const display = new ActivityRecapController(voice, { now: () => now, schedule: fn => { tick = fn; return () => {}; },
    read: async (_, s) => { if (!calls++) return packet(now); signal = s; return new Promise(() => {}); } });
  display.start(); await settle(); now += 4000; tick(); await settle();
  assert.equal(display.getSnapshot().packet, null);
  now += 8000; tick(); assert.equal(signal.aborted, true); assert.equal(display.getSnapshot().state, 'blocked'); display.stop();
});

test('blur, hidden and offline lifecycle clears recaps until fresh focus authorization', async () => {
  const documentEvents = new EventTarget(), windowEvents = new EventTarget();
  let focused = true, online = true, visible = true, reads = 0;
  const display = new ActivityRecapController(voice, { read: async () => { reads++; return packet(); }, schedule: () => () => {} });
  const detach = attachCaptionLifecycle(display, { documentEvents, windowEvents, focused: () => focused, online: () => online, visible: () => visible });
  await settle(); assert.equal(reads, 1);
  focused = false; windowEvents.dispatchEvent(new Event('blur')); assert.equal(display.getSnapshot().packet, null);
  online = false; windowEvents.dispatchEvent(new Event('offline')); online = true; windowEvents.dispatchEvent(new Event('online')); await settle();
  assert.equal(reads, 1);
  focused = true; windowEvents.dispatchEvent(new Event('focus')); await settle(); assert.equal(reads, 2);
  visible = false; documentEvents.dispatchEvent(new Event('visibilitychange')); assert.equal(display.getSnapshot().packet, null);
  detach(); assert.equal(display.getSnapshot().state, 'idle');
});
