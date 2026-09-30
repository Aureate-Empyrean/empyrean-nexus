import json
import time

from conftest import install
from nexus.db import MIGRATIONS, Database


def test_claim_token_setup_and_session_security(env):
    client, _, db, path, _ = env
    assert client.get("/api/v1/setup").json() == {"required": True}
    assert client.get("/api/v1/system").status_code == 401
    body = {
        "username": "owner",
        "password": "a unique long passphrase",
        "installation_name": "Home",
        "claim_token": "x" * 32,
    }
    assert client.post("/api/v1/setup", json=body).status_code == 403
    body["claim_token"] = (path / "setup-token").read_text()
    response = client.post("/api/v1/setup", json=body)
    assert response.status_code == 201
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert not (path / "setup-token").exists()
    assert client.post("/api/v1/setup", json=body).status_code == 409
    with db.connect() as conn:
        assert conn.execute("SELECT password FROM users").fetchone()[0].startswith("$argon2id$")
        assert (
            conn.execute("SELECT token FROM sessions").fetchone()[0]
            != client.cookies["nexus_session"]
        )


def test_auth_csrf_origin_logout_and_expiry(owner):
    client, _, db, _, _ = owner
    assert client.get("/api/v1/auth/session").status_code == 200
    assert (
        client.patch(
            "/api/v1/settings", json={"installation_name": "X"}, headers={"X-Nexus-CSRF": "bad"}
        ).status_code
        == 403
    )
    assert (
        client.patch(
            "/api/v1/settings",
            json={"installation_name": "X"},
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/system").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "owner", "password": "wrong long password"}
        ).status_code
        == 401
    )
    response = client.post(
        "/api/v1/auth/login", json={"username": "owner", "password": "a unique long passphrase"}
    )
    assert response.status_code == 200
    with db.connect() as conn:
        conn.execute("UPDATE sessions SET expires=?", (int(time.time()) - 1,))
    assert client.get("/api/v1/system").status_code == 401


def test_lifecycle_routing_revocation_and_port_registry(owner, manifest):
    client, runtime, db, _, requests = owner
    install(client, manifest)
    assert client.get("/modules/empyrean-example/").status_code == 409
    other = json.loads(json.dumps(manifest))
    other["id"] = "other"
    other["events"]["produces"] = []
    assert (
        client.post(
            "/api/v1/modules", json={"manifest": other, "grants": other["capabilities"]}
        ).status_code
        == 409
    )
    assert client.post("/api/v1/modules/empyrean-example/enable").status_code == 200
    token = runtime.tokens[manifest["id"]]
    headers = {"Authorization": "Bearer " + token}
    assert client.get("/api/v1/module/context", headers=headers).status_code == 200
    page = client.get("/modules/empyrean-example/")
    assert page.status_code == 200
    assert "sandbox allow-scripts" in page.headers["content-security-policy"]
    assert "set-cookie" not in page.headers and "location" not in page.headers
    assert "cookie" not in requests[-1].headers
    assert "authorization" not in requests[-1].headers
    assert client.post("/api/v1/modules/empyrean-example/health").json()["status"] == "healthy"
    assert client.post("/api/v1/modules/empyrean-example/disable").status_code == 200
    assert client.get("/api/v1/module/context", headers=headers).status_code == 401
    assert client.get("/modules/empyrean-example/").status_code == 409
    assert client.delete("/api/v1/modules/empyrean-example").status_code == 200
    assert client.get("/api/v1/modules").json() == []
    assert client.get("/healthz").status_code == 200
    install(client, other)  # Reservation is released only after successful uninstall.
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0] >= 8


def test_events_and_permissions(owner, manifest):
    client, runtime, _, _, _ = owner
    install(client, manifest)
    client.post("/api/v1/modules/empyrean-example/enable")
    headers = {"Authorization": "Bearer " + runtime.tokens[manifest["id"]]}
    assert (
        client.post(
            "/api/v1/module/events", headers=headers, json={"type": "other.secret", "payload": {}}
        ).status_code
        == 403
    )
    response = client.post(
        "/api/v1/module/events",
        headers=headers,
        json={"type": "empyrean-example.ping", "payload": {"hello": "world"}},
    )
    assert response.status_code == 201
    envelope = response.json()["event"]
    assert envelope["source"] == manifest["id"] and envelope["schema_version"] == 1
    consumed = client.get("/api/v1/module/events", headers=headers).json()
    assert consumed["events"][0]["event"] == envelope
    assert (
        client.get(
            "/api/v1/module/events?after=" + str(consumed["next_cursor"]), headers=headers
        ).json()["events"]
        == []
    )
    assert (
        client.post(
            "/api/v1/module/events",
            headers=headers,
            json={"type": "empyrean-example.ping", "source": "nexus", "payload": {}},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/module/notifications", headers=headers, json={"message": "Hello"}
        ).status_code
        == 201
    )
    assert client.get("/api/v1/notifications").json()[0]["message"] == "Hello"
    assert (
        client.post(
            "/api/v1/module/events",
            headers=headers,
            json={"type": "empyrean-example.ping", "payload": {"x": "a" * 20000}},
        ).status_code
        == 422
    )


def test_ungranted_capabilities_are_denied(owner, manifest):
    client, runtime, _, _, _ = owner
    manifest["capabilities"] = []
    manifest["events"] = {"produces": [], "consumes": []}
    manifest["references"] = {"version": 1, "read": [], "resolve": []}
    install(client, manifest)
    client.post("/api/v1/modules/empyrean-example/enable")
    headers = {"Authorization": "Bearer " + runtime.tokens[manifest["id"]]}
    assert client.get("/api/v1/module/events", headers=headers).status_code == 403
    assert (
        client.post(
            "/api/v1/module/notifications", headers=headers, json={"message": "No"}
        ).status_code
        == 403
    )


def test_failure_is_retryable_and_revokes_access(owner, manifest):
    client, runtime, _, _, _ = owner
    install(client, manifest)
    runtime.fail = True
    assert client.post("/api/v1/modules/empyrean-example/enable").status_code == 502
    assert client.get("/api/v1/modules/empyrean-example").json()["state"] == "error"
    assert client.delete("/api/v1/modules/empyrean-example").status_code == 502
    assert len(client.get("/api/v1/modules").json()) == 1
    runtime.fail = False
    assert client.post("/api/v1/modules/empyrean-example/disable").status_code == 200
    assert client.delete("/api/v1/modules/empyrean-example").status_code == 200


def test_review_grants_exports_and_body_limits(owner, manifest):
    client, _, _, _, _ = owner
    assert (
        client.post("/api/v1/modules/validate", json=manifest).json()["provenance"] == "community"
    )
    assert (
        client.post("/api/v1/modules", json={"manifest": manifest, "grants": []}).status_code == 422
    )
    install(client, manifest)
    exported = client.get("/api/v1/export").json()
    assert exported["format"] == "empyrean-nexus-export"
    assert "token" not in exported["modules"][0]
    assert "password" not in json.dumps(exported)
    assert client.post("/api/v1/modules/validate", content=b"x" * 70000).status_code == 413
    assert client.get("/api/v1/openapi.json").json()["info"]["version"] == "0.1.3"


def test_schema_migrations_persist_and_reject_downgrade(tmp_path):
    import pytest

    path = tmp_path / "db.sqlite3"
    db = Database(path)
    with db.connect() as conn:
        conn.execute("INSERT INTO settings VALUES('a','b')")
    db = Database(path)
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
        assert conn.execute("SELECT value FROM settings").fetchone()[0] == "b"
        conn.execute("PRAGMA user_version=999")
    with pytest.raises(RuntimeError):
        Database(path)


def test_login_rate_limit(env):
    client, _, _, _, _ = env
    body = {"username": "nobody", "password": "a long enough invalid password"}
    for _ in range(10):
        assert client.post("/api/v1/auth/login", json=body).status_code == 401
    assert client.post("/api/v1/auth/login", json=body).status_code == 429


def test_non_subscribed_events_are_hidden_and_cursor_advances(owner, manifest):
    client, runtime, db, _, _ = owner
    manifest["events"]["consumes"] = ["other-module.allowed"]
    install(client, manifest)
    client.post("/api/v1/modules/empyrean-example/enable")
    headers = {"Authorization": "Bearer " + runtime.tokens[manifest["id"]]}
    client.post(
        "/api/v1/module/events",
        headers=headers,
        json={"type": "empyrean-example.ping", "payload": {}},
    )
    response = client.get("/api/v1/module/events", headers=headers).json()
    assert response["events"] == [] and response["next_cursor"] == 1
    with db.connect() as conn:
        conn.execute("UPDATE events SET seq=100")
    assert client.get("/api/v1/module/events?after=1", headers=headers).json()["retention_gap"]


def test_restart_recovers_transitions_and_missing_modules(owner, manifest, monkeypatch):
    from fastapi.testclient import TestClient
    from nexus.app import create_app

    client, runtime, db, path, _ = owner
    install(client, manifest)
    client.post("/api/v1/modules/empyrean-example/enable")
    runtime.fail = True
    with TestClient(create_app(path, runtime)) as restarted:
        assert restarted.get("/healthz").status_code == 200
    with db.connect() as conn:
        row = conn.execute("SELECT state,token FROM modules").fetchone()
        assert row["state"] == "error" and row["token"] is None
        conn.execute("UPDATE modules SET state='enabling',token='secret'")
    with TestClient(create_app(path, runtime)):
        pass
    with db.connect() as conn:
        row = conn.execute("SELECT state,token FROM modules").fetchone()
        assert row["state"] == "error" and row["token"] is None


def test_spa_routes_and_real_activity(owner):
    client, _, _, _, _ = owner
    for route in [
        "/app/overview",
        "/app/modules",
        "/app/activity",
        "/app/settings",
        "/app/modules/community-example",
    ]:
        response = client.get(route)
        assert response.status_code == 200 and 'type="module"' in response.text
    assert client.get("/api/v1/missing").status_code == 404
    activity = client.get("/api/v1/activity/entries?limit=1").json()
    assert activity["items"][0]["kind"] == "setup.completed"
    assert activity["items"][0]["actor"] == "owner"
    client.patch("/api/v1/settings", json={"installation_name": "Changed"})
    newest = client.get("/api/v1/activity/entries?limit=1").json()
    assert newest["items"][0]["kind"] == "settings.changed" and newest["has_more"]
    older = client.get("/api/v1/activity/entries", params={"before": newest["next_cursor"]}).json()
    assert older["items"][0]["kind"] == "setup.completed"


def test_activity_entries_require_owner_and_preserve_legacy_contract(owner):
    client, _, _, _, _ = owner
    response = client.get("/api/v1/activity/entries")
    assert response.status_code == 200
    assert response.json() == client.get("/api/v1/activity").json()
    assert response.json()["items"][0]["kind"] == "setup.completed"
    client.cookies.clear()
    assert client.get("/api/v1/activity/entries").status_code == 401
    assert client.get("/api/v1/activity").status_code == 401


def test_restart_revokes_modules_incompatible_with_running_nexus(owner, manifest):
    from fastapi.testclient import TestClient
    from nexus.app import create_app

    client, runtime, db, path, _ = owner
    install(client, manifest)
    client.post("/api/v1/modules/empyrean-example/enable")
    token = runtime.tokens["empyrean-example"]
    assert (
        client.get(
            "/api/v1/module/context", headers={"Authorization": "Bearer " + token}
        ).status_code
        == 200
    )
    # Simulate a Nexus upgrade outside the range the installed module declared.
    with db.connect() as conn:
        stored = json.loads(conn.execute("SELECT manifest FROM modules").fetchone()[0])
        stored["nexus"] = ">=0.0.1,<0.1.0"
        conn.execute("UPDATE modules SET manifest=?", (json.dumps(stored),))
    before = len(runtime.calls)
    with TestClient(create_app(path, runtime)) as restarted:
        assert (
            restarted.get(
                "/api/v1/module/context", headers={"Authorization": "Bearer " + token}
            ).status_code
            == 401
        )
    with db.connect() as conn:
        row = conn.execute("SELECT state,token,resolver_key,health FROM modules").fetchone()
        assert (row["state"], row["token"], row["resolver_key"], row["health"]) == (
            "error",
            None,
            None,
            "incompatible",
        )
        assert conn.execute(
            "SELECT 1 FROM audit WHERE action='module.compatibility.failed'"
        ).fetchone()
        assert conn.execute(
            "SELECT 1 FROM notifications WHERE message LIKE '%does not support Nexus%'"
        ).fetchone()
    # Runtime reconciliation is not attempted for a module whose access was revoked.
    assert ("status", "empyrean-example") not in runtime.calls[before:]
