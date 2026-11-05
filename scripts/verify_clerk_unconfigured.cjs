/* Actual browser negative checks. This deliberately does not fake Clerk login. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('../.local/browser/node_modules/playwright');
async function main() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const base = process.env.AUTH_BROWSER_BASE ?? 'http://127.0.0.1:3000';
  const expectedOrigin = process.env.AUTH_BROWSER_ORIGIN ?? 'http://localhost:3000';
  const checks = [], errors = [], providerCalls = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (/clerk\.accounts|clerk\.com/.test(request.url())) providerCalls.push(request.url()); });
  const output = path.resolve(__dirname, '../artifacts');
  try {
    assert.equal((await page.goto(base)).status(), 200);
    await page.getByRole('heading', { level: 1 }).waitFor();
    checks.push('Public landing renders without Clerk keys');
    assert.equal((await page.goto(base + '/how-it-works')).status(), 200);
    checks.push('Public educational page remains available');
    for (const route of ['/sign-in', '/sign-up', '/sign-in/verify']) {
      assert.equal((await page.goto(base + route)).status(), 200);
      await page.getByRole('status').filter({ hasText: 'awaiting secure provider configuration' }).waitFor();
    }
    await page.screenshot({ path: path.join(output, 'clerk-setup-required-20261104.png'), fullPage: true });
    checks.push('Sign-in/up and catch-all verification routes show honest setup-required state');
    for (const route of ['/workspace', '/intake', '/comparison', '/handoff', '/advisor']) {
      await page.goto(base + route);
      await page.getByRole('heading', { name: 'Account access is unavailable', exact: true }).waitFor();
      assert.equal(await page.getByRole('textbox').count(), 0);
    }
    checks.push('All private views withhold case and advisor UI when auth is unconfigured');
    assert.equal((await page.request.get(base + '/api/backend/me')).status(), 503);
    checks.push('Private BFF fails closed with 503 while provider config is missing');
    assert.equal((await page.request.post(base + '/api/backend/consent', {
      headers: { Origin: 'https://foreign.invalid' }, data: {},
    })).status(), 403);
    checks.push('Cross-origin privacy mutation is forbidden');
    assert.equal((await page.request.post(base + '/api/backend/consent', {
      headers: { Origin: expectedOrigin },
      data: { scope: 'save_profile', action: 'grant', user_id: '00000000-0000-4000-8000-000000000123' },
    })).status(), 422);
    checks.push('Caller-supplied identity is rejected before upstream access');
    for (const route of ['/api/auth/callback', '/api/auth/session']) {
      assert.equal((await page.request.get(base + route)).status(), 404);
    }
    checks.push('Legacy OIDC entry points are disabled in Clerk mode');
    assert.deepEqual(providerCalls, []);
    assert.deepEqual(errors, []);
    checks.push('No keyless Clerk provisioning/network call or browser runtime exception');
    const result = { scope: 'actual_browser_unconfigured_negative_only', checks,
      live_clerk_login_verified: false, browser_errors: errors, passed: true };
    await fs.writeFile(path.join(output, 'clerk-browser-negative-20261104.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result, null, 2));
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
