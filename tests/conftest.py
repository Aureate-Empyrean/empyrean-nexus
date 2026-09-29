import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from nexus.app import create_app


class FakeRuntime:
    def __init__(self):
        self.tokens = {}
        self.calls = []
        self.fail = False

    def call(self, action, module_id, manifest=None, token=None, resolver_key=None):
        self.calls.append((action, module_id))
        if self.fail:
            raise RuntimeError("Simulated broker outage")
        if action == "enable":
            self.tokens[module_id] = token
        return {"state": "running" if action in {"enable", "status"} else "absent"}

    def target(self, module_id, port):
        return f"http://module-{module_id}:{port}"


@pytest.fixture
def manifest():
    return json.loads(Path("examples/example-module/manifest.json").read_text())


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_ALLOW_EXAMPLE", "1")
    monkeypatch.setenv("NEXUS_PUBLIC_ORIGIN", "http://testserver")
    runtime = FakeRuntime()
    requests = []

    def module(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={"status": "ok"},
            headers={"set-cookie": "evil=1", "location": "https://evil.test"},
        )

    app = create_app(tmp_path, runtime, httpx.MockTransport(module))
    with TestClient(app) as client:
        yield client, runtime, app.state.db, tmp_path, requests


@pytest.fixture
def owner(env):
    client, _, _, path, _ = env
    response = client.post(
        "/api/v1/setup",
        json={
            "username": "owner",
            "password": "a unique long passphrase",
            "installation_name": "Test Nexus",
            "claim_token": (path / "setup-token").read_text(),
        },
    )
    assert response.status_code == 201
    client.headers["X-Nexus-CSRF"] = response.json()["csrf"]
    return env


def install(client, manifest):
    response = client.post(
        "/api/v1/modules", json={"manifest": manifest, "grants": manifest["capabilities"]}
    )
    assert response.status_code == 201, response.text
