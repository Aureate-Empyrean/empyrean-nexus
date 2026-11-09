"""Legacy modules (no navigation client) keep working with navigation on (aetest only).

Opens each installed application through Nexus, checks its page renders without errors, and
that Back between two of them follows normal browser history.
"""

import json
import re
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://localhost:12334"
MODULES = sys.argv[1:] or ["mnemosyne", "chronos", "lyra", "argus"]


def main():
    owner = json.loads((ROOT / ".data/aetest-owner.json").read_text())
    passed = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE + "/app/overview")
        page.locator("#username").fill(owner["username"])
        page.locator("#password").fill(owner["password"])
        page.get_by_role("button", name="Sign in", exact=True).click()
        expect(page.locator(".hero h1")).to_be_visible(timeout=20000)
        for module in MODULES:
            page.goto(f"{BASE}/app/modules/{module}")
            frame = page.frame_locator("#module-application")
            expect(frame.locator("body")).not_to_be_empty(timeout=20000)
            page.wait_for_timeout(1500)
            text = frame.locator("body").inner_text()
            ok = len(text.strip()) > 20 and "did not respond" not in text
            print(("PASS" if ok else "FAIL") + f": {module} renders inside Nexus", flush=True)
            passed += ok
        page.go_back()
        expect(page).to_have_url(re.compile(rf"/app/modules/{MODULES[-2]}$"))
        print(f"PASS: Back from {MODULES[-1]} returns to {MODULES[-2]}")
        passed += 1
        print(("PASS" if not errors else "FAIL") + ": no page errors", errors[:2])
        passed += not errors
        browser.close()
    total = len(MODULES) + 2
    print(json.dumps({"passed": passed, "total": total}))
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
