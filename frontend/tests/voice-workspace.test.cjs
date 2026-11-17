const { test, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const { workspaceStorageKeys, probeMicrophone, currentStep, WorkspaceLifetime } = require('../../artifacts/voice-next/voice/workspace-lifetime.js');
const { startDevelopment, connectDevelopment } = require('../../artifacts/voice-next/voice/api.js');
const originalFetch = global.fetch;
afterEach(() => { global.fetch = originalFetch; });

test('different accounts cannot share voice recovery or uncertain start keys', () => {
  const first = workspaceStorageKeys('user_synthetic_A'), second = workspaceStorageKeys('user_synthetic_B');
  assert.notEqual(first.session, second.session);
  assert.notEqual(first.attempt, second.attempt);
  assert.notEqual(first.session, 'assurely-synthetic-voice-session');
  assert.deepEqual(first, workspaceStorageKeys('user_synthetic_A'));
  assert.throws(() => workspaceStorageKeys(''));
});

test('permission resolving after account exit always closes microphone tracks', async () => {
  const controller = new AbortController(); let resolve, stopped = 0, grants = 0;
  const pending = probeMicrophone(controller.signal, () => new Promise(done => { resolve = done; })).then(() => { grants++; });
  controller.abort(); resolve({ getTracks: () => [{ stop: () => { stopped++; } }, { stop: () => { stopped++; } }] });
  await assert.rejects(pending, { name: 'AbortError' });
  assert.equal(stopped, 2); assert.equal(grants, 0);
});

test('an already closed account never opens a microphone probe', async () => {
  const controller = new AbortController(); controller.abort(); let probes = 0;
  await assert.rejects(probeMicrophone(controller.signal, async () => { probes++; }), { name: 'AbortError' });
  assert.equal(probes, 0);
});

test('account exit after first side effect prevents the next consent or dispatch stage', async () => {
  const controller = new AbortController(); let dispatches = 0, resolve;
  const pending = (async () => {
    await currentStep(controller.signal, () => new Promise(done => { resolve = done; }));
    await currentStep(controller.signal, async () => { dispatches++; });
  })();
  controller.abort(); resolve('first side effect may already have committed');
  await assert.rejects(pending, { name: 'AbortError' }); assert.equal(dispatches, 0);
});

test('closed workspace signals prevent start and connect network requests', async () => {
  const controller = new AbortController(); controller.abort(); let requests = 0;
  global.fetch = async () => { requests++; throw new Error('must not run'); };
  const id = '00000000-0000-4000-8000-000000000123';
  await assert.rejects(startDevelopment(id, { signal: controller.signal }), { name: 'AbortError' });
  await assert.rejects(connectDevelopment(id, { signal: controller.signal }), { name: 'AbortError' });
  assert.equal(requests, 0);
});

test('effect reactivation fences prior asynchronous work without disabling the current workspace', async () => {
  const lifetime = new WorkspaceLifetime(), first = lifetime.activate();
  first.abort();
  const second = lifetime.activate();
  assert.equal(first.signal.aborted, true); assert.equal(second.signal.aborted, false);
  assert.equal(lifetime.signal, second.signal);
  await assert.rejects(currentStep(first.signal, async () => 'stale'), { name: 'AbortError' });
  assert.equal(await currentStep(second.signal, async () => 'current'), 'current');
});
