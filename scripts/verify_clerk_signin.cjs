/* Live configured provider UI checks; never creates accounts or supplies user credentials. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('../.local/browser/node_modules/playwright');
async function main() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  const base = 'http://localhost:3000';
  const checks = [], errors = [];
  page.on('pageerror', error => errors.push(error.name));
  try {
    assert.equal((await page.goto(base + '/sign-in')).status(), 200);
    await page.locator('.cl-signIn-root').waitFor({ timeout: 60_000 });
    assert.ok(await page.locator('.cl-signIn-root input').count());
    checks.push('Genuine Clerk sign-in widget renders with configured instance');
    await page.screenshot({ path: path.resolve(__dirname, '../artifacts/clerk-live-signin-20261104.png'), fullPage: true });
    await page.goto(base + '/sign-up');
    await page.locator('.cl-signUp-root').waitFor({ timeout: 30_000 });
    checks.push('Genuine Clerk sign-up widget renders without creating an account');
    await page.goto(base + '/workspace');
    await page.waitForURL('**/sign-in*');
    checks.push('Anonymous private workspace redirects to sign-in');
    assert.equal((await page.request.get(base + '/api/backend/me')).status(), 401);
    checks.push('Unauthenticated configured BFF returns 401');
    await page.goto(base + '/');
    await page.getByRole('heading', { level: 1 }).waitFor();
    checks.push('Public landing remains accessible with Clerk configured');
    assert.deepEqual(errors, []);
    const result = { passed: true, checks, browser_errors: errors,
      user_account_created: false, authenticated_session_e2e_verified: false };
    await fs.writeFile(path.resolve(__dirname, '../artifacts/clerk-live-ui-20261104.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result, null, 2));
  } finally { await context.close(); await browser.close(); }
}
main().catch(error => { console.error(error.name + ': live Clerk UI check failed'); process.exitCode = 1; });
