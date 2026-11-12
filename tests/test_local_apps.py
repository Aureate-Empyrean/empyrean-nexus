import json

import httpx
import pytest
from conftest import FakeRuntime
from fastapi.testclient import TestClient
from nexus.app import create_app
from nexus.local_apps import LocalAppError, load_local_apps

ICON = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><title>Zeus</title><defs><linearGradient id="b"><stop offset="0" stop-color="#f6dc96"/></linearGradient></defs><rect width="256" height="256" fill="#151b2c"/><path d="M146 34 L82 140 H124 L104 222 L176 108 H132 L158 34 Z" fill="url(#b)"/></svg>'
ZEUS = {
    "id": "zeus-local",
    "name": "Zeus",
    "description": "Private development control panel",
    "url": "http://127.0.0.1:65333/",
    "icon": "zeus.svg",
}


def write(directory, entries, icon=ICON):
    (directory / "zeus.svg").write_bytes(icon)
    path = directory / "apps.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def nexus(tmp_path, monkeypatch, entries=None):
    data = tmp_path / "data"
    if entries is not None:
        monkeypatch.setenv("NEXUS_LOCAL_APPS", str(write(tmp_path, entries)))
    else:
        monkeypatch.delenv("NEXUS_LOCAL_APPS", raising=False)
    monkeypatch.setenv("NEXUS_PUBLIC_ORIGIN", "http://testserver")
    client = TestClient(create_app(data, FakeRuntime(), httpx.MockTransport(lambda r: None)))
    return client, data


def sign_in(client, data):
    response = client.post(
        "/api/v1/setup",
        json={
            "username": "owner",
            "password": "a unique long passphrase",
            "installation_name": "Local Nexus",
            "claim_token": (data / "setup-token").read_text(),
        },
    )
    assert response.status_code == 201
    client.headers["X-Nexus-CSRF"] = response.json()["csrf"]


def test_local_apps_are_off_unless_configured(tmp_path, monkeypatch):
    client, data = nexus(tmp_path, monkeypatch)
    with client:
        sign_in(client, data)
        assert client.get("/api/v1/local-apps").json() == {"apps": []}
        assert client.get("/api/v1/local-apps/zeus-local/icon").status_code == 404


def test_configured_app_is_listed_with_its_validated_icon_for_the_owner_only(tmp_path, monkeypatch):
    client, data = nexus(tmp_path, monkeypatch, [ZEUS])
    with client:
        assert client.get("/api/v1/local-apps").status_code == 401
        assert client.get("/api/v1/local-apps/zeus-local/icon").status_code == 401
        sign_in(client, data)
        apps = client.get("/api/v1/local-apps").json()["apps"]
        assert [(a["id"], a["name"], a["url"], a["label"]) for a in apps] == [
            ("zeus-local", "Zeus", "http://127.0.0.1:65333/", "127.0.0.1:65333")
        ]
        icon = client.get("/api/v1/local-apps/zeus-local/icon")
        assert icon.status_code == 200 and icon.content == ICON
        assert icon.headers["content-type"] == "image/svg+xml"
        assert "sandbox" in icon.headers["content-security-policy"]
        cached = client.get(
            "/api/v1/local-apps/zeus-local/icon", headers={"if-none-match": icon.headers["etag"]}
        )
        assert cached.status_code == 304


@pytest.mark.parametrize(
    "change",
    [
        {"url": "http://192.168.1.10:65333/"},
        {"url": "https://zeus.example.com/"},
        {"url": "http://127.0.0.1/"},
        {"url": "http://user:pw@127.0.0.1:65333/"},
        {"url": "javascript:alert(1)"},
        {"id": "Zeus Local"},
        {"icon": "../zeus.svg"},
        {"name": ""},
        {"extra": "field"},
    ],
)
def test_invalid_entries_stop_nexus_instead_of_being_ignored(tmp_path, change):
    with pytest.raises(LocalAppError):
        load_local_apps(str(write(tmp_path, [{**ZEUS, **change}])))


def test_active_svg_icons_are_refused(tmp_path):
    active = ICON.replace(b"<title>", b'<script>alert(1)</script><title>')
    with pytest.raises(LocalAppError):
        load_local_apps(str(write(tmp_path, [ZEUS], icon=active)))
