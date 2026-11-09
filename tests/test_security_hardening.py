import hashlib
import os
import sqlite3
import stat
import time

import pytest
from conftest import install
from fastapi.testclient import TestClient
from nexus import manage
from nexus.app import SESSION_MAX
from nexus.db import MIGRATIONS, Database


def _admin_headers(path):
    key = (path / "admin-key").read_text().strip()
    return {"X-Nexus-Admin-Key": key, "X-Nexus-Admin-Client": "nexus.manage"}


def test_session_provenance_issuance_and_revocation_audit(owner):
    client, _, db, _, _ = owner
    with db.connect() as conn:
        row = conn.execute(
            "SELECT created_at,expires,kind,issued_by,revoked_at FROM sessions"
        ).fetchone()
        assert row["kind"] == "interactive"
        assert row["issued_by"] == "login"
        assert row["revoked_at"] is None
        assert row["created_at"] <= int(time.time()) + 2
        assert row["expires"] == row["created_at"] + SESSION_MAX
        assert (
            conn.execute("SELECT COUNT(*) FROM audit WHERE action='setup.completed'").fetchone()[0]
            == 1
        )

    assert client.post("/api/v1/auth/logout").status_code == 200
    with db.connect() as conn:
        row = conn.execute("SELECT revoked_at,expires FROM sessions").fetchone()
        assert row["revoked_at"] is not None
        assert row["expires"] == row["revoked_at"]
        assert (
            conn.execute("SELECT COUNT(*) FROM audit WHERE action='auth.logout'").fetchone()[0] == 1
        )
    assert client.get("/api/v1/system").status_code == 401


def test_session_absolute_lifetime_revocation_and_malformed_tokens(owner):
    client, _, db, _, _ = owner

    def login():
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "owner", "password": "a unique long passphrase"},
        )
        assert response.status_code == 200

    with db.connect() as conn:
        conn.execute(
            "UPDATE sessions SET created_at=? WHERE revoked_at IS NULL",
            (int(time.time()) - SESSION_MAX - 5,),
        )
    assert client.get("/api/v1/system").status_code == 401

    login()
    with db.connect() as conn:
        conn.execute(
            "UPDATE sessions SET created_at=? WHERE revoked_at IS NULL",
            (int(time.time()) + 120,),
        )
    assert client.get("/api/v1/system").status_code == 401

    login()
    with db.connect() as conn:
        conn.execute(
            "UPDATE sessions SET revoked_at=? WHERE revoked_at IS NULL",
            (int(time.time()),),
        )
    assert client.get("/api/v1/system").status_code == 401

    client.cookies.set("nexus_session", "short")
    assert client.get("/api/v1/system").status_code == 401


def test_admin_key_is_loopback_scoped_auditable_and_does_not_create_sessions(owner):
    client, _, db, path, _ = owner
    headers = _admin_headers(path)
    with db.connect() as conn:
        before = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    admin = TestClient(client.app, client=("127.0.0.1", 50000), headers=headers)
    assert admin.get("/api/v1/modules").status_code == 200
    assert admin.patch("/api/v1/settings", json={"installation_name": "No"}).status_code == 403
    assert admin.get("/modules/example/").status_code == 403
    assert (
        admin.post(
            "/api/v1/modules/example/external-origins",
            json={"origin": "https://example.com"},
        ).status_code
        == 403
    )

    remote = TestClient(client.app, client=("10.0.0.5", 50000), headers=headers)
    assert remote.get("/api/v1/modules").status_code == 401
    wrong = TestClient(
        client.app,
        client=("127.0.0.1", 50000),
        headers={"X-Nexus-Admin-Key": "wrong"},
    )
    assert wrong.get("/api/v1/modules").status_code == 401

    with db.connect() as conn:
        after = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        row = conn.execute(
            "SELECT actor,action,target FROM audit WHERE action='admin.request' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert after == before
    assert row["actor"] == "host-admin:nexus.manage"
    assert row["target"] == "GET /api/v1/modules"
    if os.name == "posix":
        assert stat.S_IMODE((path / "admin-key").stat().st_mode) == 0o600
    assert headers["X-Nexus-Admin-Key"] not in client.get("/api/v1/system").text


def test_admin_key_deploys_and_audits_without_owner_browser_session(owner, manifest):
    client, runtime, db, path, _ = owner
    admin = TestClient(client.app, client=("127.0.0.1", 50000), headers=_admin_headers(path))
    with db.connect() as conn:
        before = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    response = admin.post(
        "/api/v1/modules",
        json={"manifest": manifest, "grants": manifest["capabilities"]},
    )
    assert response.status_code == 201, response.text
    assert admin.post("/api/v1/modules/empyrean-example/enable").status_code == 200
    assert admin.post("/api/v1/modules/empyrean-example/health").json()["status"] == "healthy"

    with db.connect() as conn:
        after = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        actor = conn.execute(
            "SELECT actor FROM audit WHERE action='module.installed' ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
    assert after == before
    assert actor == "host-admin:nexus.manage"
    assert runtime.tokens[manifest["id"]]


def test_module_token_cannot_reach_owner_routes(owner, manifest):
    client, runtime, _, _, _ = owner
    install(client, manifest)
    assert client.post("/api/v1/modules/empyrean-example/enable").status_code == 200
    token = runtime.tokens[manifest["id"]]

    module_client = TestClient(client.app, headers={"Authorization": "Bearer " + token})
    assert module_client.get("/api/v1/modules").status_code == 401
    assert module_client.post("/api/v1/modules/empyrean-example/disable").status_code == 401


def test_deployment_cli_uses_scoped_admin_key_not_cookies(tmp_path, monkeypatch):
    key_path = tmp_path / "admin-key"
    key = "deployment-test-key-" + "x" * 32
    key_path.write_text(key + "\n")
    key_path.chmod(0o600)
    monkeypatch.setenv("NEXUS_ADMIN_KEY_FILE", str(key_path))

    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(manage.httpx, "Client", FakeClient)
    with manage.admin_client():
        pass

    assert captured["headers"]["X-Nexus-Admin-Key"] == key
    assert captured["headers"]["X-Nexus-Admin-Client"] == "nexus.manage"
    assert "cookies" not in captured
    assert "nexus_session" not in repr(captured)

    if os.name == "posix":
        key_path.chmod(0o644)
        with pytest.raises(RuntimeError, match="readable only"):
            with manage.admin_client():
                pass


def test_legacy_session_row_remains_usable_after_migration(env):
    client, _, db, _, _ = env
    raw = "legacy-test-session-token-1234567890"
    now = int(time.time())
    with db.connect() as conn:
        conn.execute("INSERT INTO users VALUES('u','owner','hash')")
        conn.execute(
            "INSERT INTO sessions(token,user_id,csrf,expires,created_at,kind,issued_by,revoked_at)"
            " VALUES(?,?,?,?,?,?,?,NULL)",
            (
                hashlib.sha256(raw.encode()).hexdigest(),
                "u",
                "csrf",
                now + 100,
                now - 100,
                "legacy",
                "legacy",
            ),
        )
    legacy = TestClient(client.app, cookies={"nexus_session": raw})
    assert legacy.get("/api/v1/modules").status_code == 200


def test_session_migration_backfills_legacy_rows(tmp_path):
    path = tmp_path / "nexus.sqlite3"
    connection = sqlite3.connect(path)
    for index, script in enumerate(MIGRATIONS[:5], start=1):
        connection.executescript("BEGIN;" + script + f"PRAGMA user_version={index};COMMIT;")
    connection.execute("INSERT INTO users VALUES('u','owner','hash')")
    expires = int(time.time()) + 100
    connection.execute(
        "INSERT INTO sessions(token,user_id,csrf,expires) VALUES('token','u','csrf',?)",
        (expires,),
    )
    connection.commit()
    connection.close()

    Database(path)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    row = connection.execute("SELECT * FROM sessions").fetchone()
    assert connection.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    assert row["created_at"] == expires - SESSION_MAX
    assert row["kind"] == "legacy"
    assert row["issued_by"] == "legacy"
    assert row["revoked_at"] is None
    connection.close()
