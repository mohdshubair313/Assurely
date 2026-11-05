/* Synthetic fixture only. Uses the isolated tests.browser_server; never a live user token. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('../.local/browser/node_modules/playwright');

const base = 'http://localhost:3000';
const output = path.resolve(__dirname, '../artifacts');

async function main() {
  const fixture = JSON.parse(await fs.readFile(path.join(output, 'browser-fixture.json'), 'utf8'));
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const owner = await browser.newContext({ viewport: { width: 1280, height: 900 }, ignoreHTTPSErrors: true, timezoneId: 'UTC' });
  const advisor = await browser.newContext({ viewport: { width: 1280, height: 900 }, ignoreHTTPSErrors: true, timezoneId: 'UTC' });
  const checks = [];
  const errors = [];
  try {
    for (const [context, role] of [[owner, 'owner'], [advisor, 'advisor']]) {
      await context.addCookies([{ name: 'synthetic_role', value: role,
        url: 'https://localhost:19443', httpOnly: true, secure: true, sameSite: 'Lax' }]);
    }
    const page = await owner.newPage();
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(base + '/sign-in');
    await page.getByRole('button', { name: 'Continue with your account' }).click();
    await page.waitForURL('**/workspace', { timeout: 45000 });
    checks.push('OIDC discovery, PKCE, state, nonce and signed ID token complete via server callback');
    assert(!(await page.evaluate(() => document.cookie)).includes('assurely_session'));
    const sessionState = await (await page.request.get(base + '/api/auth/session')).json();
    assert.deepEqual(sessionState, { authenticated: true });
    checks.push('Session cookie is HttpOnly and account status never returns access tokens');
    await page.getByRole('button', { name: 'New case', exact: true }).click();
    const session = await page.getByLabel('Case identifier').inputValue();
    assert.match(session, /^[a-f0-9-]{36}$/);
    await page.getByText('Review a specific policy', { exact: true }).click();
    await page.getByLabel('Advisor-supplied policy reference').fill(fixture.publication);
    await page.getByLabel('Entry age in completed years').fill('35');
    await page.getByLabel('Applicable issue or renewal date').fill(new Date().toISOString().slice(0,10));
    await page.getByLabel('Your question', { exact: true }).fill('Explain the discrete cover amount options for this selected policy.');
    await page.getByRole('button', { name: 'Send question', exact: true }).click();
    await page.getByText('Your case is held for review. No report has been released.').waitFor({ timeout: 90000 });
    assert(!(await page.locator('body').innerText()).includes('500000'));
    await page.getByRole('button', { name: 'Refresh case status' }).click();
    await page.getByText('Report prepared. Independent review is required before release.').waitFor();
    await page.getByRole('button', { name: 'Check and open reviewed report' }).click();
    await page.getByRole('alert').waitFor();
    assert.equal(await page.getByRole('article', { name: 'Released report' }).count(), 0);
    checks.push('Actual graph/BFF holds sourced report before advisor approval');
    await page.screenshot({ path: path.join(output, 'journey-owner-held.png'), fullPage: true });
    const current = await page.request.get(`${base}/api/backend/sessions/${session}/report-status`);
    assert.equal(current.status(), 200);
    const metadata = await current.json();
    assert(metadata.report_digest);

    const review = await advisor.newPage();
    review.on('pageerror', e => errors.push(e.message));
    await review.goto(base + '/sign-in');
    await review.getByRole('button', { name: 'Continue with your account' }).click();
    await review.waitForURL('**/workspace', { timeout: 45000 });
    await review.goto(base + '/advisor');
    await review.getByLabel('Case identifier', { exact: true }).fill(session);
    await review.getByRole('button', { name: 'Load current case report' }).click();
    await review.getByRole('heading', { name: 'Exact report under review' }).waitFor();
    await review.getByLabel('Review reason', { exact: true }).fill('Synthetic browser review of the exact sourced report');
    await review.getByLabel('Approval expires at').fill(new Date(Date.now()+15*60000).toISOString().slice(0,16));
    const approvalResponse = review.waitForResponse(r => r.url().endsWith('/decisions'));
    await review.getByRole('button', { name: 'Approve reviewed report', exact: true }).click();
    const decision = await approvalResponse;
    assert.equal(decision.status(), 200, JSON.stringify(await decision.json()));
    await review.getByText('Review status: approved · Revision 1').waitFor();
    checks.push('Independent authorized advisor reads exact report and records approval');
    await review.screenshot({ path: path.join(output, 'journey-advisor-review.png'), fullPage: true });

    await page.getByRole('button', { name: 'Check and open reviewed report' }).click();
    await page.getByRole('article', { name: 'Released report' }).waitFor();
    assert((await page.getByRole('article').innerText()).includes('Last verified:'));
    checks.push('Owner release returns sourced/date-bearing report through committed transaction');
    await page.getByText('Source documents and conditions', { exact: true }).click();
    const source = page.getByRole('link', { name: /Policy fact · PDF page/ }).first();
    assert.match(await source.getAttribute('href'), /^https:\/\/.*#page=\d+$/);
    assert.equal(await source.getAttribute('rel'), 'noopener noreferrer');
    checks.push('Released citations expose HTTPS PDF pages and separate applicability/condition evidence');
    await page.screenshot({ path: path.join(output, 'journey-owner-released.png'), fullPage: true });
    await page.evaluate(() => { document.documentElement.dataset.theme = 'dark'; });
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: path.join(output, 'journey-mobile-dark.png'), fullPage: true });
    checks.push('Dark mobile view has no horizontal overflow');

    const foreign = await review.request.get(`${base}/api/backend/sessions/${session}/report-status`);
    assert.equal(foreign.status(), 403);
    const csrf = await page.request.post(base + '/api/backend/message', {
      headers: { Origin: 'https://foreign.example', 'Content-Type': 'application/json' }, data: {},
    });
    assert.equal(csrf.status(), 403);
    const oversize = await page.request.post(base + '/api/backend/message', {
      headers: { Origin: base, 'Content-Type': 'application/json' }, data: 'x'.repeat(70000),
    });
    assert.equal(oversize.status(), 413);
    checks.push('Foreign owner, cross-origin writes and oversized body rejected');
    await review.getByRole('button', { name: 'Revoke approval', exact: true }).click();
    await review.getByText('Review status: revoked · Revision 2').waitFor();
    await page.getByRole('button', { name: 'Check and open reviewed report' }).click();
    await page.getByRole('alert').waitFor();
    assert.equal(await page.getByRole('article', { name: 'Released report' }).count(), 0);
    checks.push('Revocation blocks idempotent release retry and clears displayed report');

    const anonymous = await browser.newContext();
    const denied = await anonymous.request.get(`${base}/api/backend/sessions/${session}/report-status`);
    assert.equal(denied.status(), 401);
    await anonymous.addCookies([{ name: 'assurely_session', value: 'tampered', url: base }]);
    assert.equal((await anonymous.request.get(`${base}/api/backend/sessions/${session}/report-status`)).status(), 401);
    const callback = await anonymous.newPage();
    await callback.goto(base + '/api/auth/callback?code=invalid&state=invalid');
    await callback.getByText('Sign-in could not be completed. Please try again or contact your administrator.').waitFor();
    checks.push('Missing session and invalid OIDC transaction fail closed');
    await page.getByRole('button', { name: 'New case', exact: true }).click();
    await page.route('**/api/backend/message', route => route.fulfill({
      status: 200, contentType: 'application/json', body: '{}',
    }));
    await page.getByLabel('Your question', { exact: true }).fill('Synthetic malformed response check');
    await page.getByRole('button', { name: 'Send question', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'The service returned an invalid response.' }).waitFor();
    await page.unroute('**/api/backend/message');
    checks.push('Malformed successful message response cannot claim a report is available');
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(base + '/', { waitUntil: 'networkidle' });
    await page.screenshot({ path: path.join(output, 'journey-landing.png'), fullPage: true, animations: 'disabled' });
    await page.goto(base + '/comparison', { waitUntil: 'networkidle' });
    await page.screenshot({ path: path.join(output, 'journey-comparison-preview.png'), fullPage: true, animations: 'disabled' });
    assert.deepEqual(errors, []);
    await fs.writeFile(path.join(output, 'advisory-browser-results.json'), JSON.stringify({
      synthetic: true, session_id: session, passed: checks, page_errors: errors,
      synthetic_oidc_protocol_tested: true, live_oidc_provider_tested: false, real_policy_approval: false,
    }, null, 2));
    console.log(`PASS: ${checks.length} browser journey checks; no page errors`);
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
