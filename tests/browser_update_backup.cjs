// Review-only browser check of the 0.1.13 update dialog on aetest (never production): the
// dialog says a verified backup is required, keeps "Back up before updating" checked, and asks
// for a reason when it is unchecked. Nothing is applied: the dialog is closed after the review.
//
//   PLAYWRIGHT_PATH=G:/AureateEmpyrean/mnemosyne/node_modules/playwright node tests/browser_update_backup.cjs
const fs = require("fs");
const path = require("path");
const { chromium } = require(process.env.PLAYWRIGHT_PATH || "playwright");

const NEXUS = "http://localhost:12334";
let passed = 0;
const check = (ok, what) => {
  if (!ok) {
    console.error(`FAIL ${what}`);
    process.exit(1);
  }
  passed++;
  console.log(`ok   ${what}`);
};

(async () => {
  // Lyra's installed manifest with a higher version: a reviewable update that is never applied.
  const browser = await chromium.launch();
  for (const [label, viewport] of [["desktop", { width: 1440, height: 900 }], ["phone", { width: 390, height: 844 }]]) {
    const page = await browser.newPage({ viewport });
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    await page.goto(NEXUS + "/app/modules");
    if (await page.locator("#username").isVisible({ timeout: 5000 }).catch(() => false)) {
      const owner = JSON.parse(fs.readFileSync(path.join(__dirname, "../.data/aetest-owner.json"), "utf8"));
      await page.locator("#username").fill(owner.username);
      await page.locator("#password").fill(owner.password);
      await page.getByRole("button", { name: "Sign in", exact: true }).click();
    }
    await page.locator('.module-row[data-module-id="lyra"]').first().waitFor({ timeout: 30000 });
    const installed = await page.evaluate(async () => {
      const r = await fetch("/api/v1/modules/lyra", { credentials: "same-origin" });
      return r.ok ? (await r.json()).manifest : null;
    });
    check(installed && installed.version, `${label}: Lyra ${installed?.version} is installed`);
    const next = { ...installed, version: installed.version.replace(/\d+$/, (n) => String(+n + 1)) };
    await page.locator(`.module-row[data-module-id="lyra"] .row-more`).first().click();
    await page.getByRole("menuitem", { name: /Review an update/ }).click();
    await page.locator("#update-manifest").fill(JSON.stringify(next));
    await page.getByRole("button", { name: "Review changes" }).click();
    await page.locator("#apply-update").waitFor();
    const text = await page.locator("#update-review").innerText();
    check(/A verified backup is required before this update/.test(text), `${label}: the review says a verified backup is required`);
    const box = page.locator("#backup-before");
    check(await box.isChecked(), `${label}: "Back up before updating" starts checked`);
    check(await page.locator("#backup-override-box").isHidden(), `${label}: no override field while the backup is kept`);
    await box.uncheck();
    check(await page.locator("#backup-override-box").isVisible(), `${label}: unchecking asks for a reason`);
    await page.getByRole("button", { name: new RegExp(`Update to v${next.version.replace(/\./g, "\\.")}`) }).click();
    await page.waitForTimeout(300);
    check(/give a reason/.test(await page.locator("#update-review, .dialog").first().innerText()) || /give a reason/.test(await page.content()), `${label}: updating without backup or reason is refused in the dialog`);
    await page.screenshot({ path: path.join(__dirname, `../docs/screenshots/update-backup-${label}.png`) });
    await page.keyboard.press("Escape");
    const still = await page.evaluate(async () => (await (await fetch("/api/v1/modules/lyra")).json()).manifest.version);
    check(still === installed.version, `${label}: nothing was applied (Lyra still ${still})`);
    check(errors.length === 0, `${label}: no page errors (${errors.join(" / ")})`);
    await page.close();
  }
  await browser.close();
  console.log(`${passed} checks passed`);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
