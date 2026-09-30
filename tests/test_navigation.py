"""Per-module external-origin trust: canonical origins only, scoped, revocable."""

import pytest
from conftest import install
from nexus.navigation import canonical_origin


@pytest.mark.parametrize(
    "value",
    [
        "https://docs.example.org",
        "http://docs.example.org",
        "https://docs.example.org:8443",
        "http://127.0.0.1:12333",
        "https://[::1]:8443",
        "https://xn--exmple-4nf.org",
    ],
)
def test_canonical_origins_are_accepted(value):
    assert canonical_origin(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "https://docs.example.org/",  # a path, however short
        "https://docs.example.org/path",
        "https://docs.example.org?q=1",
        "https://docs.example.org#x",
        "https://user:pw@docs.example.org",
        "https://user@docs.example.org",
        "https://Docs.Example.org",  # not canonical
        "https://docs.example.org:443",  # default port must be omitted
        "http://docs.example.org:80",
        "https://exаmple.org",  # Unicode lookalike; browsers send punycode
        "javascript:alert(1)",
        "ftp://files.example.org",
        "mailto:a@example.org",
        "https://",
        "https://docs.example.org:99999",
    ],
)
def test_non_origins_and_deceptive_forms_are_rejected(value):
    with pytest.raises(ValueError):
        canonical_origin(value)


def application(manifest, module_id, port):
    manifest = {**manifest, "id": module_id, "container": {**manifest["container"], "port": port}}
    manifest["nexus"] = ">=0.1.2,<0.2.0"
    manifest["references"] = {"version": 1, "read": [], "resolve": []}
    manifest["capabilities"] = [*manifest["capabilities"], "ui.application"]
    manifest["events"] = {"produces": [module_id + ".ping"], "consumes": []}
    return manifest


def origins(client, module_id):
    return client.get("/api/v1/modules/" + module_id).json()["external_origins"]


def test_trust_is_scoped_revocable_and_removed_on_uninstall(owner, manifest):
    client, runtime, _, _, _ = owner
    first, second = (
        application(manifest, "first-app", 13333),
        application(manifest, "second-app", 14333),
    )
    install(client, first)
    install(client, second)
    body = {"origin": "https://docs.example.org"}
    assert client.post("/api/v1/modules/first-app/external-origins", json=body).status_code == 200
    assert origins(client, "first-app") == ["https://docs.example.org"]
    assert origins(client, "second-app") == []
    listed = {m["id"]: m["external_origins"] for m in client.get("/api/v1/modules").json()}
    assert listed == {"first-app": ["https://docs.example.org"], "second-app": []}
    bad = client.post(
        "/api/v1/modules/first-app/external-origins", json={"origin": "https://docs.example.org/x"}
    )
    assert bad.status_code == 422
    revoked = client.delete(
        "/api/v1/modules/first-app/external-origins", params={"origin": "https://docs.example.org"}
    )
    assert revoked.status_code == 200 and revoked.json()["external_origins"] == []
    assert (
        client.delete(
            "/api/v1/modules/first-app/external-origins",
            params={"origin": "https://docs.example.org"},
        ).status_code
        == 404
    )
    client.post("/api/v1/modules/second-app/external-origins", json=body)
    assert client.delete("/api/v1/modules/second-app").status_code == 200
    # A later module reusing the identity starts without inherited navigation trust.
    install(client, second)
    assert origins(client, "second-app") == []


def test_only_the_owner_can_grant_trust_and_only_to_application_modules(owner, manifest):
    client, runtime, _, _, _ = owner
    install(client, manifest)  # no ui.application
    body = {"origin": "https://docs.example.org"}
    assert (
        client.post("/api/v1/modules/empyrean-example/external-origins", json=body).status_code
        == 409
    )
    app = application(manifest, "an-app", 14333)
    install(client, app)
    client.post("/api/v1/modules/an-app/enable")
    module_headers = {"Authorization": "Bearer " + runtime.tokens["an-app"]}
    del client.headers["X-Nexus-CSRF"]
    assert client.post("/api/v1/modules/an-app/external-origins", json=body).status_code == 403
    client.cookies.clear()
    assert (
        client.post(
            "/api/v1/modules/an-app/external-origins", json=body, headers=module_headers
        ).status_code
        == 401
    )
