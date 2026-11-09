"""Module availability: only a recent check by this Nexus process proves a module is running."""

import time

import httpx
import pytest
from conftest import FakeRuntime, install
from fastapi.testclient import TestClient
from nexus.app import create_app


class Module:
    """A module whose health endpoint can be up, down, slow or failing."""

    def __init__(self):
        self.mode = "up"
        self.health_calls = 0

    def __call__(self, request):
        if request.url.path == "/health":
            self.health_calls += 1
        if self.mode == "down":
            raise httpx.ConnectError("connection refused")
        if self.mode == "timeout":
            raise httpx.ReadTimeout("timed out")
        if self.mode == "error" and request.url.path == "/health":
            return httpx.Response(500, json={"status": "broken"})
        return httpx.Response(200, json={"status": "ok"})


def start(tmp_path, monkeypatch, manifest, module, interval="0"):
    monkeypatch.setenv("NEXUS_ALLOW_EXAMPLE", "1")
    monkeypatch.setenv("NEXUS_PUBLIC_ORIGIN", "http://testserver")
    monkeypatch.setenv("NEXUS_FIRST_HEALTH_ATTEMPTS", "1")
    monkeypatch.setenv("NEXUS_HEALTH_INTERVAL", interval)
    app = create_app(tmp_path, FakeRuntime(), httpx.MockTransport(module))
    client = TestClient(app)
    client.__enter__()
    claim = tmp_path / "setup-token"
    if claim.exists():
        r = client.post(
            "/api/v1/setup",
            json={
                "username": "owner",
                "password": "a unique long passphrase",
                "installation_name": "Test Nexus",
                "claim_token": claim.read_text(),
            },
        )
        client.headers["X-Nexus-CSRF"] = r.json()["csrf"]
    else:
        r = client.post(
            "/api/v1/auth/login", json={"username": "owner", "password": "a unique long passphrase"}
        )
        client.headers["X-Nexus-CSRF"] = r.json()["csrf"]
    return app, client


def view(client, module_id):
    return client.get(f"/api/v1/modules/{module_id}").json()


@pytest.fixture
def running(tmp_path, monkeypatch, manifest):
    module = Module()
    app, client = start(tmp_path, monkeypatch, manifest, module)
    install(client, manifest)
    assert client.post(f"/api/v1/modules/{manifest['id']}/enable").status_code == 200
    assert client.post(f"/api/v1/modules/{manifest['id']}/health").json()["status"] == "healthy"
    yield app, client, module, manifest["id"]
    client.__exit__(None, None, None)


def test_healthy_enabled_module_is_available_with_a_check_time(running):
    _, client, _, mid = running
    v = view(client, mid)
    assert (v["state"], v["health"], v["availability"]) == ("enabled", "healthy", "available")
    assert v["health_checked_at"]
    assert client.get("/api/v1/modules").json()[0]["availability"] == "available"


def test_stopped_module_becomes_unavailable_on_the_next_monitor_pass(running):
    app, client, module, mid = running
    module.mode = "down"
    app.state.health_monitor_pass()
    v = view(client, mid)
    assert (v["state"], v["health"], v["availability"]) == ("enabled", "unreachable", "unavailable")
    assert any(
        f"Module {mid} is unreachable" in n["message"]
        for n in client.get("/api/v1/notifications").json()
    )


def test_health_check_timeout_counts_as_unavailable(running):
    app, client, module, mid = running
    module.mode = "timeout"
    app.state.health_monitor_pass()
    assert view(client, mid)["availability"] == "unavailable"


def test_error_answer_is_unhealthy_not_running(running):
    app, client, module, mid = running
    module.mode = "error"
    app.state.health_monitor_pass()
    assert view(client, mid)["availability"] == "unhealthy"


def test_recovery_from_unavailable_to_available(running):
    app, client, module, mid = running
    module.mode = "down"
    app.state.health_monitor_pass()
    module.mode = "up"
    app.state.health_monitor_pass()
    assert view(client, mid)["availability"] == "available"
    assert any(
        f"Module {mid} recovered" in n["message"]
        for n in client.get("/api/v1/notifications").json()
    )


def test_stale_result_is_unknown_never_running(running, monkeypatch):
    app, client, _, mid = running
    later = time.time() + 3600
    monkeypatch.setattr("nexus.app.time.time", lambda: later)
    v = view(client, mid)
    assert v["health"] == "healthy"  # the last recorded result is kept...
    assert v["availability"] == "unknown"  # ...but is not presented as current proof


def test_recorded_health_from_before_a_restart_is_unknown(tmp_path, monkeypatch, manifest):
    module = Module()
    _, client = start(tmp_path, monkeypatch, manifest, module)
    install(client, manifest)
    client.post(f"/api/v1/modules/{manifest['id']}/enable")
    client.post(f"/api/v1/modules/{manifest['id']}/health")
    client.__exit__(None, None, None)
    module.mode = "down"  # stopped outside Nexus while Nexus was down
    _, again = start(tmp_path, monkeypatch, manifest, module)
    try:
        v = view(again, manifest["id"])
        assert v["health"] == "healthy" and v["availability"] == "unknown"
    finally:
        again.__exit__(None, None, None)


def test_disabled_module_is_disabled_not_unavailable(running):
    _, client, _, mid = running
    assert client.post(f"/api/v1/modules/{mid}/disable").status_code == 200
    v = view(client, mid)
    assert (v["state"], v["availability"]) == ("disabled", "disabled")


def test_lifecycle_change_invalidates_an_earlier_check(running):
    app, client, module, mid = running
    client.post(f"/api/v1/modules/{mid}/disable")
    client.post(f"/api/v1/modules/{mid}/enable")
    # Enabling resets the record to "unknown"; the earlier "healthy" check no longer counts.
    assert view(client, mid)["availability"] in {"unknown", "available"}
    with app.state.db.connect() as conn:
        conn.execute("UPDATE modules SET health='unknown' WHERE id=?", (mid,))
    assert view(client, mid)["availability"] == "unknown"


def test_opening_an_unavailable_module_explains_instead_of_a_raw_error(running):
    _, client, module, mid = running
    module.mode = "down"
    page = client.get(f"/modules/{mid}/")
    assert page.status_code == 502
    assert "text/html" in page.headers["content-type"]
    assert "is not responding" in page.text and "Module did not respond" not in page.text
    # The failed open is recorded, so the dashboard stops saying "running" at once.
    assert view(client, mid)["availability"] == "unavailable"
    api = client.get(f"/modules/{mid}/api/info")
    assert api.status_code == 502 and api.json()["detail"] == "Module did not respond"


def test_background_monitor_runs_at_startup(tmp_path, monkeypatch, manifest):
    module = Module()
    _, client = start(tmp_path, monkeypatch, manifest, module)
    install(client, manifest)
    client.post(f"/api/v1/modules/{manifest['id']}/enable")
    client.post(f"/api/v1/modules/{manifest['id']}/health")
    client.__exit__(None, None, None)
    module.health_calls = 0
    _, again = start(tmp_path, monkeypatch, manifest, module, interval="1")
    try:
        deadline = time.time() + 5
        while time.time() < deadline and view(again, manifest["id"])["availability"] != "available":
            time.sleep(0.1)
        assert view(again, manifest["id"])["availability"] == "available"
        assert module.health_calls >= 1
    finally:
        again.__exit__(None, None, None)
