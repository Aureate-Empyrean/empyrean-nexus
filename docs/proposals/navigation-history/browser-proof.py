"""Real-browser fixture proof; requires Playwright and locally installed Chrome.

Starts only server.mjs on loopback, runs headless Chrome in a fresh temporary
profile, then closes both processes. No production server or credentials used.
"""
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import urlopen

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("NEXUS_PROOF_PORT", "19439"))
BASE = f"http://127.0.0.1:{PORT}"
results = []


def passed(name):
    results.append(name)
    print("PASS", name, flush=True)


server = subprocess.Popen(
    ["node", str(ROOT / "server.mjs")], cwd=ROOT,
    env={**os.environ, "NEXUS_PROOF_PORT": str(PORT)},
    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
)
try:
    for _ in range(100):
        if server.poll() is not None:
            raise RuntimeError(server.stderr.read().decode())
        try:
            with urlopen(BASE, timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)
    else:
        raise RuntimeError("Fixture failed to start")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def child():
            return page.frame_locator("iframe")

        def frame():
            return page.frames[1]

        def view(route):
            expect(child().locator("#view")).to_have_text(route)

        def length():
            return page.evaluate("history.length")

        page.goto(BASE + "/app/modules/fixture-alpha?path=%2Fexisting&keep=yes&nav=1&route=%2Fitem%2F42%3Ftab%3Dnotes%23recent")
        view("/item/42?tab=notes#recent")
        assert frame().url.endswith("/modules/fixture-alpha/existing")
        assert frame().evaluate("window.origin") == "null"
        assert page.evaluate("""() => {
          try { return !!document.querySelector('iframe').contentWindow.document; }
          catch (e) { return e.name; }
        }""") == "SecurityError"
        passed("deep link restores query/fragment with opaque-origin isolation")

        initial = length()
        child().get_by_role("button", name="List", exact=True).click()
        view("/list")
        assert length() == initial + 1
        assert page.evaluate("new URL(location.href).searchParams.get('path')") == "/existing"
        assert page.evaluate("new URL(location.href).searchParams.get('keep')") == "yes"
        mounts = page.evaluate("proof.mounts")
        child().get_by_role("button", name="Item", exact=True).click()
        view("/item/42?tab=notes#recent")
        assert length() == initial + 2
        assert page.evaluate("proof.mounts") == mounts
        passed("one top-level entry per intent; same frame retained; bootstrap preserved")

        page.go_back()
        view("/list")
        page.go_forward()
        view("/item/42?tab=notes#recent")
        assert length() == initial + 2
        passed("native Back/Forward restores exact internal route without echo entries")

        before = length()
        child().get_by_role("button", name="Item", exact=True).click()
        view("/item/42?tab=notes#recent")
        assert length() == before
        child().get_by_role("button", name="Filter", exact=True).click()
        view("/filter?q=calendar")
        assert length() == before
        page.go_back()
        view("/list")
        page.go_forward()
        view("/filter?q=calendar")
        passed("duplicate intents do not push; replace preserves traversal semantics")

        page.reload()
        view("/filter?q=calendar")
        passed("reload reconstructs view entirely from URL")

        # A module switch must not leave an intermediate iframe history entry.
        page.get_by_role("link", name="Beta", exact=True).click()
        view("/")
        child().get_by_role("button", name="List", exact=True).click()
        view("/list")
        page.go_back()
        view("/")
        expect(page.locator("#status")).to_have_text("fixture-beta")
        page.go_back()
        view("/filter?q=calendar")
        expect(page.locator("#status")).to_have_text("fixture-alpha")
        page.go_forward()
        view("/")
        expect(page.locator("#status")).to_have_text("fixture-beta")
        page.go_forward()
        view("/list")
        passed("cross-module Back/Forward has no extra child history steps")

        frame().evaluate("intent('/slow')")
        page.wait_for_function("new URL(location.href).searchParams.get('route') === '/slow'")
        frame().evaluate("intent('/item/42?tab=notes#recent')")
        view("/item/42?tab=notes#recent")
        page.wait_for_timeout(300)
        view("/item/42?tab=notes#recent")
        page.evaluate("history.go(-2)")
        view("/list")
        page.evaluate("history.go(2)")
        view("/item/42?tab=notes#recent")
        passed("late rendering cannot overwrite a newer route; multi-entry traversal restores")

        url = page.url
        rejects = page.evaluate("proof.rejects")
        frame().evaluate("intent('/obsolete', 'push', 0)")
        page.wait_for_function("proof.rejects > " + str(rejects))
        assert page.url == url
        view("/item/42?tab=notes#recent")
        rejects = page.evaluate("proof.rejects")
        frame().evaluate("intent('//evil.example')")
        page.wait_for_function("proof.rejects > " + str(rejects))
        assert page.url == url
        # Same-shaped message from the top window is not the active child.
        message = frame().evaluate("fixture.last")
        page.evaluate("""m => window.postMessage({channel:m.channel,type:'commit',
          session:m.session,baseRevision:m.revision,route:'/forged',mode:'push'}, '*')""", message)
        page.wait_for_timeout(100)
        assert page.url == url
        passed("stale revisions, invalid routes and foreign message sources cannot navigate")

        page.get_by_role("link", name="Legacy", exact=True).click()
        view("Legacy bootstrap: /existing")
        page.go_back()
        view("/item/42?tab=notes#recent")
        page.go_forward()
        view("Legacy bootstrap: /existing")
        passed("nonparticipating legacy module bootstrap and traversal remain usable")

        # Chrome DevTools mouse back/forward events exercise mouse default traversal.
        cdp = page.context.new_cdp_session(page)
        for button, buttons in [("back", 8), ("forward", 16)]:
            cdp.send("Input.dispatchMouseEvent", {"type":"mousePressed", "x":5, "y":5,
                     "button":button, "buttons":buttons, "clickCount":1})
            cdp.send("Input.dispatchMouseEvent", {"type":"mouseReleased", "x":5, "y":5,
                     "button":button, "buttons":0, "clickCount":1})
            if button == "back":
                view("/item/42?tab=notes#recent")
            else:
                view("Legacy bootstrap: /existing")
        passed("Chrome synthetic mouse Back/Forward buttons use native traversal")

        assert not errors, errors
        print(json.dumps({"browser":browser.version, "passed":len(results), "checks":results}, indent=2))
        browser.close()
finally:
    server.terminate()
    server.communicate(timeout=10)
