/* Requires the dedicated synthetic OIDC/API/Postgres stack, never real accounts. */
if (process.env.ASSURELY_SYNTHETIC_BROWSER_TEST !== '1') throw new Error('Explicit synthetic flag required');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('../.local/browser/node_modules/playwright');
const base = 'http://localhost:3000', output = path.resolve(__dirname, '../artifacts');
async function main() {
  const fixture = JSON.parse(await fs.readFile(path.join(output, 'browser-fixture.json'), 'utf8'));
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const checks = [], errors = [];
  async function account(role) {
    const context = await browser.newContext({ ignoreHTTPSErrors: true, timezoneId: 'UTC', viewport: { width: 1280, height: 900 } });
    await context.addCookies([{ name: 'synthetic_role', value: role, url: 'https://localhost:19443', httpOnly: true, secure: true, sameSite: 'Lax' }]);
    const page = await context.newPage(); page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error' && /hydration|hydrated|uncontrolled|controlled input/i.test(message.text())) errors.push(message.text().slice(0, 500)); });
    await page.goto(base + '/sign-in'); await page.getByRole('button', { name: 'Continue with your account' }).click(); await page.waitForURL('**/workspace');
    return { context, page };
  }
  try {
    const { context, page } = await account('owner');
    await page.getByText('Privacy and consent', { exact: true }).click();
    const consent = page.getByText('Remember your profile for returning visits', { exact: true }).locator('..');
    await consent.getByRole('button', { name: 'Allow', exact: true }).click();
    await page.getByText(/Remember your profile for returning visits: granted/).waitFor();
    await consent.getByRole('button', { name: 'Withdraw', exact: true }).click();
    await page.getByText(/Remember your profile for returning visits: revoked/).waitFor();
    await page.getByRole('button', { name: 'Delete saved profile', exact: true }).click();
    await page.getByRole('button', { name: 'Confirm profile deletion', exact: true }).click();
    await page.getByText('No saved profile was present.', { exact: true }).waitFor();
    checks.push('Actual consent grant/revoke and confirmed owner profile deletion through UI/BFF/JWT/Postgres');
    assert.equal((await page.request.delete(base + '/api/backend/profile-memory', { headers: { Origin: 'https://foreign.invalid', 'Content-Type': 'application/json' }, data: {} })).status(), 403);
    assert.equal((await page.request.post(base + '/api/backend/consent', { headers: { Origin: base }, data: { scope: 'save_profile', action: 'grant', user_id: '00000000-0000-4000-8000-000000000123' } })).status(), 422);
    assert.equal((await page.request.delete(base + '/api/backend/profile-memory/00000000-0000-4000-8000-000000000123', { headers: { Origin: base }, data: {} })).status(), 404);
    checks.push('DELETE CSRF, caller-selected privacy subject and arbitrary backend paths rejected');

    await page.goto(base + '/workspace');
    await page.getByRole('button', { name: 'New case', exact: true }).click();
    const session = await page.getByLabel('Case identifier', { exact: true }).inputValue();
    await page.getByText('Review a specific policy', { exact: true }).click();
    await page.getByLabel('Advisor-supplied policy references').fill(fixture.publication);
    await page.getByLabel('Entry age in completed years').fill('35');
    await page.getByLabel('Applicable issue or renewal date').fill(new Date().toISOString().slice(0, 10));
    await page.getByLabel('Your question', { exact: true }).fill('Explain this selected policy coverage.');
    await page.getByRole('button', { name: 'Send question', exact: true }).click();
    await page.getByText('Your case is held for review. No report has been released.', { exact: true }).waitFor({ timeout: 90000 });
    await page.getByRole('button', { name: 'Check case activity', exact: true }).click();
    await page.getByText('Case activity: active. Report access is checked separately.', { exact: true }).waitFor();
    checks.push('Authenticated session-detail API connected without exposing held audit content');
    const advisor = await account('advisor');
    const snap = await advisor.page.request.post(`${base}/api/backend/advisor-reviews/sessions/${session}/snapshot`, { headers: { Origin: base }, data: {} });
    assert.equal(snap.status(), 200); const digest = (await snap.json()).report_digest;
    const decision = action => advisor.page.request.post(`${base}/api/backend/advisor-reviews/${digest}/decisions`, {
      headers: { Origin: base }, data: { request_key: crypto.randomUUID(), expected_revision: action === 'approve' ? 0 : 1,
        action, reason: 'Synthetic integration decision', expires_at: action === 'approve' ? new Date(Date.now() + 600000).toISOString() : null },
    });
    assert.equal((await decision('approve')).status(), 200);
    await page.goto(`${base}/comparison#${session}`); await page.getByRole('button', { name: 'Check current status', exact: true }).click();
    await page.getByRole('button', { name: 'Check and open reviewed report', exact: true }).click();
    await page.getByRole('article', { name: 'Released report' }).waitFor();
    assert((await page.getByRole('article').innerText()).includes('Last verified:'));
    await page.screenshot({ path: path.join(output, 'integration-comparison-connected.png'), fullPage: true });
    checks.push('Comparison page displays actual freshly released sourced report after independent approval');
    assert.equal((await decision('revoke')).status(), 200);
    await page.getByRole('button', { name: 'Check and open reviewed report', exact: true }).click(); await page.locator('[data-slot="inline-alert"][role="alert"]').waitFor();
    assert.equal(await page.getByRole('article', { name: 'Released report' }).count(), 0);
    await page.goto(`${base}/handoff#${session}`); await page.getByRole('button', { name: 'Check current status', exact: true }).click();
    await page.getByText('Turn: complete', { exact: true }).waitFor();
    assert(!(await page.locator('body').innerText()).includes('A licensed advisor will'));
    await page.screenshot({ path: path.join(output, 'integration-handoff-connected.png'), fullPage: true });
    checks.push('Revocation removes displayed comparison; handoff reports real metadata without invented notification');

    const oldCase = crypto.randomUUID(), newCase = crypto.randomUUID(), turn = crypto.randomUUID();
    await page.goto(`${base}/workspace#${oldCase}`);
    await page.route(`**/api/backend/sessions/${oldCase}/report-status`, async route => {
      await new Promise(resolve => setTimeout(resolve, 1200));
      await route.fulfill({ json: { turn_id: turn, report_digest: 'a'.repeat(64), status: 'complete', delivery_hold: true } }).catch(() => {});
    });
    await page.getByRole('button', { name: 'Refresh case status', exact: true }).click();
    await page.evaluate(id => { window.location.hash = id; }, newCase);
    await page.waitForTimeout(1600);
    assert.equal(await page.getByLabel('Case identifier', { exact: true }).inputValue(), newCase);
    assert.equal(await page.getByText('Report prepared. Independent review is required before release.', { exact: true }).count(), 0);
    checks.push('Delayed old-case response cannot populate a different case after hash navigation');
    await page.unrouteAll({ behavior: 'wait' });
    let submissions = 0;
    await page.route('**/api/backend/message', async route => { submissions++; await new Promise(resolve => setTimeout(resolve, 500));
      await route.fulfill({ json: { session_id: newCase, reply: 'Synthetic held response.', delivery_hold: true, missing_fields: [], escalation: true, notification_status: 'not_configured', output: {} } }); });
    await page.getByLabel('Your question', { exact: true }).fill('Synthetic duplicate-click probe');
    await page.getByRole('button', { name: 'Send question', exact: true }).evaluate(button => { button.click(); button.click(); });
    await page.getByText('Synthetic held response.', { exact: true }).waitFor(); assert.equal(submissions, 1);
    checks.push('Immediate duplicate clicks issue one message request');
    await page.unrouteAll({ behavior: 'wait' });
    await page.route('**/api/backend/sessions/*/report-status', route => route.fulfill({ json: { status: 'complete' } }));
    await page.getByRole('button', { name: 'Refresh case status', exact: true }).click(); await page.locator('[data-slot="inline-alert"][role="alert"]').waitFor();
    assert.equal(await page.getByRole('button', { name: 'Check and open reviewed report', exact: true }).count(), 0);
    checks.push('Malformed HTTP-200 status cannot enable report release');
    await page.unrouteAll({ behavior: 'wait' });

    await page.goto(base + '/intake'); await page.locator('#adults').selectOption('2');
    await page.locator('#children').selectOption('1'); await page.getByLabel('Age of the eldest member', { exact: true }).fill('35');
    await page.locator('#city-tier').selectOption('tier_1');
    await page.getByRole('button', { name: 'Continue →', exact: true }).click();
    await page.getByLabel('Room choices without a room-rent limit', { exact: true }).check();
    await page.getByRole('button', { name: '← Back', exact: true }).click();
    assert.equal(await page.getByLabel('Age of the eldest member', { exact: true }).inputValue(), '35');
    await page.getByRole('button', { name: 'Continue →', exact: true }).click();
    assert(await page.getByLabel('Room choices without a room-rent limit', { exact: true }).isChecked());
    await page.getByRole('button', { name: 'Continue →', exact: true }).click(); await page.getByLabel('Under ₹15,000 a year', { exact: true }).check();
    await page.getByRole('button', { name: 'Continue →', exact: true }).click(); await page.getByLabel('Active retail health policy', { exact: true }).check();
    await page.getByLabel('I allow these details to be processed', { exact: false }).check();
    const submitted = page.waitForResponse(response => response.url().endsWith('/api/backend/message'));
    await page.getByRole('button', { name: 'Submit my case', exact: true }).click(); const sent = await submitted;
    assert.equal(sent.status(), 200); assert.match(sent.request().postDataJSON().user_message, /Adults to cover: 2/);
    await page.getByRole('heading', { name: 'Case submitted.', exact: true }).waitFor();
    await page.screenshot({ path: path.join(output, 'integration-intake-submitted.png'), fullPage: true });
    checks.push('Guided intake retains previous-step answers and submits real consent/message requests');
    await page.goto(base + '/');
    await page.getByLabel('The statement', { exact: true }).fill('Synthetic question about room-category wording.');
    await page.getByRole('button', { name: 'Start a statement case', exact: true }).click();
    await page.getByText('Case opened', { exact: true }).waitFor({ timeout: 90000 });
    assert.match(await page.getByRole('link', { name: 'Continue or check this case', exact: false }).getAttribute('href'), /^\/workspace#[a-f0-9-]{36}$/);
    checks.push('Landing statement form opens a real case without claiming verification');
    await page.setViewportSize({ width: 390, height: 844 }); await page.goto(`${base}/comparison#${session}`);
    await page.getByRole('button', { name: 'Check current status', exact: true }).click({ trial: true });
    await page.evaluate(() => document.documentElement.dataset.theme = 'dark');
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    await page.screenshot({ path: path.join(output, 'integration-mobile-dark.png'), fullPage: true });
    checks.push('Connected comparison layout fits dark mobile viewport');
    assert.deepEqual(errors, []);
    await fs.writeFile(path.join(output, 'frontend-integration-results.json'), JSON.stringify({ synthetic: true, actual_backend_positive_paths: true, model_intake_and_retrieval_synthetic: true,
      mocked_negative_cases: ['delayed old-case response', 'duplicate-click held response', 'malformed successful status'], checks, page_errors: errors, genuine_identity_or_source_approval: false }, null, 2));
    console.log(`PASS: ${checks.length} frontend integration checks; zero page errors`);
    await context.close();
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
