import base64

import pytest
from conftest import install
from nexus.protocol import validate_manifest


def application(manifest):
    manifest["nexus"] = ">=0.1.2,<0.2.0"
    manifest["capabilities"] += ["storage.data", "blobs.read", "blobs.write", "ui.application"]
    return manifest


def test_extensions_versioned(manifest):
    m = application(manifest)
    assert validate_manifest(m, True)
    m["nexus"] = ">=0.1.1,<0.2.0"
    with pytest.raises(ValueError, match="0.1.2"):
        validate_manifest(m, True)


def test_blobs_gateway_and_revocation(owner, manifest):
    c, runtime, db, path, requests = owner
    m = application(manifest)
    install(c, m)
    assert c.post("/api/v1/modules/" + m["id"] + "/enable").status_code == 200
    h = {"Authorization": "Bearer " + runtime.tokens[m["id"]]}
    body = {"content": base64.b64encode(b"private file").decode()}
    response = c.post("/api/v1/module/blobs", headers=h, json=body)
    assert response.status_code == 201
    key = response.json()["id"]
    assert c.post("/api/v1/module/blobs", headers=h, json=body).json()["id"] == key
    assert c.get("/api/v1/module/blobs/" + key, headers=h).json()["content"] == body["content"]
    assert c.get("/api/v1/module/blobs/" + key).status_code == 401
    c.get("/modules/" + m["id"] + "/api/info")
    assert requests[-1].headers["x-nexus-gateway-key"]
    assert "cookie" not in requests[-1].headers
    assert c.post("/api/v1/modules/" + m["id"] + "/disable").status_code == 200
    assert c.get("/api/v1/module/blobs/" + key, headers=h).status_code == 401


def test_blob_capability_denied(owner, manifest):
    c, runtime, *_ = owner
    install(c, manifest)
    c.post("/api/v1/modules/" + manifest["id"] + "/enable")
    h = {"Authorization": "Bearer " + runtime.tokens[manifest["id"]]}
    assert c.post("/api/v1/module/blobs", headers=h, json={"content": ""}).status_code == 403


def test_local_image_identity(manifest):
    manifest["container"]["image"] = "sha256:" + "a" * 64
    assert validate_manifest(manifest)


def test_retained_data_requires_explicit_reuse(owner, manifest):
    c, *_ = owner
    m = application(manifest)
    install(c, m)
    assert c.delete("/api/v1/modules/" + m["id"]).status_code == 200
    assert c.post("/api/v1/modules/validate", json=m).json()["retained_data"]
    body = {"manifest": m, "grants": m["capabilities"]}
    assert c.post("/api/v1/modules", json=body).status_code == 409
    assert (
        c.post("/api/v1/modules", json={**body, "reuse_reference_identity": True}).status_code
        == 201
    )


def test_locale_preserved(owner):
    c, *_ = owner
    assert (
        c.patch(
            "/api/v1/settings", json={"installation_name": "Home", "locale": "sk-SK"}
        ).status_code
        == 200
    )
    assert c.get("/api/v1/system").json()["locale"] == "sk-SK"
    c.patch("/api/v1/settings", json={"installation_name": "Renamed"})
    assert c.get("/api/v1/system").json()["locale"] == "sk-SK"
