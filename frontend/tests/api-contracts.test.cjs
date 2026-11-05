const { test, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const contracts = require('../../artifacts/integration-client/api-contracts.js');
const client = require('../../artifacts/integration-client/api-client.js');
const intake = require('../../artifacts/integration-client/intake.js');
const originalFetch = global.fetch;
afterEach(() => { global.fetch = originalFetch; });
const id = '00000000-0000-4000-8000-000000000456', turn = '00000000-0000-4000-8000-000000000123';
const digest = 'a'.repeat(64);
const cited = { sentences: [{ text: 'Synthetic clause.', citations: [{ source: 'Synthetic source', last_verified: '2026-11-03', references: [{ url: 'https://source.invalid/policy.pdf', pdf_page: 1, clause: 'Clause', quote: 'Synthetic quote' }] }] }] };
const message = { session_id: id, reply: 'Held for review.', delivery_hold: true, missing_fields: [], escalation: true, notification_status: 'not_configured', output: {} };
const response = (data, status = 200, headers = {}) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json', ...headers } });
test('invalid case IDs, blank/oversized questions and extra authority fields fail before network', async () => {
  let calls = 0; global.fetch = async () => { calls++; return response(message); };
  for (const [session, question] of [['-'.repeat(36), 'Question'], [id, ' '], [id, 'x'.repeat(4001)]]) await assert.rejects(client.postMessage(session, question));
  assert.throws(() => contracts.messageRequest({ session_id: id, user_message: 'Question', approved: true }));
  assert.equal(calls, 0);
});
test('malformed success payloads and a different returned session fail closed', async () => {
  for (const value of [{}, [], { ...message, session_id: turn }, { ...message, delivery_hold: 'false' }, { ...message, missing_fields: {} }]) {
    global.fetch = async () => response(value); await assert.rejects(client.postMessage(id, 'Question'));
  }
});
test('held responses discard hidden report fields', async () => {
  global.fetch = async () => response({ ...message, output: cited, draft_output: { secret: 'not for display' } });
  const result = await client.postMessage(id, 'Question'); assert.equal(result.output, null); assert.equal(result.draft_output, undefined);
});
test('report status accepts only valid explicit hold/turn/digest/status values', () => {
  const valid = { turn_id: turn, report_digest: digest, status: 'complete', delivery_hold: true };
  assert.equal(contracts.reportStatusResponse(valid).status, 'complete');
  for (const bad of [{ ...valid, status: 'approved' }, { ...valid, turn_id: 'invalid' }, { ...valid, report_digest: 'invalid' }, { ...valid, delivery_hold: false }]) assert.throws(() => contracts.reportStatusResponse(bad));
});
test('report requires every sentence citation and a valid date and safe PDF link', () => {
  assert.deepEqual(contracts.report(cited), cited);
  for (const citation of [{ source: 'Source' }, { source: 'Source', last_verified: '2026-02-31' }, { source: 'Source', last_verified: '2026-11-03', references: [{ url: 'javascript:alert(1)', pdf_page: 1, clause: 'C', quote: 'Q' }] }]) assert.throws(() => contracts.report({ sentences: [{ text: 'Claim', citations: [citation] }] }));
  assert.throws(() => contracts.report({ sentences: [{ text: 'Claim', citations: [] }] }));
});
test('release response must match the requested turn and exact report', async () => {
  const valid = { delivery_hold: false, output: cited, release_receipt: { id, turn_id: turn, report_digest: digest, advisor_event_id: id, scope: 'transaction_time_release_decision' } };
  global.fetch = async () => response(valid); assert.deepEqual(await client.releaseReport(id, turn, digest, id), cited);
  for (const bad of [{ ...valid, delivery_hold: true }, { ...valid, release_receipt: { ...valid.release_receipt, report_digest: 'b'.repeat(64) } }, { ...valid, release_receipt: { ...valid.release_receipt, turn_id: id } }, { ...valid, output: { sentences: [] } }]) {
    global.fetch = async () => response(bad); await assert.rejects(client.releaseReport(id, turn, digest, id));
  }
});
test('scenario rejects invalid dates, fractional ages, duplicate options and hidden fields', () => {
  const context = { transaction: 'issue', transaction_date: '2026-11-03', cover_basis: 'individual', selected_options: [], entry_age_years: null, residency: null, zone: null, portability: null, continuity: null };
  const build = context => ({ items: [{ publication_digest: digest, capabilities: ['coverage_options'], context }] });
  assert.equal(contracts.scenario(build(context)).items[0].context.portability, null);
  for (const changed of [{ transaction_date: '2026-02-31' }, { entry_age_years: 35.5 }, { selected_options: ['X', 'X'] }, { portability: 'no' }, { approved: true }]) assert.throws(() => contracts.scenario(build({ ...context, ...changed })));
  assert.throws(() => contracts.scenario({ items: Array.from({ length: 6 }, () => build(context).items[0]) }));
});
test('advisor requires future bounded expiry and an integer revision', () => {
  const command = { action: 'approve', request_key: id, expected_revision: 0, reason: 'Reviewed.', expires_at: new Date(Date.now() + 60000).toISOString() };
  assert.equal(contracts.decisionRequest(command).expected_revision, 0);
  for (const changed of [{ reason: ' ' }, { expected_revision: 0.5 }, { expires_at: '2020-01-01T00:00:00Z' }, { expires_at: new Date(Date.now() + 8 * 86400000).toISOString() }, { action: 'revoke' }]) assert.throws(() => contracts.decisionRequest({ ...command, ...changed }));
});
test('server errors never reflect private backend messages and writes are never retried', async () => {
  let calls = 0; global.fetch = async () => { calls++; return response({ detail: 'private-health-content' }, 500); };
  await assert.rejects(client.postMessage(id, 'Question'), error => error instanceof client.ApiError && !error.message.includes('private-health-content'));
  assert.equal(calls, 1);
});
test('429 preserves safe retry information and 401 remains identifiable', async () => {
  global.fetch = async () => response({}, 429, { 'Retry-After': '30' });
  await assert.rejects(client.reportStatus(id), error => error.status === 429 && error.retryAfter === 30);
  global.fetch = async () => response({}, 401); await assert.rejects(client.reportStatus(id), error => error.status === 401);
});
test('HTML responses, broken JSON, aborted and late-resolving requests cannot appear successful', async () => {
  global.fetch = async () => new Response('<html>Error</html>'); await assert.rejects(client.reportStatus(id));
  global.fetch = async () => new Response('{', { headers: { 'Content-Type': 'application/json' } }); await assert.rejects(client.reportStatus(id));
  const controller = new AbortController();
  global.fetch = async () => { controller.abort(); return response(message); };
  await assert.rejects(client.postMessage(id, 'Question', undefined, { signal: controller.signal }), { name: 'AbortError' });
});
test('privacy requests cannot select another user and deletion uses DELETE', async () => {
  assert.throws(() => contracts.consentRequest({ scope: 'save_profile', action: 'grant', user_id: turn }));
  assert.throws(() => contracts.consentRequest({ scope: 'unknown', action: 'grant' }));
  global.fetch = async (url, options) => { assert.equal(url, '/api/backend/profile-memory'); assert.equal(options.method, 'DELETE'); assert.deepEqual(JSON.parse(options.body), {}); return response({ user_id: id, deleted: false }); };
  assert.equal((await client.deleteProfileMemory()).deleted, false);
});
test('guided intake retains supplied values and rejects invalid household details', () => {
  const value = { adults: '2', children: '1', age: '35', city: 'tier_1', priorities: [intake.priorities[0]], budget: intake.budgets[0], cover: intake.covers[0] };
  assert.match(intake.intakeQuestion(value), /Adults to cover: 2/);
  for (const changed of [{ age: '35.5' }, { children: '-1' }, { budget: 'made-up' }, { priorities: ['made-up'] }]) assert.throws(() => intake.intakeQuestion({ ...value, ...changed }));
});
