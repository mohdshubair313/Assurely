/* Capture actual localhost pages and record browser checks; no generated images. */
const fs = require("node:fs/promises");
const path = require("node:path");
const assert = require("node:assert/strict");
const { chromium } = require("../.local/browser/node_modules/playwright");

async function main() {
  const output = path.resolve(__dirname, "../artifacts");
  const captureDate = new Date().toISOString().slice(0, 10);
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: "light" });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  const shots = [];
  async function capture(name, fullPage = true) {
    await page.evaluate(() => document.fonts.ready);
    await page.evaluate(() => Promise.all(Array.from(document.images, image => image.decode())));
    const metrics = await page.evaluate(() => ({
      viewport: { width: innerWidth, height: innerHeight },
      documentWidth: document.documentElement.scrollWidth,
      theme: document.documentElement.dataset.theme,
      images: Array.from(document.images, image => ({
        src: image.currentSrc, width: image.naturalWidth, height: image.naturalHeight,
      })),
    }));
    assert(metrics.documentWidth <= metrics.viewport.width, "Document overflows horizontally");
    await page.screenshot({ path: path.join(output, name), fullPage, animations: "disabled" });
    shots.push({ file: name, url: page.url(), captured_at: new Date().toISOString(), ...metrics });
  }
  try {
    assert((await page.goto("http://localhost:3000", { waitUntil: "networkidle" })).ok());
    assert.equal(await page.locator("html").getAttribute("data-theme"), "light");
    const house = page.getByAltText("A warmly lit stone cottage with blue slate roofs, nestled among soft three-dimensional clouds.");
    await house.waitFor({ state: "visible" });
    const houseBox = await house.boundingBox();
    assert(houseBox, "House artwork must be visible");
    await page.mouse.move(houseBox.x + houseBox.width * 0.7, houseBox.y + houseBox.height * 0.4);
    assert.notEqual(await page.locator(".house-scene").evaluate(el => el.style.getPropertyValue("--scene-x")), "", "House must respond to pointer movement");
    await page.getByRole("button", { name: "Pause house animation", exact: true }).click();
    assert.equal(await page.locator(".house-float").evaluate(el => getComputedStyle(el).animationPlayState), "paused");
    await page.getByRole("button", { name: "Resume house animation", exact: true }).press("Enter");
    assert.equal(await page.locator(".house-float").evaluate(el => getComputedStyle(el).animationPlayState), "running");
    await page.emulateMedia({ reducedMotion: "reduce" });
    assert.equal(await page.locator(".house-float").evaluate(el => getComputedStyle(el).animationName), "none");
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.mouse.move(5, 5);
    await page.evaluate(() => window.scrollTo(0, 0));
    await capture(`${captureDate}-01-landing-light.png`);
    assert((await page.goto("http://localhost:3000/comparison", { waitUntil: "networkidle" })).ok());
    await capture(`${captureDate}-02-comparison-light.png`);
    await page.getByRole("button", { name: "Toggle color theme" }).click();
    await page.waitForFunction(() => document.documentElement.dataset.theme === "dark");
    await capture(`${captureDate}-03-comparison-dark.png`);
    await page.reload({ waitUntil: "networkidle" });
    assert.equal(await page.locator("html").getAttribute("data-theme"), "dark");
    await page.getByRole("button", { name: "Explore Waiting period", exact: true }).click();
    assert.equal(await page.getByRole("button", { name: "Explore Waiting period", exact: true }).getAttribute("aria-pressed"), "true");
    assert.equal(await page.locator(".clause-paper h3").textContent(), "Waiting period");
    await page.getByLabel("What did the agent tell you?").fill("All hospital rooms are covered");
    await page.getByRole("button", { name: "Check against policy" }).click();
    await page.getByText("Your statement has not been verified.", { exact: true }).waitFor();
    await page.getByRole("button", { name: "Toggle color theme" }).click();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("http://localhost:3000", { waitUntil: "networkidle" });
    await capture(`${captureDate}-04-landing-mobile.png`, false);
    assert.deepEqual(errors, [], "Browser runtime errors");
    const report = { screenshots: shots, runtime_errors: errors,
      checks: ["No document-level horizontal overflow", "House responds to pointer movement", "House pause and keyboard resume work", "Reduced motion disables house animation", "Theme toggles and survives reload",
        "Policy detail selection updates clause card", "Claim checker explicitly reports unverified preview"] };
    await fs.writeFile(path.join(output, `${captureDate}-frontend-review.json`), JSON.stringify(report, null, 2) + "\n");
    console.log(JSON.stringify(report, null, 2));
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
