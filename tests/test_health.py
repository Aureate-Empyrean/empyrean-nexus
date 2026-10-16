import httpx
from conftest import FakeRuntime, install
from fastapi.testclient import TestClient
from nexus.app import create_app


def started(tmp_path, monkeypatch, manifest, failures):
    """Nexus whose module fails its first `failures` health requests, then answers 200."""
    monkeypatch.setenv("NEXUS_ALLOW_EXAMPLE", "1")
    monkeypatch.setenv("NEXUS_PUBLIC_ORIGIN", "http://testserver")
    monkeypatch.setenv("NEXUS_FIRST_HEALTH_ATTEMPTS", "4")
    monkeypatch.setattr("nexus.app.time.sleep", lambda _: None)
    seen = {"health": 0}

    def module(request):
        if request.url.path == "/health":
            seen["health"] += 1
            if seen["health"] <= failures:
                raise httpx.ConnectError("not listening yet")
        return httpx.Response(200, json={"status": "ok"})

    client = TestClient(create_app(tmp_path, FakeRuntime(), httpx.MockTransport(module)))
    client.__enter__()
    response = client.post(
        "/api/v1/setup",
        json={
            "username": "owner",
            "password": "a unique long passphrase",
            "installation_name": "Test Nexus",
            "claim_token": (tmp_path / "setup-token").read_text(),
        },
    )
    client.headers["X-Nexus-CSRF"] = response.json()["csrf"]
    install(client, manifest)
    assert client.post(f"/api/v1/modules/{manifest['id']}/enable").status_code == 200
    return client, seen


def health_records(client):
    return [
        e["kind"]
        for e in client.get("/api/v1/activity/entries").json()["items"]
        if e["kind"].startswith("module.health.")
    ]


def test_first_check_after_start_waits_for_a_slow_module(tmp_path, monkeypatch, manifest):
    client, seen = started(tmp_path, monkeypatch, manifest, failures=2)
    try:
        assert client.post(f"/api/v1/modules/{manifest['id']}/health").json()["status"] == "healthy"
        assert seen["health"] == 3
        assert health_records(client) == ["module.health.healthy"]
        assert not [
            n for n in client.get("/api/v1/notifications").json() if "unreachable" in n["message"]
        ]
    finally:
        client.__exit__(None, None, None)


def test_real_failures_are_still_reported(tmp_path, monkeypatch, manifest):
    client, seen = started(tmp_path, monkeypatch, manifest, failures=100)
    try:
        url = f"/api/v1/modules/{manifest['id']}/health"
        assert client.post(url).json()["status"] == "unreachable"
        assert seen["health"] == 4
        # Later checks of a known state are single attempts.
        assert client.post(url).json()["status"] == "unreachable"
        assert seen["health"] == 5
    finally:
        client.__exit__(None, None, None)
