"""Module contract: enumeration, backup/restore, in-place updates and development gating."""

import copy
import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from conftest import FakeRuntime
from fastapi.testclient import TestClient
from nexus import updates
from nexus.app import create_app

ITEM = "0192a5d3-7c1e-7b2a-9f4e-3d8c1b6a2e10"
OTHER = "0192a5d4-1b2c-7d3e-8f40-5a6b7c8d9e01"


def ref(module, value, kind="item"):
    return f"nexus:v1:{module}:{kind}:{value}"


class RecordingRuntime(FakeRuntime):
    def __init__(self):
        super().__init__()
        self.keys, self.manifests = {}, {}

    def call(self, action, module_id, manifest=None, token=None, resolver_key=None):
        result = super().call(action, module_id, manifest, token, resolver_key)
        if action == "enable":
            self.keys[module_id], self.manifests[module_id] = resolver_key, manifest
        return result


class FakeModule:
    """A persistent module implementing the contract. Its dict is its own database."""

    def __init__(self, runtime, module_id="library"):
        self.runtime, self.id = runtime, module_id
        self.items = {ITEM: {"title": "Kept", "trashed_at": None}}
        self.edges = []
        self.suspended = False
        self.calls = []
        self.fail = set()
        self.version = "1.0.0"

    def purge(self, now):
        """Automatic retention: 30 days after trashing, unless suspended by a restore."""
        if self.suspended:
            return
        for key, item in list(self.items.items()):
            if item["trashed_at"] and now - datetime.fromisoformat(item["trashed_at"]) > timedelta(
                days=30
            ):
                del self.items[key]

    def __call__(self, request):
        path = request.url.path
        self.calls.append(path)
        if path == "/health":
            return httpx.Response(503 if "health" in self.fail else 200, json={"status": "ok"})
        if request.headers.get("x-nexus-resolver-key") != self.runtime.keys.get(self.id):
            return httpx.Response(403, json={"detail": "Resolver authentication required"})
        if path == "/empyrean/v1/references/outgoing":
            if "enumerate" in self.fail:
                return httpx.Response(503)
            if "loop" in self.fail:
                return httpx.Response(200, json={"references": [], "next_cursor": "same"})
            start = int(request.url.params.get("cursor", "0"))
            limit = int(request.url.params["limit"])
            page = self.edges[start : start + limit]
            following = start + limit if start + limit < len(self.edges) else None
            return httpx.Response(
                200,
                json={"references": page, "next_cursor": str(following) if following else None},
            )
        if path == "/empyrean/v1/backup/export":
            headers = {
                "X-Empyrean-Backup-Module": "wrong" if "identity" in self.fail else self.id,
                "X-Empyrean-Backup-Module-Version": self.version,
                "X-Empyrean-Backup-Format": "library-json",
                "X-Empyrean-Backup-Format-Version": "1",
                "X-Empyrean-Backup-Created-At": datetime.now(timezone.utc).isoformat(),
                "X-Empyrean-Backup-Restorable-By": ">=1.0.0,<2.0.0",
            }
            body = json.dumps({"items": self.items, "edges": self.edges}).encode()
            return httpx.Response(200, content=body, headers=headers)
        if path == "/empyrean/v1/backup/validate":
            try:
                data = json.loads(request.read())
                assert set(data) == {"items", "edges"}
                assert request.headers["x-empyrean-backup-format"] == "library-json"
            except (ValueError, AssertionError, KeyError):
                return httpx.Response(422, json={"detail": "Not a library backup"})
            if "validate" in self.fail:
                return httpx.Response(422, json={"detail": "Rejected"})
            return httpx.Response(200, json={"valid": True})
        if path == "/empyrean/v1/backup/restore":
            if "restore" in self.fail:
                return httpx.Response(500, json={"detail": "Disk full"})
            data = json.loads(request.read())
            self.items, self.edges, self.suspended = data["items"], data["edges"], True
            return httpx.Response(200, json={"restored": True})
        if path == "/empyrean/v1/backup/finalize":
            if "finalize" in self.fail:
                return httpx.Response(500)
            # Retention restarts at restore time instead of the old timestamps.
            for item in self.items.values():
                if item["trashed_at"]:
                    item["trashed_at"] = datetime.now(timezone.utc).isoformat()
            self.suspended = False
            return httpx.Response(200, json={"finalized": True})
        return httpx.Response(404)


def persistent_manifest():
    return {
        "protocol": 1,
        "id": "library",
        "name": "Library",
        "description": "Persistent test module.",
        "version": "1.0.0",
        "publisher": {"name": "Tests", "originalAuthors": ["Tests"]},
        "repository": "https://example.org/library",
        "license": "AGPL-3.0-or-later",
        "nexus": ">=0.1.3,<0.2.0",
        "container": {"image": "sha256:" + "a" * 64, "port": 14333},
        "capabilities": ["storage.data", "blobs.read", "blobs.write", "references.create"],
        "routes": {"ui": "/", "api": "/api", "health": "/health"},
        "events": {"produces": [], "consumes": []},
        "resources": [{"type": "item", "resolvable": True}],
        "references": {"version": 2, "read": [], "resolve": [], "enumerate": True},
        "backup": {"version": 1},
    }


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_PUBLIC_ORIGIN", "http://testserver")
    monkeypatch.setattr(updates, "sleep", lambda seconds: None)
    monkeypatch.setenv("NEXUS_UPDATE_HEALTH_ATTEMPTS", "2")
    runtime = RecordingRuntime()
    module = FakeModule(runtime)
    app = create_app(tmp_path, runtime, httpx.MockTransport(module))
    with TestClient(app) as client:
        setup = client.post(
            "/api/v1/setup",
            json={
                "username": "owner",
                "password": "a unique long passphrase",
                "installation_name": "Lab",
                "claim_token": (tmp_path / "setup-token").read_text(),
            },
        )
        client.headers["X-Nexus-CSRF"] = setup.json()["csrf"]
        manifest = persistent_manifest()
        assert (
            client.post(
                "/api/v1/modules", json={"manifest": manifest, "grants": manifest["capabilities"]}
            ).status_code
            == 201
        )
        assert client.post("/api/v1/modules/library/enable").status_code == 200
        yield client, runtime, module, app.state.db, tmp_path


def bearer(runtime, module_id="library"):
    return {"Authorization": "Bearer " + runtime.tokens[module_id]}


def edges(db, creator="library"):
    with db.connect() as conn:
        return sorted(
            (r["source"], r["target"], r["relation"], r["readers"])
            for r in conn.execute("SELECT * FROM resource_references WHERE creator=?", (creator,))
        )


def owned_edge(target_id, readers=()):
    return {
        "source": ref("library", ITEM),
        "target": ref("library", target_id),
        "relation": "library.related",
        "metadata": {},
        "readers": list(readers),
    }


# --- Manifest rules -------------------------------------------------------------------------


def test_manifest_rules_for_new_contracts():
    from nexus.protocol import validate_manifest

    manifest = persistent_manifest()
    assert validate_manifest(copy.deepcopy(manifest))
    for change, message in (
        (lambda m: m["references"].update(version=1), "requires references.version=2"),
        (lambda m: m.update(nexus=">=0.1.2,<0.2.0"), "excluding 0.1.2"),
        (lambda m: m["capabilities"].remove("storage.data"), "storage.data"),
        (lambda m: m["capabilities"].remove("references.create"), "references.create"),
    ):
        candidate = copy.deepcopy(manifest)
        change(candidate)
        with pytest.raises(ValueError, match=message):
            validate_manifest(candidate)


# --- UUID identity --------------------------------------------------------------------------


def test_v2_owner_requires_canonical_uuid_resource_ids(lab):
    client, runtime, _, _, _ = lab
    headers = bearer(runtime)
    base = {"relation": "library.related", "readers": []}
    for bad in ("42", "sample", ITEM.upper(), ITEM.replace("-", "")):
        response = client.post(
            "/api/v1/module/references",
            json={**base, "source": ref("library", bad), "target": ref("library", OTHER)},
            headers=headers,
        )
        assert response.status_code == 422, bad
    ok = client.post(
        "/api/v1/module/references",
        json={**base, "source": ref("library", ITEM), "target": ref("library", OTHER)},
        headers=headers,
    )
    assert ok.status_code == 200


# --- Enumeration and reconciliation ---------------------------------------------------------


def test_reconciliation_rebuilds_the_derived_index_idempotently(lab):
    client, runtime, module, db, _ = lab
    # The index lost track of reality: one stale edge, and the owner's real edge is missing.
    stale = owned_edge(str(uuid.uuid4()))
    assert (
        client.post("/api/v1/module/references", json=stale, headers=bearer(runtime)).status_code
        == 200
    )
    module.edges = [owned_edge(OTHER, readers=["archive"])] + [
        owned_edge(str(uuid.UUID(int=n))) for n in range(1, 450)
    ]
    result = client.post("/api/v1/modules/library/references/reconcile")
    assert result.status_code == 200, result.text
    assert result.json() == {
        "module": "library",
        "added": 450,
        "updated": 0,
        "removed": 1,
        "unchanged": 0,
    }
    wanted = sorted(
        (e["source"], e["target"], e["relation"], json.dumps(sorted(e["readers"])))
        for e in module.edges
    )
    assert edges(db) == wanted
    again = client.post("/api/v1/modules/library/references/reconcile").json()
    assert again == {"module": "library", "added": 0, "updated": 0, "removed": 0, "unchanged": 450}
    module.edges[0]["readers"] = []
    assert client.post("/api/v1/modules/library/references/reconcile").json()["updated"] == 1


@pytest.mark.parametrize(
    "failure",
    ["enumerate", "loop", "foreign", "non-uuid", "duplicate", "undeclared-type"],
)
def test_failed_enumeration_never_erases_valid_index_state(lab, failure):
    client, runtime, module, db, _ = lab
    valid = owned_edge(OTHER)
    client.post("/api/v1/module/references", json=valid, headers=bearer(runtime))
    before = edges(db)
    if failure in {"enumerate", "loop"}:
        module.fail.add(failure)
    elif failure == "foreign":
        module.edges = [{**valid, "source": ref("archive", ITEM)}]
    elif failure == "non-uuid":
        module.edges = [{**valid, "source": ref("library", "42")}]
    elif failure == "duplicate":
        module.edges = [valid, valid]
    else:
        module.edges = [{**valid, "source": ref("library", ITEM, "folder")}]
    response = client.post("/api/v1/modules/library/references/reconcile")
    assert response.status_code == 502
    assert "not changed" in response.json()["detail"]
    assert edges(db) == before


def test_other_creators_edges_and_non_enumerating_modules_are_untouched(lab):
    client, _, module, db, _ = lab
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO resource_references(id,source,target,relation,creator,metadata,readers,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                ref("archive", "a"),
                ref("library", ITEM),
                "archive.cites",
                "archive",
                "{}",
                "[]",
                "t",
                "t",
            ),
        )
    module.edges = []
    assert client.post("/api/v1/modules/library/references/reconcile").status_code == 200
    assert len(edges(db, "archive")) == 1


# --- Backup ---------------------------------------------------------------------------------


def test_backup_records_validated_metadata_and_shared_files(lab):
    client, runtime, _, _, path = lab
    blob = client.post(
        "/api/v1/module/blobs", json={"content": "aGVsbG8="}, headers=bearer(runtime)
    ).json()["id"]
    response = client.post("/api/v1/modules/library/backups")
    assert response.status_code == 201, response.text
    meta = response.json()
    assert meta["format"] == "empyrean-module-backup" and meta["version"] == 1
    assert (meta["module"], meta["module_version"], meta["module_format"]) == (
        "library",
        "1.0.0",
        "library-json",
    )
    assert meta["module_format_version"] == 1 and meta["restorable_by"] == ">=1.0.0,<2.0.0"
    assert meta["blobs"] == [{"sha256": blob, "size": 5}]
    stored = path / "backups/modules/library" / meta["id"]
    assert (stored / "artifact").exists() and (stored / "blobs" / blob).exists()
    listed = client.get("/api/v1/modules/library/backups").json()
    assert [b["id"] for b in listed] == [meta["id"]]
    assert "resolver" not in json.dumps(listed).lower()
    archive = client.get(f"/api/v1/modules/library/backups/{meta['id']}/download")
    assert archive.status_code == 200 and archive.headers["content-type"] == "application/x-tar"


def test_backup_with_wrong_identity_is_not_recorded(lab):
    client, _, module, _, path = lab
    module.fail.add("identity")
    response = client.post("/api/v1/modules/library/backups")
    assert response.status_code == 502
    assert client.get("/api/v1/modules/library/backups").json() == []
    assert not any((path / "backups/modules/library").iterdir())


# --- Restore --------------------------------------------------------------------------------


def backup(client):
    response = client.post("/api/v1/modules/library/backups")
    assert response.status_code == 201, response.text
    return response.json()["id"]


def restore(client, backup_id, confirm=True):
    return client.post(
        f"/api/v1/modules/library/backups/{backup_id}/restore", json={"confirm_replace": confirm}
    )


def test_restore_preserves_identity_suspends_purge_and_reconciles(lab):
    client, runtime, module, db, _ = lab
    old = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    module.items[OTHER] = {"title": "In trash for 45 days", "trashed_at": old}
    module.edges = [owned_edge(OTHER)]
    client.post("/api/v1/modules/library/references/reconcile")
    snapshot = backup(client)
    # Afterwards the module changes: data is deleted and different references exist.
    module.items, module.edges = {}, [owned_edge(str(uuid.uuid4()))]
    client.post("/api/v1/modules/library/references/reconcile")
    assert restore(client, snapshot, confirm=False).status_code == 422
    result = restore(client, snapshot)
    assert result.status_code == 200, result.text
    assert result.json()["state"] == "completed"
    # Same UUIDs; the item trashed 45 days ago was not purged because of its old timestamp.
    assert set(module.items) == {ITEM, OTHER}
    module.purge(datetime.now(timezone.utc))
    assert OTHER in module.items and module.suspended is False
    # The derived index follows the restored authoritative state, not the old index.
    assert [e[1] for e in edges(db)] == [ref("library", OTHER)]
    order = [
        c for c in module.calls if c.startswith("/empyrean/v1/backup/") or c.endswith("outgoing")
    ]
    assert order[-4:] == [
        "/empyrean/v1/backup/validate",
        "/empyrean/v1/backup/restore",
        "/empyrean/v1/references/outgoing",
        "/empyrean/v1/backup/finalize",
    ]
    with db.connect() as conn:
        assert conn.execute("SELECT state FROM modules").fetchone()[0] == "enabled"
    assert client.get("/api/v1/module/context", headers=bearer(runtime)).status_code == 200


def test_rejected_backup_changes_nothing(lab):
    client, runtime, module, db, _ = lab
    snapshot = backup(client)
    module.fail.add("validate")
    module.items = {"after": {"title": "current", "trashed_at": None}}
    response = restore(client, snapshot)
    assert response.status_code == 422 and "nothing was changed" in response.json()["detail"]
    assert set(module.items) == {"after"}
    assert "/empyrean/v1/backup/restore" not in module.calls
    job = client.get("/api/v1/modules/library/restores").json()[0]
    assert (job["state"], job["stage"]) == ("failed", "validate")
    assert client.get("/api/v1/module/context", headers=bearer(runtime)).status_code == 200


def test_failed_restore_is_visible_and_fails_closed(lab):
    client, runtime, module, db, _ = lab
    snapshot = backup(client)
    module.fail.add("restore")
    response = restore(client, snapshot)
    assert response.status_code == 502
    with db.connect() as conn:
        row = conn.execute("SELECT state,token,health FROM modules").fetchone()
        assert (row["state"], row["token"], row["health"]) == ("error", None, "restore_failed")
        assert conn.execute(
            "SELECT 1 FROM notifications WHERE message LIKE '%data state is unknown%'"
        ).fetchone()
    job = client.get("/api/v1/modules/library/restores").json()[0]
    assert (job["state"], job["stage"]) == ("failed", "restore")
    assert "/empyrean/v1/backup/finalize" not in module.calls


def test_reconciliation_failure_keeps_purge_suspended_until_finalized(lab):
    client, _, module, _, _ = lab
    old = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    module.items[OTHER] = {"title": "old trash", "trashed_at": old}
    snapshot = backup(client)
    module.fail.add("enumerate")
    response = restore(client, snapshot)
    assert response.status_code == 502
    job = client.get("/api/v1/modules/library/restores").json()[0]
    assert (job["state"], job["stage"]) == ("needs_attention", "reconcile")
    assert module.suspended is True and "/empyrean/v1/backup/finalize" not in module.calls
    module.purge(datetime.now(timezone.utc))
    assert OTHER in module.items
    module.fail.clear()
    retried = client.post(f"/api/v1/modules/library/restores/{job['id']}/finalize")
    assert retried.status_code == 200 and module.suspended is False
    assert client.post(f"/api/v1/modules/library/restores/{job['id']}/finalize").status_code == 409


def test_damaged_or_incompatible_backup_is_refused_before_contacting_module(lab):
    client, _, module, db, path = lab
    snapshot = backup(client)
    (path / "backups/modules/library" / snapshot / "artifact").write_bytes(b"tampered")
    calls = len(module.calls)
    assert restore(client, snapshot).status_code == 409
    snapshot = backup(client)
    with db.connect() as conn:
        meta = json.loads(
            conn.execute("SELECT metadata FROM module_backups WHERE id=?", (snapshot,)).fetchone()[
                0
            ]
        )
        meta["restorable_by"] = ">=2.0.0"
        conn.execute(
            "UPDATE module_backups SET metadata=? WHERE id=?", (json.dumps(meta), snapshot)
        )
    assert restore(client, snapshot).status_code == 409
    assert not any(c.endswith(("validate", "restore")) for c in module.calls[calls:])


def test_interrupted_restore_and_update_fail_closed_on_restart(lab):
    client, runtime, _, db, path = lab
    with db.connect() as conn:
        conn.execute("UPDATE modules SET state='restoring'")
        conn.execute(
            "INSERT INTO module_restores VALUES('r','library','b','running','restore','','t','t')"
        )
        conn.execute(
            "INSERT INTO module_updates VALUES('u','library','1','2','{}','{}','applying','health','','t','t')"
        )
    with TestClient(create_app(path, runtime, httpx.MockTransport(lambda r: httpx.Response(200)))):
        pass
    with db.connect() as conn:
        assert conn.execute("SELECT state,token FROM modules").fetchone()[:] == ("error", None)
        assert conn.execute("SELECT state FROM module_restores").fetchone()[0] == "failed"
        assert conn.execute("SELECT state FROM module_updates").fetchone()[0] == "failed"


# --- Update ---------------------------------------------------------------------------------


def next_version(**changes):
    manifest = persistent_manifest()
    manifest.update(version="1.1.0", container={"image": "sha256:" + "b" * 64, "port": 14333})
    manifest.update(changes)
    return manifest


def test_update_with_unchanged_capabilities_keeps_identity_and_data(lab):
    client, runtime, module, db, _ = lab
    old_token = runtime.tokens["library"]
    new = next_version()
    review = client.post("/api/v1/modules/library/update/review", json=new).json()
    assert review["from_version"] == "1.0.0" and review["to_version"] == "1.1.0"
    assert review["capabilities"] == {"added": [], "removed": []}
    assert review["persistent_data"] == "retained" and review["backup"] == "recommended"
    result = client.post(
        "/api/v1/modules/library/update", json={"manifest": new, "grants": new["capabilities"]}
    )
    assert result.status_code == 200, result.text
    assert result.json()["health"] == "healthy"
    # The same registration is replaced in place: never disable, uninstall or reinstall.
    assert [c[0] for c in runtime.calls] == ["enable", "enable"]
    assert runtime.manifests["library"]["version"] == "1.1.0"
    assert runtime.tokens["library"] != old_token
    assert ITEM in module.items
    with db.connect() as conn:
        assert conn.execute("SELECT 1 FROM retained_module_data WHERE id='library'").fetchone()
        row = conn.execute("SELECT state,manifest FROM modules").fetchone()
        assert row["state"] == "enabled" and json.loads(row["manifest"])["version"] == "1.1.0"
    history = client.get("/api/v1/modules/library/updates").json()[0]
    assert (history["from_version"], history["to_version"], history["state"]) == (
        "1.0.0",
        "1.1.0",
        "completed",
    )


def test_capability_escalation_requires_explicit_approval(lab):
    client, runtime, _, db, _ = lab
    new = next_version(
        capabilities=[*persistent_manifest()["capabilities"], "notifications.publish"]
    )
    review = client.post("/api/v1/modules/library/update/review", json=new).json()
    assert review["capabilities"]["added"] == ["notifications.publish"]
    assert review["requires_approval"] == ["notifications.publish"]
    denied = client.post(
        "/api/v1/modules/library/update",
        json={"manifest": new, "grants": persistent_manifest()["capabilities"]},
    )
    assert denied.status_code == 422 and "notifications.publish" in denied.json()["detail"]
    with db.connect() as conn:
        assert (
            json.loads(conn.execute("SELECT manifest FROM modules").fetchone()[0])["version"]
            == "1.0.0"
        )
    approved = client.post(
        "/api/v1/modules/library/update", json={"manifest": new, "grants": new["capabilities"]}
    )
    assert approved.status_code == 200
    assert (
        client.post(
            "/api/v1/module/notifications", json={"message": "hi"}, headers=bearer(runtime)
        ).status_code
        == 201
    )


def test_removed_capability_is_no_longer_usable(lab):
    client, runtime, _, _, _ = lab
    caps = [c for c in persistent_manifest()["capabilities"] if c != "blobs.write"]
    new = next_version(capabilities=caps)
    assert (
        client.post(
            "/api/v1/modules/library/update", json={"manifest": new, "grants": caps}
        ).status_code
        == 200
    )
    denied = client.post("/api/v1/module/blobs", json={"content": "aGk="}, headers=bearer(runtime))
    assert denied.status_code == 403


def test_failed_post_update_health_is_not_reported_as_success(lab):
    client, runtime, module, db, _ = lab
    module.fail.add("health")
    new = next_version()
    response = client.post(
        "/api/v1/modules/library/update", json={"manifest": new, "grants": new["capabilities"]}
    )
    assert response.status_code == 502
    with db.connect() as conn:
        row = conn.execute("SELECT state,token,health FROM modules").fetchone()
        assert (row["state"], row["token"], row["health"]) == ("error", None, "unhealthy")
        notice = conn.execute("SELECT message FROM notifications ORDER BY id DESC").fetchone()[0]
    assert "No automatic rollback" in notice and "v1.0.0" in notice
    history = client.get("/api/v1/modules/library/updates").json()[0]
    assert (history["state"], history["stage"]) == ("failed", "health")
    assert ITEM in module.items  # Nothing deleted module data.
    # Honest recovery: explicitly re-apply the previous version.
    module.fail.clear()
    previous = persistent_manifest()
    downgrade = client.post(
        "/api/v1/modules/library/update",
        json={"manifest": previous, "grants": previous["capabilities"]},
    )
    assert downgrade.status_code == 409 and "downgrade" in downgrade.json()["detail"]
    recovered = client.post(
        "/api/v1/modules/library/update",
        json={"manifest": previous, "grants": previous["capabilities"], "allow_downgrade": True},
    )
    assert recovered.status_code == 200 and recovered.json()["state"] == "enabled"


def test_update_that_cannot_start_is_error(lab):
    client, runtime, _, db, _ = lab
    runtime.fail = True
    new = next_version()
    assert (
        client.post(
            "/api/v1/modules/library/update", json={"manifest": new, "grants": new["capabilities"]}
        ).status_code
        == 502
    )
    with db.connect() as conn:
        assert conn.execute("SELECT state FROM modules").fetchone()[0] == "error"


def test_update_of_disabled_module_does_not_claim_health(lab):
    client, runtime, _, db, _ = lab
    client.post("/api/v1/modules/library/disable")
    new = next_version()
    result = client.post(
        "/api/v1/modules/library/update", json={"manifest": new, "grants": new["capabilities"]}
    ).json()
    assert result["state"] == "disabled" and result["health"] == "not_verified"
    assert runtime.calls[-1][0] == "disable"


def test_update_identity_compatibility_and_backup_policy(lab, monkeypatch):
    client, _, module, db, _ = lab
    other = next_version(id="other")
    assert client.post("/api/v1/modules/library/update/review", json=other).status_code == 422
    incompatible = next_version(nexus=">=0.2.0")
    assert (
        client.post("/api/v1/modules/library/update/review", json=incompatible).status_code == 422
    )
    new = next_version()
    monkeypatch.setenv("NEXUS_UPDATE_BACKUP", "require")
    body = {"manifest": new, "grants": new["capabilities"]}
    assert client.post("/api/v1/modules/library/update", json=body).status_code == 409
    module.fail.add("identity")  # The pre-update backup fails, so the update must not proceed.
    assert (
        client.post(
            "/api/v1/modules/library/update", json={**body, "backup_before": True}
        ).status_code
        == 502
    )
    with db.connect() as conn:
        assert (
            json.loads(conn.execute("SELECT manifest FROM modules").fetchone()[0])["version"]
            == "1.0.0"
        )
    module.fail.clear()
    assert (
        client.post(
            "/api/v1/modules/library/update", json={**body, "backup_before": True}
        ).status_code
        == 200
    )
    assert len(client.get("/api/v1/modules/library/backups").json()) == 1


# --- Development features -------------------------------------------------------------------


def test_reference_module_is_development_only(lab):
    client, _, _, _, _ = lab
    assert client.get("/api/v1/system").json()["development"] == {"reference_module": False}
    assert client.get("/api/v1/example-manifest").status_code == 404


def test_update_review_handles_semver_prerelease_versions(lab):
    client, _, _, _, _ = lab
    review = client.post(
        "/api/v1/modules/library/update/review", json=next_version(version="1.1.0-alpha.x")
    )
    assert review.status_code == 200 and review.json()["downgrade"] is False
    older = client.post(
        "/api/v1/modules/library/update/review", json=next_version(version="0.9.0-x7")
    )
    assert older.json()["downgrade"] is True
