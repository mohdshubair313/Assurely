/* Disposable local protocol fixture; not an identity service for real users. */
if (process.env.ASSURELY_SYNTHETIC_BROWSER_TEST !== '1') throw new Error('Explicit synthetic fixture flag required');
const https = require('node:https');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '../artifacts');
const fixture = JSON.parse(fs.readFileSync(path.join(root, 'browser-fixture.json'), 'utf8'));
const key = crypto.createPrivateKey(fs.readFileSync(path.join(root, 'oidc-fixture-key.pem')));
const jwk = crypto.createPublicKey(key).export({ format: 'jwk' });
const issuer = 'https://localhost:19443';
const callback = 'http://localhost:3000/api/auth/callback';
const codes = new Map();
function json(res, status, data) { res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }); res.end(JSON.stringify(data)); }
function jwt(data) {
  const header = Buffer.from(JSON.stringify({ alg: 'RS256', kid: 'synthetic', typ: 'JWT' })).toString('base64url');
  const body = Buffer.from(JSON.stringify(data)).toString('base64url');
  const input = `${header}.${body}`;
  return input + '.' + crypto.sign('sha256', Buffer.from(input), key).toString('base64url');
}
https.createServer({ key: fs.readFileSync(path.join(root, 'oidc-fixture-key.pem')), cert: fs.readFileSync(path.join(root, 'oidc-fixture-cert.pem')) }, async (req, res) => {
  const url = new URL(req.url, issuer);
  if (url.pathname === '/.well-known/openid-configuration') return json(res, 200, {
    issuer, authorization_endpoint: issuer + '/authorize', token_endpoint: issuer + '/token', jwks_uri: issuer + '/jwks',
    response_types_supported: ['code'], grant_types_supported: ['authorization_code'], subject_types_supported: ['public'],
    id_token_signing_alg_values_supported: ['RS256'], token_endpoint_auth_methods_supported: ['none'], code_challenge_methods_supported: ['S256'],
  });
  if (url.pathname === '/jwks') return json(res, 200, { keys: [{ ...jwk, kid: 'synthetic', alg: 'RS256', use: 'sig' }] });
  if (url.pathname === '/authorize') {
    const p = url.searchParams;
    if (p.get('client_id') !== 'synthetic-browser' || p.get('redirect_uri') !== callback ||
        p.get('response_type') !== 'code' || p.get('code_challenge_method') !== 'S256' || !p.get('state') || !p.get('nonce')) return json(res, 400, { error: 'invalid_request' });
    const code = crypto.randomUUID();
    const role = (req.headers.cookie ?? '').includes('synthetic_role=advisor') ? 'advisor' : 'owner';
    codes.set(code, { challenge: p.get('code_challenge'), nonce: p.get('nonce'), role, expires: Date.now()+60000 });
    const result = new URL(callback); result.searchParams.set('code', code); result.searchParams.set('state', p.get('state'));
    res.writeHead(302, { Location: result.href }); return res.end();
  }
  if (url.pathname === '/token' && req.method === 'POST') {
    let body = ''; for await (const chunk of req) { body += chunk; if (body.length > 10000) return json(res, 413, {}); }
    const p = new URLSearchParams(body); const record = codes.get(p.get('code')); codes.delete(p.get('code'));
    if (!record || record.expires < Date.now() || p.get('redirect_uri') !== callback || p.get('client_id') !== 'synthetic-browser' ||
        p.get('grant_type') !== 'authorization_code' || crypto.createHash('sha256').update(p.get('code_verifier') ?? '').digest('base64url') !== record.challenge) return json(res, 400, { error: 'invalid_grant' });
    const now = Math.floor(Date.now()/1000);
    return json(res, 200, { access_token: fixture.tokens[record.role], token_type: 'Bearer', expires_in: 900,
      id_token: jwt({ iss: issuer, aud: 'synthetic-browser', sub: record.role === 'owner' ? '00000000-0000-4000-8000-000000000456' : '00000000-0000-4000-8000-000000000123', nonce: record.nonce, iat: now, exp: now+900 }),
    });
  }
  return json(res, 404, {});
}).listen(19443, '127.0.0.1', () => console.log('Synthetic local OIDC fixture ready'));
