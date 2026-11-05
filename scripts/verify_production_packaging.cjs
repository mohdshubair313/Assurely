// Disposable packaging checks, never production service/account verification.
if (process.env.ASSURELY_SYNTHETIC_DEPLOY_TEST !== '1') throw new Error('Explicit synthetic flag required');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const https = require('node:https');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const output = path.join(root, 'artifacts', 'packaging');
const network = 'assurely-packaging-test';
const names = ['assurely-packaging-ingress', 'assurely-packaging-frontend', 'assurely-packaging-stub'];
const gateway = 'synthetic-packaging-only-gateway-key-20261103';
const created = [];
function docker(...args) { return execFileSync('docker', args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim(); }
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function main() {
  // Refuse to collide with an existing resource, including a previous incomplete run.
  for (const name of names) assert(!docker('ps', '-a', '--filter', `name=^/${name}$`, '--format', '{{.Names}}'));
  assert(!docker('network', 'ls', '--filter', `name=^${network}$`, '--format', '{{.Name}}'));
  await fs.mkdir(output, { recursive: true });
  const temporary = ['cert.pem', 'key.pem', 'stub.py'];
  let networkCreated = false;
  try {
    docker('run', '--rm', '--mount', `type=bind,source=${output},target=/out`, '--entrypoint', 'python',
      'insuranceai-api:durable-test', '-c', `
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from datetime import datetime, timedelta, UTC
from pathlib import Path
k=rsa.generate_private_key(public_exponent=65537,key_size=2048)
n=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'assurely.local')])
c=(x509.CertificateBuilder().subject_name(n).issuer_name(n).public_key(k.public_key())
.serial_number(x509.random_serial_number()).not_valid_before(datetime.now(UTC)-timedelta(minutes=1))
.not_valid_after(datetime.now(UTC)+timedelta(hours=1))
.add_extension(x509.SubjectAlternativeName([x509.DNSName('assurely.local')]),False)
.sign(k,hashes.SHA256()))
Path('/out/cert.pem').write_bytes(c.public_bytes(serialization.Encoding.PEM))
Path('/out/key.pem').write_bytes(k.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))`);
    await fs.writeFile(path.join(output, 'stub.py'), `from http.server import BaseHTTPRequestHandler, HTTPServer
import json, os
class Handler(BaseHTTPRequestHandler):
 def do_POST(self):
  self.rfile.read(int(self.headers.get('Content-Length',0)))
  body=json.dumps({'gateway_valid':self.headers.get('X-Assurely-Gateway-Key')==os.environ['EXPECTED_GATEWAY'],'bearer_absent':not self.headers.get('Authorization')}).encode()
  self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)
 def log_message(self,*args): pass
HTTPServer(('0.0.0.0',8000),Handler).serve_forever()
`);
    docker('network', 'create', network); networkCreated = true;
    docker('run', '-d', '--name', names[2], '--network', network, '--network-alias', 'api',
      '-e', `EXPECTED_GATEWAY=${gateway}`, '--mount', `type=bind,source=${output},target=/fixture,readonly`,
      '--entrypoint', 'python', 'insuranceai-api:durable-test', '/fixture/stub.py'); created.push(names[2]);
    docker('run', '-d', '--name', names[1], '--network', network, '--network-alias', 'frontend',
      '--read-only', '--tmpfs', '/tmp:mode=1777', '-e', 'APP_ORIGIN=https://assurely.local',
      '-e', 'BACKEND_URL=http://api:8000', '-e', 'BACKEND_PRIVATE_NETWORK=1',
      '-e', `BACKEND_GATEWAY_TOKEN=${gateway}`, 'assurely-frontend:release'); created.push(names[1]);
    docker('run', '-d', '--name', names[0], '--network', network, '--user', '101:101', '--read-only',
      '--tmpfs', '/etc/nginx/conf.d:uid=101,gid=101,mode=0700',
      '--tmpfs', '/var/cache/nginx:uid=101,gid=101,mode=0700', '--tmpfs', '/var/run:uid=101,gid=101,mode=0700',
      '-p', '127.0.0.1:14443:8443', '-e', 'PUBLIC_HOST=assurely.local', '-e', 'NGINX_ENVSUBST_FILTER=^PUBLIC_HOST$',
      '--mount', `type=bind,source=${path.join(root, 'deploy', 'nginx.conf.template')},target=/etc/nginx/templates/default.conf.template,readonly`,
      '--mount', `type=bind,source=${path.join(output, 'cert.pem')},target=/run/secrets/tls_cert,readonly`,
      '--mount', `type=bind,source=${path.join(output, 'key.pem')},target=/run/secrets/tls_key,readonly`,
      'nginx:stable-alpine'); created.push(names[0]);
    const ca = await fs.readFile(path.join(output, 'cert.pem'));
    function request(urlPath, body, extra = {}) {
      return new Promise((resolve, reject) => {
        const req = https.request({ hostname: '127.0.0.1', port: 14443, servername: 'assurely.local', ca,
          path: urlPath, method: body === undefined ? 'GET' : 'POST', headers: {
            Host: 'assurely.local', Origin: 'https://assurely.local', 'Content-Type': 'application/json', ...extra,
          } }, res => { let text = ''; res.on('data', chunk => { text += chunk; });
            res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, text })); });
        req.setTimeout(10000, () => req.destroy(new Error('Probe timeout')));
        req.on('error', reject); req.end(body);
      });
    }
    let landing;
    for (let attempt = 0; attempt < 30; attempt++) {
      try { landing = await request('/'); if (landing.status === 200) break; } catch {}
      await delay(500);
    }
    assert.equal(landing?.status, 200);
    assert.match(landing.headers['strict-transport-security'], /max-age=/);
    const question = JSON.stringify({ session_id: '00000000-0000-4000-8000-000000000456', user_message: 'Synthetic packaging question' });
    const gatewayResponse = await request('/api/backend/message', question, {
      Authorization: 'Bearer untrusted-browser-value', 'X-Assurely-Gateway-Key': 'untrusted-browser-value',
    });
    assert.equal(gatewayResponse.status, 200);
    assert.deepEqual(JSON.parse(gatewayResponse.text), { gateway_valid: true, bearer_absent: true });
    assert(!gatewayResponse.text.includes(gateway));
    assert.equal((await request('/api/backend/message', '{}', { Origin: 'https://foreign.example' })).status, 403);
    assert.equal((await request('/api/backend/message', 'x'.repeat(70000))).status, 413);
    const burst = await Promise.all(Array.from({ length: 10 }, () => request('/api/backend/message', question)));
    assert(burst.some(response => response.status === 429));
    assert.equal((await request('/', undefined, { Host: 'foreign.example' })).status, 421);
    assert.equal(docker('port', names[1]), ''); assert.equal(docker('port', names[2]), '');
    await fs.writeFile(path.join(root, 'artifacts', 'production-packaging-results.json'), JSON.stringify({
      synthetic: true, production_next_server: true, tls_and_security_headers: true,
      server_gateway_overrides_browser_headers: true, foreign_origin_rejected: true,
      ingress_body_limit: true, burst_rate_limit_429: true, unexpected_host_rejected: true,
      no_application_ports_published: true, live_hosting_or_insurance_approval: false,
    }, null, 2));
    console.log('PASS: production Next/TLS ingress, gateway isolation, CSRF, size, rate and host controls');
  } finally {
    for (const name of created.reverse()) docker('rm', '-f', name);
    if (networkCreated) docker('network', 'rm', network);
    for (const file of temporary) await fs.rm(path.join(output, file), { force: true });
  }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
