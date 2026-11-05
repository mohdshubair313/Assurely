/* Destructive operations are limited to this script's disposable, named test DBs. */
if (process.env.ASSURELY_SYNTHETIC_BROWSER_TEST !== '1') throw new Error('Explicit synthetic fixture flag required');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { chromium } = require('../.local/browser/node_modules/playwright');
const output = path.resolve(__dirname, '../artifacts');
function docker(...args) { return execFileSync('docker', args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim(); }
const query = "SELECT json_build_object('sessions',(SELECT count(*) FROM sessions),'checkpoints',(SELECT count(*) FROM checkpoints),'release_receipts',(SELECT count(*) FROM report_release_receipts),'decisions',(SELECT count(*) FROM advisor_decisions))";
function counts(database) { return JSON.parse(docker('exec', 'insurance-gates-db', 'psql', '-U', 'postgres', '-d', database, '-Atc', query)); }
async function main() {
  const before = counts('policy_review_test_terms');
  docker('exec', 'insurance-gates-db', 'pg_dump', '-U', 'postgres', '-d', 'policy_review_test_terms', '-Fc', '-f', '/tmp/assurely-synthetic.dump');
  docker('exec', 'insurance-gates-db', 'createdb', '-U', 'postgres', 'policy_review_restore_test');
  docker('exec', 'insurance-gates-db', 'pg_restore', '-U', 'postgres', '-d', 'policy_review_restore_test', '/tmp/assurely-synthetic.dump');
  assert.deepEqual(counts('policy_review_restore_test'), before);
  docker('cp', 'insurance-gates-db:/tmp/assurely-synthetic.dump', path.join(output, 'synthetic-backup.dump'));
  docker('restart', 'insurance-gates-db');
  let ready = false;
  for (let attempt = 0; attempt < 40; attempt++) {
    try { docker('exec', 'insurance-gates-db', 'pg_isready', '-U', 'postgres'); ready = true; break; }
    catch { await new Promise(resolve => setTimeout(resolve, 500)); }
  }
  assert(ready, 'Disposable database did not restart');
  assert.deepEqual(counts('policy_review_test_terms'), before);
  const result = JSON.parse(await fs.readFile(path.join(output, 'advisory-browser-results.json'), 'utf8'));
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    const page = await context.newPage();
    await page.goto('http://localhost:3000/sign-in');
    await page.getByRole('button', { name: 'Continue with your account' }).click();
    await page.waitForURL('**/workspace');
    const response = await page.request.get(`http://localhost:3000/api/backend/session/${result.session_id}`);
    assert.equal(response.status(), 200);
    assert.deepEqual((await response.json()).messages, []);
  } finally { await browser.close(); }
  await fs.writeFile(path.join(output, 'database-recovery-results.json'), JSON.stringify({
    synthetic: true, dump_restore_counts_match: true, physical_postgres_restart: true,
    application_read_after_restart: true, held_data_redacted: true, table_counts: before,
    production_infrastructure_verified: false,
  }, null, 2));
  console.log('PASS: synthetic dump/restore, physical Postgres restart and protected checkpoint read');
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
