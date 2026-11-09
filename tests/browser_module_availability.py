"""Browser check of module availability on the disposable aetest Nexus (never production).

Stops one aetest module container outside Nexus, then expects the dashboard to report it as
unavailable without a page reload (no green "Running", not counted, no Open link, a friendly
module view), and to recover after the container is started again.
Run: <python with playwright> tests/browser_module_availability.py [module-id]
"""

import json
import re
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs/screenshots/module-availability"
URL = "http://localhost:12334/app/overview"
MODULE = sys.argv[1] if len(sys.argv) > 1 else "zeus"
MODE = sys.argv[2] if len(sys.argv) > 2 else "runtime"
results = []


def check(name, ok=True):
    results.append((name, ok))
    print(("PASS: " if ok else "FAIL: ") + name, flush=True)
    if not ok:
        raise AssertionError(name)


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    owner = json.loads((ROOT / ".data/aetest-owner.json").read_text())
    container = f"aetest-module-{MODULE}"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(URL)
        page.locator("#username").fill(owner["username"])
        page.locator("#password").fill(owner["password"])
        page.get_by_role("button", name="Sign in", exact=True).click()
        hero = page.locator(".hero h1")
        expect(hero).to_have_text("Everything is running normally", timeout=60000)
        total = page.locator(".overview-app").count()
        expect(page.locator(".hero-sub")).to_contain_text(f"{total} of {total} modules running")
        check("All modules verified running before the stop")
        row = page.locator(f'.overview-app[data-module-id="{MODULE}"]')
        name = row.locator("strong").inner_text()
        subprocess.run(["docker", "stop", container], check=True, capture_output=True)
        try:
            # Background monitor (30 s) + quiet page refresh (20 s); no reload.
            expect(row).to_contain_text("Unavailable", timeout=75000)
            check("Stopped module shown as Unavailable without a reload")
            expect(hero).to_have_text(f"{name} is unavailable")
            expect(page.locator(".hero-sub")).to_contain_text(
                f"{total - 1} of {total} modules running · 1 unavailable")
            check("Headline and running count exclude the unavailable module")
            check("No green Running indicator on it",
                  row.locator(".status.tone-good").count() == 0)
            check("No Open action for the unavailable module",
                  row.locator("a", has_text="Open").count() == 0)
            check("Other modules still running", page.locator(
                ".overview-app .status.tone-good").count() == total - 1)
            page.screenshot(path=str(SHOTS / "overview-unavailable-1440.png"), full_page=True)
            page.goto(f"http://localhost:12334/app/modules/{MODULE}")
            expect(page.locator("h1")).to_have_text(re.compile("is not responding"), timeout=15000)
            check("Module view explains instead of showing a raw proxy error",
                  page.locator("#module-application").count() == 0)
            page.screenshot(path=str(SHOTS / "module-unavailable-1440.png"))
            page.goto(URL)
        finally:
            subprocess.run(["docker", "start", container], check=True, capture_output=True)
        expect(page.locator(".hero h1")).to_have_text("Everything is running normally",
                                                     timeout=90000)
        expect(page.locator(f'.overview-app[data-module-id="{MODULE}"] .status.tone-good')
               ).to_be_visible()
        check("Recovery shown without a reload")
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(SHOTS / "overview-390.png"), full_page=True)
        check("No page errors", not errors)
        browser.close()
    print(json.dumps({"passed": sum(ok for _, ok in results), "total": len(results)}))


def startup():
    """The production case: the module was stopped before Nexus restarted."""
    owner = json.loads((ROOT / ".data/aetest-owner.json").read_text())
    subprocess.run(["docker", "stop", f"aetest-module-{MODULE}"], check=True, capture_output=True)
    subprocess.run(["docker", "restart", "aetest-nexus-1"], check=True, capture_output=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        for _ in range(30):
            try:
                page.goto(URL)
                break
            except Exception:  # noqa: BLE001 - Nexus still starting
                page.wait_for_timeout(1000)
        page.locator("#username").fill(owner["username"])
        page.locator("#password").fill(owner["password"])
        page.get_by_role("button", name="Sign in", exact=True).click()
        row = page.locator(f'.overview-app[data-module-id="{MODULE}"]')
        expect(row).to_contain_text("Unavailable", timeout=60000)
        total = page.locator(".overview-app").count()
        name = row.locator("strong").inner_text()
        expect(page.locator(".hero h1")).to_have_text(f"{name} is unavailable", timeout=60000)
        expect(page.locator(".hero-sub")).to_contain_text(
            f"{total - 1} of {total} modules running · 1 unavailable")
        check("Module stopped before a Nexus restart is Unavailable, not running",
              row.locator("a", has_text="Open").count() == 0)
        page.screenshot(path=str(SHOTS / "overview-after-restart-1440.png"), full_page=True)
        browser.close()
    print(json.dumps({"passed": sum(ok for _, ok in results), "total": len(results)}))


if __name__ == "__main__":
    try:
        startup() if MODE == "startup" else main()
    except AssertionError as error:
        print("FAILED:", str(error)[:1500], flush=True)
        sys.exit(1)
