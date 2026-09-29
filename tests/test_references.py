import copy
import json
import sqlite3

import httpx
import pytest
from conftest import install
from fastapi.testclient import TestClient
from nexus.app import create_app
from nexus.db import MIGRATIONS, Database
from nexus.protocol import validate_manifest
from nexus.references import parse_resource


def extended(manifest, module_id, port):
    result = copy.deepcopy(manifest)
    result.update(id=module_id, nexus=">=0.1.1,<0.2.0")
    result["container"]["port"] = port
    result["resources"] = [{"type": "item", "resolvable": True}]
    result["references"] = {"version": 1, "read": [], "resolve": []}
    result["events"] = {
        "produces": [],
        "consumes": [
            "nexus.reference.created",
            "nexus.reference.updated",
            "nexus.reference.deleted",
        ],
    }
    result["capabilities"] = [
        "references.create",
        "references.read",
        "references.resolve",
        "events.subscribe",
    ]
    return result


@pytest.fixture
def refs(owner, manifest):
    client, runtime, db, path, requests = owner
    for name, port in [("source", 13333), ("target", 14333), ("outsider", 15333)]:
        m = extended(manifest, name, port)
        if name == "source":
            m["references"]["read"] = [{"module": "target", "type": "item"}]
            m["references"]["resolve"] = [{"module": "target", "type": "item"}]
        install(client, m)
        assert client.post(f"/api/v1/modules/{name}/enable").status_code == 200
    return owner


def token(env, name):
    return {"Authorization": "Bearer " + env[1].tokens[name]}


def write(env, **changes):
    body = {
        "source": "nexus:v1:source:item:a",
        "target": "nexus:v1:target:item:b",
        "relation": "source.related",
        "metadata": {},
    }
    body.update(changes)
    return env[0].post("/api/v1/module/references", headers=token(env, "source"), json=body)


@pytest.mark.parametrize(
    "value", ["nexus:v1:source:item:a", "nexus:v1:community-example:opaque-type:A_42-~.x"]
)
def test_identity(value):
    assert parse_resource(value)["version"] == 1


@pytest.mark.parametrize(
    "value",
    [
        "source://item/a",
        "nexus:v2:source:item:a",
        "nexus:v1:source:item:../secret",
        "nexus:v1:source:item:%2F",
        "nexus:v1:source:item:a?b",
        "nexus:v1:source:item:a#b",
        "nexus:v1:Source:item:a",
        "nexus:v1:source:item:a\n",
        "nexus:v1:source:item:" + ("a" * 129),
    ],
)
def test_unsafe_identity(value):
    with pytest.raises(ValueError):
        parse_resource(value)


def test_private_backlinks_and_explicit_sharing(refs):
    c = refs[0]
    result = write(refs).json()
    assert result["created"]
    resource = "nexus:v1:target:item:b"
    before = c.get(
        "/api/v1/module/references",
        params={"resource": resource, "direction": "incoming"},
        headers=token(refs, "target"),
    ).json()
    assert before == {"references": [], "next_cursor": 0, "has_more": False}
    events = c.get("/api/v1/module/events", headers=token(refs, "target")).json()
    assert events["events"] == []  # Target ownership alone must not reveal the edge.
    shared = write(refs, readers=["target"]).json()
    assert shared["reference"]["id"] == result["reference"]["id"] and not shared["created"]
    backlinks = c.get(
        "/api/v1/module/references",
        params={"resource": resource, "direction": "incoming"},
        headers=token(refs, "target"),
    ).json()
    assert len(backlinks["references"]) == 1
    outgoing = c.get(
        "/api/v1/module/references",
        params={"resource": "nexus:v1:source:item:a"},
        headers=token(refs, "source"),
    ).json()
    assert len(outgoing["references"]) == 1
    assert len(c.get("/api/v1/module/events", headers=token(refs, "target")).json()["events"]) == 2
    write(refs, readers=[])
    assert c.get("/api/v1/module/events", headers=token(refs, "target")).json()["events"] == []
    assert (
        c.get(
            "/api/v1/module/references",
            params={"resource": resource, "direction": "incoming"},
            headers=token(refs, "target"),
        ).json()["references"]
        == []
    )


def test_spoofing_grants_and_delete(refs):
    c = refs[0]
    assert write(refs, source="nexus:v1:target:item:c").status_code == 403
    assert write(refs, relation="target.related").status_code == 403
    assert write(refs, metadata={"x": "x" * 3000}).status_code == 422
    assert write(refs, readers=["*"]).status_code == 422
    assert write(refs, target="nexus:v1:target:unknown:c").status_code == 422
    assert (
        c.get(
            "/api/v1/module/references",
            params={"resource": "nexus:v1:target:item:b"},
            headers=token(refs, "outsider"),
        ).status_code
        == 403
    )
    edge = write(refs, readers=["target"]).json()["reference"]
    assert (
        c.delete(
            "/api/v1/module/references/" + edge["id"], headers=token(refs, "target")
        ).status_code
        == 404
    )
    assert (
        c.delete(
            "/api/v1/module/references/" + edge["id"], headers=token(refs, "source")
        ).status_code
        == 200
    )
    assert c.get("/api/v1/module/events", headers=token(refs, "target")).json()["events"] == []


def test_retention_lifecycle_and_export(refs):
    c = refs[0]
    edge = write(refs).json()["reference"]
    assert c.post("/api/v1/modules/target/disable").status_code == 200
    response = c.post(
        "/api/v1/module/resources/resolve",
        headers=token(refs, "source"),
        json={"resource": edge["target"]},
    )
    assert response.json()["availability"] == "module_disabled"
    assert c.delete("/api/v1/modules/target").status_code == 200
    assert (
        c.post(
            "/api/v1/module/resources/resolve",
            headers=token(refs, "source"),
            json={"resource": edge["target"]},
        ).json()["availability"]
        == "module_uninstalled"
    )
    data = c.get("/api/v1/export").json()
    assert data["references"][0]["id"] == edge["id"]
    assert "resolver_key" not in json.dumps(data)
    assert (
        c.post(
            "/api/v1/module/resources/resolve",
            headers=token(refs, "outsider"),
            json={"resource": edge["target"]},
        ).status_code
        == 403
    )
    assert write(refs, metadata={"note": "still retained"}).status_code == 200


def test_resolution_owner_contract(refs):
    client, runtime, db, path, _ = refs
    seen = []

    def resolver(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "resource": "nexus:v1:target:item:b",
                "label": "Owner label",
                "open_path": "/items/b",
                "representation": {"summary": "minimal"},
            },
        )

    app = create_app(path, runtime, httpx.MockTransport(resolver))
    with TestClient(app) as c:
        response = c.post(
            "/api/v1/module/resources/resolve",
            headers=token(refs, "source"),
            json={"resource": "nexus:v1:target:item:b"},
        )
        assert response.json()["availability"] == "available"
        assert response.json()["open"] == {
            "route": "/app/modules/target",
            "module_path": "/items/b",
        }
    with db.connect() as conn:
        key = conn.execute("SELECT resolver_key FROM modules WHERE id='target'").fetchone()[0]
    assert seen[0].headers["x-nexus-resolver-key"] == key
    assert "cookie" not in seen[0].headers and "authorization" not in seen[0].headers
    assert json.loads(seen[0].content)["requester"] == "source"


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (404, {}, "not_found"),
        (410, {}, "deleted"),
        (403, {}, "forbidden"),
        (503, {}, "temporarily_unavailable"),
        (200, {"resource": "nexus:v1:target:item:wrong", "label": "no"}, "temporarily_unavailable"),
        (
            200,
            {"resource": "nexus:v1:target:item:b", "label": "no", "open_path": "//evil"},
            "temporarily_unavailable",
        ),
        (
            200,
            {
                "resource": "nexus:v1:target:item:b",
                "label": "no",
                "representation": {"x": "x" * 5000},
            },
            "temporarily_unavailable",
        ),
    ],
)
def test_resolver_failures(refs, status, body, expected):
    _, runtime, _, path, _ = refs
    with TestClient(
        create_app(
            path, runtime, httpx.MockTransport(lambda req: httpx.Response(status, json=body))
        )
    ) as c:
        assert (
            c.post(
                "/api/v1/module/resources/resolve",
                headers=token(refs, "source"),
                json={"resource": "nexus:v1:target:item:b"},
            ).json()["availability"]
            == expected
        )


def test_manifest_extension_compatibility(manifest):
    validate_manifest(manifest, True)
    m = extended(manifest, "community-test", 14333)
    validate_manifest(m, True)
    m["resources"].append({"type": "item", "resolvable": False})
    with pytest.raises(ValueError):
        validate_manifest(m, True)
    m = extended(manifest, "community-test", 14333)
    m["nexus"] = ">=0.1.0"
    with pytest.raises(ValueError):
        validate_manifest(m, True)


def test_existing_v1_database_migration(tmp_path):
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript(MIGRATIONS[0] + "PRAGMA user_version=1;")
        conn.execute("INSERT INTO settings VALUES('installation_name','Existing')")
    db = Database(path)
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        assert conn.execute("SELECT value FROM settings").fetchone()[0] == "Existing"
        assert conn.execute("SELECT COUNT(*) FROM resource_references").fetchone()[0] == 0


def test_reinstall_requires_explicit_identity_confirmation(refs, manifest):
    c = refs[0]
    write(refs)
    assert c.delete("/api/v1/modules/target").status_code == 200
    target = extended(manifest, "target", 14333)
    assert c.post("/api/v1/modules/validate", json=target).json()["retained_references"] == 1
    body = {"manifest": target, "grants": target["capabilities"]}
    assert c.post("/api/v1/modules", json=body).status_code == 409
    body["reuse_reference_identity"] = True
    assert c.post("/api/v1/modules", json=body).status_code == 201


def test_reference_features_need_each_capability(owner, manifest):
    c, runtime, _, _, _ = owner
    m = extended(manifest, "minimal", 13333)
    m["capabilities"] = []
    m["events"]["consumes"] = []
    install(c, m)
    c.post("/api/v1/modules/minimal/enable")
    headers = {"Authorization": "Bearer " + runtime.tokens["minimal"]}
    resource = "nexus:v1:minimal:item:a"
    assert (
        c.get(
            "/api/v1/module/references", params={"resource": resource}, headers=headers
        ).status_code
        == 403
    )
    assert (
        c.post(
            "/api/v1/module/resources/resolve", json={"resource": resource}, headers=headers
        ).status_code
        == 403
    )
    assert (
        c.post(
            "/api/v1/module/references",
            json={"source": resource, "target": resource, "relation": "minimal.related"},
            headers=headers,
        ).status_code
        == 403
    )


def test_legacy_manifests_remain_valid(manifest):
    legacy = copy.deepcopy(manifest)
    legacy.pop("resources")
    legacy.pop("references")
    legacy["capabilities"] = [c for c in legacy["capabilities"] if not c.startswith("references.")]
    legacy["nexus"] = ">=0.1.0,<0.2.0"
    validate_manifest(legacy, True)


def test_resource_schema_matches_security_boundaries():
    from pathlib import Path

    from jsonschema import Draft202012Validator

    schema = json.loads(Path("protocol/resource-v1.schema.json").read_text())
    validator = Draft202012Validator(schema)
    maximum = "nexus:v1:" + ("a" * 48) + ":" + ("b" * 48) + ":" + ("c" * 128)
    assert validator.is_valid(maximum)
    for value in [
        maximum + "x",
        "nexus:v1:source:item:a\n",
        "nexus:v1:" + ("a" * 49) + ":item:1",
        "nexus:v1:source:item:a/b",
    ]:
        assert not validator.is_valid(value)


def test_reinstall_checks_retained_reader_grants_too(refs, manifest):
    c = refs[0]
    write(refs, readers=["outsider"])
    c.delete("/api/v1/modules/outsider")
    m = extended(manifest, "outsider", 15333)
    assert c.post("/api/v1/modules/validate", json=m).json()["retained_references"] == 1
    assert (
        c.post("/api/v1/modules", json={"manifest": m, "grants": m["capabilities"]}).status_code
        == 409
    )


def test_platform_events_cannot_be_spoofed_by_legacy_registration(refs):
    c, runtime, db, _, _ = refs
    with db.connect() as conn:
        row = conn.execute("SELECT manifest FROM modules WHERE id='source'").fetchone()
        m = json.loads(row["manifest"])
        m["id"] = "nexus"
        m["capabilities"].append("events.publish")
        m["events"]["produces"] = ["nexus.reference.created"]
        conn.execute("UPDATE modules SET id='nexus',manifest=? WHERE id='source'", (json.dumps(m),))
    assert (
        c.post(
            "/api/v1/module/events",
            headers={"Authorization": "Bearer " + runtime.tokens["source"]},
            json={"type": "nexus.reference.created", "payload": {}},
        ).status_code
        == 403
    )
    with pytest.raises(ValueError):
        validate_manifest(m, True)
