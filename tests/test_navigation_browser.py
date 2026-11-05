"""Opt-in real local runtime regression: NEXUS_BROWSER_TESTS=1 pytest -s ...

Requires installed Chrome, Playwright and each repository's .venv dependencies.
Only the container lifecycle is substituted with disposable loopback processes.
"""

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    os.getenv("NEXUS_BROWSER_TESTS") != "1", reason="Opt-in local browser integration"
)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_real_nexus_mnemosyne_navigation(tmp_path):
    from playwright.sync_api import expect, sync_playwright

    port = free_port()
    origin = f"http://127.0.0.1:{port}"
    module_ports = {name: free_port() for name in ("mnemosyne", "chronos")}
    env = {
        **os.environ,
        "PILOT_DATA": str(tmp_path),
        "PILOT_NEXUS_PORT": str(port),
        "PILOT_MODULE_PORTS": json.dumps(module_ports),
        "NEXUS_PUBLIC_ORIGIN": origin,
        "NEXUS_URL": origin,
        "NEXUS_NAVIGATION_HISTORY": "1",
        "NEXUS_ALLOW_EXAMPLE": "0",
    }
    log = open(tmp_path / "nexus.log", "w", encoding="utf-8")
    server = subprocess.Popen(
        [sys.executable, "-X", "utf8", str(ROOT / "tests/navigation_pilot_runtime.py")],
        env=env,
        stdout=log,
        stderr=log,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    client = httpx.Client(base_url=origin, trust_env=False, timeout=30)
    checks = []

    def checked(response, status=200):
        assert response.status_code == status, response.text[:1000]
        return response.json()

    def passed(name):
        checks.append(name)
        print("PASS:", name, flush=True)

    try:
        for _ in range(200):
            if server.poll() is not None:
                pytest.fail((tmp_path / "nexus.log").read_text())
            try:
                if client.get("/healthz").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.05)
        else:
            pytest.fail("Disposable Nexus did not start")
        password = secrets.token_urlsafe(24)
        setup = checked(
            client.post(
                "/api/v1/setup",
                json={
                    "username": "pilot-owner",
                    "password": password,
                    "installation_name": "Disposable navigation pilot",
                    "claim_token": (tmp_path / "nexus/setup-token").read_text(),
                },
            ),
            201,
        )
        client.headers["X-Nexus-CSRF"] = setup["csrf"]
        for name in module_ports:
            manifest = json.loads((ROOT.parent / name / "manifest.json").read_text())
            checked(
                client.post(
                    "/api/v1/modules",
                    json={"manifest": manifest, "grants": manifest["capabilities"]},
                ),
                201,
            )
            response = client.post(f"/api/v1/modules/{name}/enable")
            if response.status_code != 200:
                logs = (
                    (tmp_path / (name + ".log")).read_text()
                    if (tmp_path / (name + ".log")).exists()
                    else ""
                )
                pytest.fail(response.text + "\n" + logs)
        wid = checked(
            client.post(
                "/modules/mnemosyne/api/workspaces",
                json={"title": "Pilot Workspace", "timezone": "Europe/Bratislava"},
            ),
            201,
        )["id"]
        other_wid = checked(
            client.post("/modules/mnemosyne/api/workspaces", json={"title": "Other Workspace"}), 201
        )["id"]

        def create(kind, title, **values):
            return checked(
                client.post(
                    f"/modules/mnemosyne/api/w/{wid}/resources",
                    json={"kind": kind, "title": title, "status": "open", **values},
                ),
                201,
            )

        note = create("note", "Pilot Note", content="Saved original")
        second = create("note", "Second Note", content="Second original")
        task = create("task", "Pilot Task")
        base = origin + "/app/modules/mnemosyne"

        def link(route):
            return base + "?" + str(httpx.QueryParams({"nav": "1", "route": route}))

        notes = f"/w/{wid}/notes?note=" + note["id"]
        tasks = f"/w/{wid}/tasks?taskView=all"

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(reduced_motion="reduce")
            page = context.new_page()
            page.on("dialog", lambda dialog: dialog.accept())
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            # Use the real login page instead of inserting a fabricated session cookie.
            page.goto(link(notes))
            page.locator("#username").fill("pilot-owner")
            page.locator("#password").fill(password)
            page.get_by_role("button", name="Sign in", exact=True).click()

            def child():
                return page.frame_locator("#module-application")

            def route_is(route):
                expect(page).to_have_url(link(route))

            def note_is(text="Saved original"):
                expect(child().locator("#markdown")).to_have_value(text)
                expect(child().locator("#markdown")).to_be_visible()

            def tasks_visible():
                expect(child().locator('.sidebar [data-view="task"].active')).to_be_visible()
                expect(child().locator('[data-open-task="' + task["id"] + '"]')).to_be_visible()

            note_is()
            route_is(notes)
            assert page.frames[1].evaluate("window.origin") == "null"
            passed("Authenticated direct deep link and opaque iframe isolation")
            marker = secrets.token_hex(8)
            page.frames[1].evaluate("marker => {window.navigationProofMarker = marker;}", marker)
            duplicate_length = page.evaluate("history.length")
            child().locator('.sidebar [data-view="note"]').click()
            route_is(notes)
            page.wait_for_function("!document.querySelector('iframe').hasAttribute('aria-busy')")
            assert page.evaluate("history.length") == duplicate_length

            initial = page.evaluate("history.length")
            child().locator('.sidebar [data-view="task"]').click()
            # Today is default; use All to make the no-date task visible.
            child().locator('.tab[data-task-view="all"]').click()
            tasks_visible()
            route_is(tasks)
            assert page.frames[1].evaluate("window.navigationProofMarker") == marker
            page.go_back()
            expect(child().locator('.tab[data-task-view="today"]')).to_have_attribute(
                "aria-selected", "true"
            )
            page.go_back()
            note_is()
            route_is(notes)
            page.go_forward()
            page.go_forward()
            tasks_visible()
            route_is(tasks)
            passed("Notes -> Tasks -> Back -> Notes; Back -> Forward")

            child().locator('[data-open-task="' + task["id"] + '"]').click()
            expect(child().locator("#drawer")).to_have_attribute("aria-hidden", "false")
            detail = tasks + "&task=" + task["id"]
            route_is(detail)
            page.go_back()
            tasks_visible()
            expect(child().locator("#drawer")).to_have_attribute("aria-hidden", "true")
            page.go_forward()
            route_is(detail)
            expect(child().locator("#drawer .drawer-title")).to_have_value("Pilot Task")
            passed("Tasks -> task detail -> Back -> Tasks; Forward restores task detail")

            # Exercise real module switcher and unmodified Chronos.
            child().locator('[data-act="apps-menu"]').click()
            child().get_by_role("menuitem", name="Chronos", exact=True).click()
            expect(page).to_have_url(origin + "/app/modules/chronos")
            expect(child().locator("#view")).to_be_visible()
            assert page.frames[1].evaluate("typeof moduleNavigation") == "undefined"
            page.go_back()
            route_is(detail)
            expect(child().locator("#drawer .drawer-title")).to_have_value("Pilot Task")
            page.go_forward()
            expect(page).to_have_url(origin + "/app/modules/chronos")
            page.go_back()
            route_is(detail)
            passed("Mnemosyne -> legacy Chronos -> Back restores previous internal view")

            page.reload()
            route_is(detail)
            expect(child().locator("#drawer .drawer-title")).to_have_value("Pilot Task")
            passed("Page reload reconstructs task list and selected detail")

            cdp = context.new_cdp_session(page)
            for button, buttons in [("back", 8), ("forward", 16)]:
                for event in ["mousePressed", "mouseReleased"]:
                    cdp.send(
                        "Input.dispatchMouseEvent",
                        {
                            "type": event,
                            "x": 5,
                            "y": 5,
                            "button": button,
                            "buttons": buttons if event == "mousePressed" else 0,
                            "clickCount": 1,
                        },
                    )
                if button == "back":
                    tasks_visible()
                    expect(child().locator("#drawer")).to_have_attribute("aria-hidden", "true")
                else:
                    expect(child().locator("#drawer .drawer-title")).to_have_value("Pilot Task")
            passed("Mouse4/Mouse5 native browser traversal restores actual module views")

            page.goto(link(notes))
            note_is()
            child().locator("#markdown").fill("Autosaved before traversal")
            child().locator('.sidebar [data-view="task"]').click()
            route_is(f"/w/{wid}/tasks")
            page.go_back()
            note_is("Autosaved before traversal")
            assert (
                checked(client.get(f"/modules/mnemosyne/api/w/{wid}/resources/{note['id']}"))[
                    "content"
                ]
                == "Autosaved before traversal"
            )
            passed("Unsaved edit flushes before internal click navigation")

            # Unsaved quick-capture text is not a resource yet; it must also survive.
            child().locator('.sidebar [data-view="home"]').click()
            home = f"/w/{wid}/home"
            route_is(home)
            child().locator("#capture-input").fill("Capture draft without submitting")
            child().locator('.sidebar [data-view="task"]').click()
            route_is(f"/w/{wid}/tasks")
            page.go_back()
            expect(child().locator("#capture-input")).to_have_value(
                "Capture draft without submitting"
            )
            page.reload()
            expect(child().locator("#capture-input")).to_have_value(
                "Capture draft without submitting"
            )
            passed("Unsubmitted capture draft survives internal navigation and reload")
            page.goto(link(notes))
            note_is("Autosaved before traversal")
            child().locator('.sidebar [data-view="task"]').click()
            route_is(f"/w/{wid}/tasks")
            page.go_back()
            note_is("Autosaved before traversal")

            # Refuse real gateway PUTs in the browser; GET/auth/backend remain real.
            def fail_saves(request_route):
                if request_route.request.method == "PUT":
                    request_route.fulfill(
                        status=503,
                        content_type="application/json",
                        body='{"detail":"Pilot save failure"}',
                    )
                else:
                    request_route.continue_()

            page.route("**/modules/mnemosyne/api/w/**/resources/*", fail_saves)
            child().locator("#markdown").fill("Retained after failed save")
            page.wait_for_function(
                "Object.keys(sessionStorage).some(k => k.startsWith('nexus.navigation.drafts') && sessionStorage[k].includes('Retained after failed save'))"
            )
            page.go_forward()
            expect(child().locator('.sidebar [data-view="task"].active')).to_be_visible()
            expect(child().locator("#navigation-recovery")).to_contain_text("Recover draft")
            page.go_back()
            note_is("Retained after failed save")
            page.reload()
            note_is("Retained after failed save")
            assert "Retained" not in page.url
            passed("Failed-save draft survives traversal and full page reload outside URL")

            # Cross-module traversal unmounts the editor; checkpoint must survive it too.
            page.go_forward()
            child().locator('[data-act="apps-menu"]').click()
            child().get_by_role("menuitem", name="Chronos", exact=True).click()
            # Existing guard asks to stay/discard on a failing save; choose Stay here.
            expect(child().locator("#dialog")).to_be_visible()
            child().get_by_role("button", name="Stay here", exact=True).click()
            expect(page).to_have_url(link(f"/w/{wid}/tasks"))
            # Browser navigation bypasses the click guard but never loses the checkpoint.
            page.goto(origin + "/app/modules/chronos")
            expect(page).to_have_url(origin + "/app/modules/chronos")
            expect(child().locator("#view")).to_be_visible()
            page.go_back()
            expect(child().locator("#navigation-recovery")).to_contain_text("Recover draft")
            child().locator('[data-act="recover-navigation-draft"]').first.click()
            note_is("Retained after failed save")
            page.unroute("**/modules/mnemosyne/api/w/**/resources/*", fail_saves)
            child().locator('[data-act="retry-save"]').first.click()
            expect(child().locator(".save-status")).to_contain_text("Saved")
            passed("Failed-save guard and draft recovery across real module unmount")

            # Conflict is a real optimistic-concurrency rejection from Mnemosyne.
            page.route("**/modules/mnemosyne/api/w/**/resources/*", fail_saves)
            child().locator("#markdown").fill("My conflicting draft")
            latest = checked(client.get(f"/modules/mnemosyne/api/w/{wid}/resources/{note['id']}"))
            checked(
                client.put(
                    f"/modules/mnemosyne/api/w/{wid}/resources/{note['id']}",
                    json={
                        "kind": "note",
                        "title": latest["title"],
                        "content": "Remote saved edit",
                        "revision": latest["revision"],
                    },
                )
            )
            page.unroute("**/modules/mnemosyne/api/w/**/resources/*", fail_saves)
            child().locator('.sidebar [data-view="task"]').click()
            expect(child().locator("#dialog")).to_be_visible()
            child().get_by_role("button", name="Stay here", exact=True).click()
            note_is("My conflicting draft")
            child().get_by_role("button", name="Use saved", exact=True).click()
            note_is("Remote saved edit")
            passed(
                "Real backend revision conflict retains local text until explicit recovery choice"
            )

            page.goto(link(f"/w/{other_wid}/home"))
            expect(child().locator(".ws-name")).to_have_text("Other Workspace")
            page.goto(link(notes))
            note_is("Remote saved edit")
            expect(child().locator(".ws-name")).to_have_text("Pilot Workspace")
            passed("Deep links restore their own workspace independently of last-opened workspace")

            child().locator('[data-act="preview-mode"]').click()
            route_is(notes + "&preview=1")
            expect(child().locator("#preview")).to_be_visible()
            page.go_back()
            note_is("Remote saved edit")
            child().locator("#search").fill("Pilot")
            route_is(f"/w/{wid}/search")
            expect(child().locator(".search-page")).to_be_visible()
            assert "Pilot" not in page.url
            page.go_back()
            note_is("Remote saved edit")
            passed(
                "Preview and search view participate in history without putting search text in URLs"
            )

            missing = f"/w/{wid}/notes?note=00000000-0000-0000-0000-000000000000"
            page.goto(link(missing))
            expect(child().locator("#view")).to_contain_text("Resource not found")
            route_is(missing)
            passed("Missing-resource deep link retains its address and shows an error")

            # Legacy bootstrap path remains valid with the new host and module.
            page.goto(base + "?" + str(httpx.QueryParams({"path": f"/w/{wid}/r/{second['id']}"})))
            note_is("Second original")
            passed("Legacy resource deep-link URL remains valid")
            page.screenshot(path=str(tmp_path / "navigation-pilot.png"))
            # The host account action must not silently erase retained capture drafts.
            page.evaluate("document.querySelector('#logout').click()")
            expect(page.locator("#dialog")).to_be_visible()
            expect(page.locator("#dialog")).to_contain_text("Sign out with unsaved drafts?")
            page.get_by_role("button", name="Cancel", exact=True).click()
            note_is("Second original")
            page.evaluate("document.querySelector('#logout').click()")
            page.get_by_role("button", name="Sign out and clear tab drafts", exact=True).click()
            expect(page.locator("#auth-form")).to_be_visible()
            assert not page.evaluate(
                "Object.keys(sessionStorage).some(k => k.startsWith('nexus.navigation.drafts.v1:'))"
            )
            passed(
                "Sign-out warns before clearing retained drafts and revokes the session normally"
            )
            assert not errors, errors
            result = {
                "browser": browser.version,
                "checks": checks,
                "initial_history_length": initial,
                "scope": "Real HTTP apps; disposable process broker; no Docker or deployment",
            }
            (tmp_path / "navigation-results.json").write_text(
                json.dumps(result, indent=2), encoding="utf-8"
            )
            print("ARTIFACTS:", tmp_path)
            browser.close()
    finally:
        for name in module_ports:
            try:
                client.post(f"/api/v1/modules/{name}/disable")
            except httpx.HTTPError:
                pass
        client.close()
        server.terminate()
        server.wait(timeout=10)
        log.close()
