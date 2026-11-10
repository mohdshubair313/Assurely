/* Provider/Next boundaries are mocked explicitly; these are not live Clerk E2E tests. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const contracts = require('../../artifacts/integration-client/api-contracts.js');
const voiceCaseContracts = require('../../artifacts/integration-client/voice/case-contracts.js');
const owner = '00000000-0000-4000-8000-000000000456';
const origin = 'http://localhost:3000';

function load(file, imports, env = {}, globals = {}) {
  const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  const compiledModule = { exports: {} };
  vm.runInNewContext(code, { module: compiledModule, exports: compiledModule.exports, Buffer, URL, Request, Response,
    AbortSignal, setTimeout, clearTimeout, process: { env }, ...globals,
    require(name) { if (!(name in imports)) throw new Error('Unexpected import ' + name); return imports[name]; },
  }, { filename: file });
  return compiledModule.exports;
}

function session({ mode = 'clerk', configured = true, secret = 'synthetic-unit-only', auth } = {}) {
  return load('lib/server-session.ts', {
    'node:crypto': require('node:crypto'),
    'next/headers': { cookies: async () => { throw new Error('Clerk must not read legacy token cookies'); } },
    '@/lib/auth-config': { authMode: mode, clerkConfigured: configured },
    '@clerk/nextjs/server': { auth },
  }, { CLERK_SECRET_KEY: secret });
}

test('Clerk requests use session tokens and refresh via SDK on every request, never legacy cookies', async () => {
  let calls = 0;
  const api = session({ auth: async options => {
    assert.equal(options.acceptsToken, 'session_token');
    return { isAuthenticated: true, getToken: async () => 'synthetic-renewed-' + ++calls };
  } });
  assert.equal(await api.accessToken(), 'synthetic-renewed-1');
  assert.equal(await api.accessToken(), 'synthetic-renewed-2');
});

test('Logged-out and expired SDK sessions cannot access a backend; missing config fails closed', async () => {
  for (const state of [{ isAuthenticated: false }, { isAuthenticated: true, getToken: async () => null }]) {
    assert.equal(await session({ auth: async () => state }).accessToken(), undefined);
  }
  await assert.rejects(() => session({ configured: false }).accessToken());
  await assert.rejects(() => session({ secret: '' }).accessToken());
  await assert.rejects(() => session({ mode: 'unknown' }).accessToken());
});

function gateway(token, fetch) {
  return load('app/api/backend/[...path]/route.ts', {
    'next/server': { NextResponse: { json: (value, init) => Response.json(value, init) } },
    '@/lib/server-session': { accessToken: async () => token, sameOrigin: request => request.headers.get('origin') === origin },
    '@/lib/api-contracts': contracts,
    '@/lib/voice/case-contracts': voiceCaseContracts,
  }, { BACKEND_URL: 'http://127.0.0.1:8000', NODE_ENV: 'development' }, { fetch });
}
const context = path => ({ params: Promise.resolve({ path: path.split('/') }) });
const write = (path, value, from = origin) => new Request(origin + '/api/backend/' + path, {
  method: 'POST', headers: { Origin: from, 'Content-Type': 'application/json' }, body: JSON.stringify(value),
});
test('human-review BFF forwards only owner credentials and a validated operation key', async () => {
  const path = `sessions/${owner}/human-review`;
  let calls = 0;
  const signed = gateway('synthetic-session-token', async (url, init) => {
    calls++; assert.equal(url.pathname, `/v1/${path}`);
    assert.equal(init.headers.Authorization, 'Bearer synthetic-session-token');
    if (init.method === 'POST') assert.deepEqual(JSON.parse(init.body), { request_key: owner });
    return Response.json({ request: null });
  });
  assert.equal((await signed.GET(new Request(origin + '/api/backend/' + path), context(path))).status, 200);
  assert.equal((await signed.POST(write(path, { request_key: owner }), context(path))).status, 200);
  for (const body of [{ request_key: 'invalid' }, { request_key: owner, role: 'admin' }, { request_key: owner, user_id: owner }]) {
    assert.equal((await signed.POST(write(path, body), context(path))).status, 422);
  }
  assert.equal((await signed.POST(write(path, { request_key: owner }, 'https://foreign.invalid'), context(path))).status, 403);
  const duplicate = write(path, {});
  const duplicateRequest = new Request(duplicate.url, { method: 'POST', headers: duplicate.headers, body: `{"request_key":"${owner}","request_\\u006bey":"${owner}"}` });
  assert.equal((await signed.POST(duplicateRequest, context(path))).status, 422);
  assert.equal(calls, 2);
  const anon = gateway(undefined, async () => { throw new Error('anonymous request forwarded'); });
  assert.equal((await anon.GET(new Request(origin + '/api/backend/' + path), context(path))).status, 401);
});
test('case-binding BFF exposes only owner routes and a duplicate-safe closed command', async () => {
  const path = `voice/development/sessions/${owner}/case-binding`;
  let calls = 0;
  const signed = gateway('synthetic-session-token', async (url, init) => {
    calls++; assert.equal(init.headers.Authorization, 'Bearer synthetic-session-token');
    if (init.method === 'POST') assert.deepEqual(JSON.parse(init.body), { case_id: owner, idempotency_key: owner });
    return Response.json({});
  });
  assert.equal((await signed.POST(write(path, { case_id: owner, idempotency_key: owner }), context(path))).status, 200);
  for (const endpoint of [path, path.replace('case-binding', 'captions')]) assert.equal((await signed.GET(new Request(origin + '/api/backend/' + endpoint), context(endpoint))).status, 200);
  for (const patch of [{ user_id: owner }, { report_digest: 'a'.repeat(64) }, { approved: true }]) assert.equal((await signed.POST(write(path, { case_id: owner, idempotency_key: owner, ...patch }), context(path))).status, 422);
  const duplicate = write(path, {});
  const malformed = new Request(duplicate.url, { method: 'POST', headers: duplicate.headers, body: `{"case_id":"${owner}","case_\\u0069d":"${owner}"}` });
  assert.equal((await signed.POST(malformed, context(path))).status, 422);
  assert.equal(calls, 3);
});

test('BFF obtains owner from independently verified /me and never decodes Clerk user IDs', async () => {
  const calls = [];
  const api = gateway('synthetic-not-a-jwt', async (url, init) => {
    calls.push([url.pathname, init]);
    assert.equal(init.headers.Authorization, 'Bearer synthetic-not-a-jwt');
    return Response.json(url.pathname === '/v1/me' ? { user_id: owner } : { status: 'granted' });
  });
  const result = await api.POST(write('consent', { scope: 'save_profile', action: 'grant', purpose_version: contracts.consentVersion }), context('consent'));
  assert.equal(result.status, 200);
  assert.deepEqual(calls.map(([path]) => path), ['/v1/me', '/v1/consent']);
  assert.equal(JSON.parse(calls[1][1].body).user_id, owner);
});

test('BFF rejects anonymous requests, forged owners, roles, cross-origin writes and unlisted paths', async () => {
  const forbidden = async () => { throw new Error('Rejected request reached upstream'); };
  const anon = gateway(undefined, forbidden);
  assert.equal((await anon.GET(new Request(origin + '/api/backend/me'), context('me'))).status, 401);
  const signed = gateway('synthetic', forbidden);
  assert.equal((await signed.POST(write('consent', { scope: 'save_profile', action: 'grant', user_id: owner }), context('consent'))).status, 422);
  assert.equal((await signed.POST(write('consent', { scope: 'save_profile', action: 'grant', role: 'admin' }), context('consent'))).status, 422);
  assert.equal((await signed.POST(write('consent', {}, 'https://foreign.invalid'), context('consent'))).status, 403);
  assert.equal((await signed.POST(write('admin/users', {}), context('admin/users'))).status, 404);
});

test('Failed /me identity resolution never mutates consent or substitutes a caller token', async () => {
  let calls = 0;
  const api = gateway('server-token', async (_, init) => {
    calls++;
    assert.equal(init.headers.Authorization, 'Bearer server-token');
    return Response.json({ detail: 'private upstream detail' }, { status: 401 });
  });
  const request = write('consent', { scope: 'save_profile', action: 'revoke' });
  request.headers.set('Authorization', 'Bearer attacker-token');
  const response = await api.POST(request, context('consent'));
  assert.equal(response.status, 401);
  assert.equal(calls, 1);
  assert.doesNotMatch(await response.text(), /private upstream detail/);
});

test('voice BFF preserves empty end retries and validates optional operation keys', async () => {
  const path=`voice/sessions/${owner}/end`;
  const calls=[];
  const api=gateway('synthetic-session-token',async (url,init) => {
    calls.push(JSON.parse(init.body));return Response.json({state:'ended'});
  });
  for (const body of [{},{idempotency_key:owner}]) {
    assert.equal((await api.POST(write(path,body),context(path))).status,200);
  }
  assert.deepEqual(calls,[{},{idempotency_key:owner}]);
  for (const body of [{idempotency_key:'invalid'},{user_id:owner}]) {
    assert.equal((await api.POST(write(path,body),context(path))).status,422);
  }
  assert.equal(calls.length,2);
});
