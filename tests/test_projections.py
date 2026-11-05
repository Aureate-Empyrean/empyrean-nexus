import copy
import json

import httpx
import pytest
from broker.app import INSTALLATION, Operation, operate
from conftest import install
from docker.errors import NotFound
from fastapi.testclient import TestClient
from nexus.app import create_app
from nexus.protocol import validate_manifest


def module(manifest, module_id, port, provides=(), read=()):
    result = copy.deepcopy(manifest)
    result.update(id=module_id, nexus=">=0.1.5,<0.2.0")
    result["container"]["port"] = port
    result["events"] = {"produces": [], "consumes": []}
    result["capabilities"] = ["projections.read"] if read else []
    result["projections"] = {
        "version": 1,
        "provides": list(provides),
        "read": [{"module": m, "projection": p} for m, p in read],
    }
    result.pop("resources", None)
    result.pop("references", None)
    result.pop("backup", None)
    return result


@pytest.fixture
def projections(owner, manifest):
    client = owner[0]
    install(client, module(manifest, "provider", 13333, provides=["dated-items"]))
    install(client, module(manifest, "reader", 14333, read=[("provider", "dated-items")]))
    install(client, module(manifest, "stranger", 15333, read=[("other", "dated-items")]))
    for name in ("provider", "reader", "stranger"):
        assert client.post(f"/api/v1/modules/{name}/enable").status_code == 200
    return owner


def token(env, name):
    return {"Authorization": "Bearer " + env[1].tokens[name]}


def query(client, env, who="reader", **changes):
    body = {"module": "provider", "projection": "dated-items", "query": {"from": "2026-11-01"}}
    body.update(changes)
    return client.post("/api/v1/module/projections/query", headers=token(env, who), json=body)


def test_forwarding_contract(projections):
    _, runtime, db, path, _ = projections
    seen = []

    def provider(request):
        seen.append(request)
        return httpx.Response(200, json={"items": [{"id": "a", "title": "x"}], "next_cursor": "2"})

    with TestClient(create_app(path, runtime, httpx.MockTransport(provider))) as c:
        response = query(c, projections, cursor="1")
    assert response.status_code == 200
    assert response.json() == {
        "module": "provider",
        "projection": "dated-items",
        "availability": "available",
        "items": [{"id": "a", "title": "x"}],
        "next_cursor": "2",
    }
    with db.connect() as conn:
        key = conn.execute("SELECT resolver_key FROM modules WHERE id='provider'").fetchone()[0]
    request = seen[0]
    assert request.url.path == "/empyrean/v1/projections/dated-items"
    assert request.headers["x-nexus-resolver-key"] == key
    assert "authorization" not in request.headers and "cookie" not in request.headers
    assert json.loads(request.content) == {
        "requester": "reader",
        "query": {"from": "2026-11-01"},
        "cursor": "1",
    }
    # Nexus keeps nothing: no table records projected items.
    with db.connect() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not any("projection" in t for t in tables)


def test_scope_and_capability_are_required(projections):
    client = projections[0]
    assert query(client, projections, who="stranger").status_code == 403
    assert query(client, projections, who="provider").status_code == 403
    assert query(client, projections, projection="other-items").status_code == 403
    assert query(client, projections, query={"x": "y" * 5000}).status_code == 422


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (403, {}, "forbidden"),
        (404, {}, "temporarily_unavailable"),
        (500, {}, "temporarily_unavailable"),
        (200, {"items": "not-a-list"}, "temporarily_unavailable"),
        (200, {"items": [{"id": str(i)} for i in range(501)]}, "temporarily_unavailable"),
        (200, {"items": [{"x": "y" * 1100000}]}, "temporarily_unavailable"),
    ],
)
def test_provider_failures_are_unavailable(projections, status, body, expected):
    _, runtime, _, path, _ = projections
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json=body))
    with TestClient(create_app(path, runtime, transport)) as c:
        assert query(c, projections).json()["availability"] == expected


def test_lifecycle_availability(projections, manifest):
    client = projections[0]
    assert client.post("/api/v1/modules/provider/disable").status_code == 200
    assert query(client, projections).json()["availability"] == "module_disabled"
    assert client.delete("/api/v1/modules/provider").status_code == 200
    assert query(client, projections).json()["availability"] == "module_uninstalled"
    # A registered module that does not declare the projection is not asked.
    install(client, module(manifest, "provider", 13333))
    assert client.post("/api/v1/modules/provider/enable").status_code == 200
    assert query(client, projections).json()["availability"] == "not_provided"


def test_manifest_rules(manifest):
    reader = module(manifest, "reader", 14333, read=[("provider", "dated-items")])
    assert validate_manifest(copy.deepcopy(reader), True)
    older = copy.deepcopy(reader)
    older["nexus"] = ">=0.1.3,<0.2.0"
    with pytest.raises(ValueError, match="excluding 0.1.4"):
        validate_manifest(older, True)
    missing = copy.deepcopy(reader)
    missing["capabilities"] = []
    with pytest.raises(ValueError, match="projections.read"):
        validate_manifest(missing, True)
    undeclared = copy.deepcopy(reader)
    del undeclared["projections"]
    with pytest.raises(ValueError, match="projections declaration"):
        validate_manifest(undeclared, True)
    wildcard = copy.deepcopy(reader)
    wildcard["projections"]["read"] = [{"module": "*", "projection": "dated-items"}]
    with pytest.raises(ValueError):
        validate_manifest(wildcard, True)
    egress = module(manifest, "fetcher", 16333)
    del egress["projections"]
    egress["capabilities"] = ["network.egress"]
    assert validate_manifest(copy.deepcopy(egress), True)
    egress["nexus"] = ">=0.1.4,<0.2.0"
    with pytest.raises(ValueError, match="network.egress"):
        validate_manifest(egress, True)


def test_update_review_reports_projection_and_egress_changes(projections, manifest):
    client = projections[0]
    new = module(manifest, "reader", 14333, read=[("provider", "dated-items")])
    new["version"] = "9.0.0"
    new["capabilities"] = ["projections.read", "network.egress"]
    new["projections"]["provides"] = ["dated-items"]
    diff = client.post("/api/v1/modules/reader/update/review", json=new).json()
    assert diff["capabilities"]["added"] == ["network.egress"]
    assert diff["projections"]["provides"]["added"] == ["dated-items"]


@pytest.fixture
def engine(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    client = MagicMock()
    gateway = MagicMock()
    gateway.attrs = {"NetworkSettings": {"Networks": {}}}
    client.containers.list.return_value = [gateway]
    client.containers.get.side_effect = NotFound("missing")
    client.networks.get.side_effect = NotFound("missing")
    image = SimpleNamespace(id="sha256:resolved", attrs={"Config": {}})
    client.images.get.return_value = image
    monkeypatch.setattr("broker.app.docker.from_env", lambda **kw: client)
    monkeypatch.setenv("NEXUS_ALLOW_EXAMPLE", "1")
    return client


def test_broker_egress_network_only_when_granted(engine, manifest):
    from unittest.mock import MagicMock, call

    from broker.app import LABEL

    networks = {}

    def create(name, **options):
        networks[name] = MagicMock(options=options)
        networks[name].attrs = {"Labels": {LABEL: INSTALLATION}}
        return networks[name]

    engine.networks.create.side_effect = create
    plain = module(manifest, "plain", 16333)
    operate("enable", Operation(id="plain", manifest=plain, token="x" * 40))
    assert list(networks) == [f"{INSTALLATION}-net-plain"]

    fetcher = module(manifest, "fetcher", 17333)
    fetcher["capabilities"] = ["network.egress"]
    operate("enable", Operation(id="fetcher", manifest=fetcher, token="x" * 40))
    internal = networks[f"{INSTALLATION}-net-fetcher"]
    egress = networks[f"{INSTALLATION}-egress-fetcher"]
    assert internal.options["internal"] is True and egress.options["internal"] is False
    container = engine.containers.run.return_value
    assert egress.connect.call_args_list == [call(container)]
    gateway = engine.containers.list.return_value[0]
    assert internal.connect.call_args_list == [call(gateway, aliases=["nexus"])]

    def existing(name):
        if name not in networks:
            raise NotFound("missing")
        return networks[name]

    engine.networks.get.side_effect = existing
    operate("disable", Operation(id="fetcher"))
    egress.remove.assert_called_once()
    internal.remove.assert_called_once()
