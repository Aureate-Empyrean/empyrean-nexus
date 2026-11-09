"""Nexus 0.1.14: Full and Quick backups, content-addressed objects, the memory grant (ADR 0026, 0028)."""

import hashlib
import json
import tarfile
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from nexus.app import create_app
from nexus.protocol import validate_manifest

from test_lifecycle import RecordingRuntime, persistent_manifest


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Library:
    """A module with originals stored outside its artifact."""

    def __init__(self, runtime):
        self.runtime = runtime
        self.originals = {sha(b): b for b in (b"first photo", b"second photo", b"x" * 300_000)}
        self.database = {"photos": list(self.originals)}
        self.fetched = []
        self.received = []
        self.fail = set()

    def __call__(self, request):
        path = request.url.path
        if path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.headers.get("x-nexus-resolver-key") != self.runtime.keys.get("library"):
            return httpx.Response(403)
        if path == "/empyrean/v1/references/outgoing":
            return httpx.Response(200, json={"references": [], "next_cursor": None})
        if path == "/empyrean/v1/backup/export":
            mode = request.headers["x-empyrean-backup-mode"]
            headers = {
                "X-Empyrean-Backup-Module": "library", "X-Empyrean-Backup-Module-Version": "1.0.0",
                "X-Empyrean-Backup-Format": "library-set", "X-Empyrean-Backup-Format-Version": "1",
                "X-Empyrean-Backup-Created-At": datetime.now(timezone.utc).isoformat(),
                "X-Empyrean-Backup-Restorable-By": ">=1.0.0,<2.0.0",
                "X-Empyrean-Backup-Completeness": "quick" if "lie" in self.fail else mode,
            }  # fmt: skip
            if mode == "full":
                headers["X-Empyrean-Backup-Objects"] = "token-1"
            return httpx.Response(200, content=json.dumps(self.database).encode(), headers=headers)
        if path == "/empyrean/v1/backup/objects":
            assert request.url.params["export"] == "token-1"
            return httpx.Response(200, json={"objects": [{"sha256": k, "size": len(v)} for k, v in self.originals.items()]})
        if path.startswith("/empyrean/v1/backup/object/"):
            key = path.rsplit("/", 1)[1]
            if request.method == "GET":
                self.fetched.append(key)
                if "corrupt" in self.fail:
                    return httpx.Response(200, content=b"not what was promised")
                return httpx.Response(200, content=self.originals[key])
            self.originals[key] = request.read()
            self.received.append(key)
            return httpx.Response(200, json={"stored": True})
        if path == "/empyrean/v1/backup/objects/missing":
            wanted = [o["sha256"] for o in json.loads(request.read())["objects"]]
            return httpx.Response(200, json={"missing": [k for k in wanted if k not in self.originals]})
        if path == "/empyrean/v1/backup/validate":
            return httpx.Response(200, json={"valid": True})
        if path == "/empyrean/v1/backup/restore":
            self.database = json.loads(request.read())
            return httpx.Response(200, json={"restored": True})
        if path == "/empyrean/v1/backup/finalize":
            return httpx.Response(200, json={"finalized": True})
        return httpx.Response(404)


def manifest(**extra):
    m = persistent_manifest()
    m["nexus"] = ">=0.1.14,<0.2.0"
    m["backup"] = {"version": 1, "objects": True}
    m.update(extra)
    return m


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_PUBLIC_ORIGIN", "http://testserver")
    runtime = RecordingRuntime()
    module = Library(runtime)
    app = create_app(tmp_path, runtime, httpx.MockTransport(module))
    with TestClient(app) as client:
        setup = client.post("/api/v1/setup", json={
            "username": "owner", "password": "a unique long passphrase", "installation_name": "Lab",
            "claim_token": (tmp_path / "setup-token").read_text(),
        })  # fmt: skip
        client.headers["X-Nexus-CSRF"] = setup.json()["csrf"]
        m = manifest()
        assert client.post("/api/v1/modules", json={"manifest": m, "grants": m["capabilities"]}).status_code == 201
        assert client.post("/api/v1/modules/library/enable").status_code == 200
        yield client, module, tmp_path


def test_full_backup_stores_objects_once_and_quick_is_labelled_incomplete(lab):
    client, module, path = lab
    first = client.post("/api/v1/modules/library/backups")
    assert first.status_code == 201, first.text
    meta = first.json()
    assert meta["completeness"] == "full"
    assert (meta["objects"]["count"], meta["objects"]["transferred"]) == (3, 3)
    assert meta["objects"]["bytes"] == sum(len(v) for v in module.originals.values())
    # A second full backup transfers nothing that did not change.
    module.originals[sha(b"third photo")] = b"third photo"
    module.fetched.clear()
    second = client.post("/api/v1/modules/library/backups").json()
    assert (second["objects"]["count"], second["objects"]["transferred"]) == (4, 1)
    assert module.fetched == [sha(b"third photo")]
    quick = client.post("/api/v1/modules/library/backups", params={"mode": "quick"})
    assert quick.status_code == 201 and quick.json()["completeness"] == "quick" and not quick.json().get("objects")
    listed = {b["id"]: b["completeness"] for b in client.get("/api/v1/modules/library/backups").json()}
    assert sorted(listed.values()) == ["full", "full", "quick"]
    assert client.post("/api/v1/modules/library/backups", params={"mode": "other"}).status_code == 422
    download = client.get(f"/api/v1/modules/library/backups/{meta['id']}/download")
    archive = path / "bundle.tar"
    archive.write_bytes(download.content)
    with tarfile.open(archive) as tar:
        names = tar.getnames()
    assert "objects.json" in names and sum(n.startswith("objects/") for n in names) == 3


def test_a_backup_claiming_the_wrong_completeness_or_a_damaged_object_is_not_recorded(lab):
    client, module, _ = lab
    module.fail.add("lie")
    assert client.post("/api/v1/modules/library/backups").status_code == 502
    module.fail.clear()
    module.fail.add("corrupt")
    response = client.post("/api/v1/modules/library/backups")
    assert response.status_code == 502 and "digest" in response.text
    assert client.get("/api/v1/modules/library/backups").json() == []


def test_restore_returns_only_the_missing_objects(lab):
    client, module, path = lab
    meta = client.post("/api/v1/modules/library/backups").json()
    lost = sha(b"second photo")
    kept = module.originals.pop(lost)
    result = client.post(f"/api/v1/modules/library/backups/{meta['id']}/restore", json={"confirm_replace": True})
    assert result.status_code in (200, 201, 202), result.text
    assert module.received == [lost] and module.originals[lost] == kept
    stored = path / "backups/objects/library" / lost[:2] / lost
    stored.chmod(0o640)
    stored.write_bytes(b"bit rot")
    module.received.clear()
    again = client.post(f"/api/v1/modules/library/backups/{meta['id']}/restore", json={"confirm_replace": True})
    assert again.status_code == 409 and "damaged" in again.text and module.received == []


def test_manifest_extensions_require_this_nexus_and_a_bounded_memory_grant():
    good = manifest(runtime={"memory_mb": 768})
    assert validate_manifest(good, allow_example=True)["runtime"]["memory_mb"] == 768
    for bad in ({"memory_mb": 2048}, {"memory_mb": 100}, {"memory_mb": "768"}, {}):
        with pytest.raises(ValueError):
            validate_manifest(manifest(runtime=bad), allow_example=True)
    older = manifest()
    older["nexus"] = ">=0.1.8,<0.2.0"
    with pytest.raises(ValueError, match="0.1.13"):
        validate_manifest(older, allow_example=True)
    older = manifest(runtime={"memory_mb": 512})
    older["backup"] = {"version": 1}
    older["nexus"] = ">=0.1.8,<0.2.0"
    with pytest.raises(ValueError, match="memory grant"):
        validate_manifest(older, allow_example=True)
