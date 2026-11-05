import copy
import json

import httpx
import pytest
from conftest import FakeRuntime, install
from fastapi.testclient import TestClient
from nexus.app import create_app
from nexus.icons import IconError, validate

ICON = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><defs><linearGradient id="t"><stop offset="0" stop-color="#7aa7eb"/></linearGradient></defs><rect width="48" height="48" fill="url(#t)"/><path d="M12 12h24v24z"/></svg>'
OTHER = ICON.replace(b"#7aa7eb", b"#c98be0")


class Modules:
    """Module containers as seen through Nexus's private transport."""

    def __init__(self):
        self.online = True
        self.icons = {"alpha": ICON, "beta": OTHER}
        self.content_type = "image/svg+xml"
        self.requests = []

    def handle(self, request):
        module_id = request.url.host.removeprefix("module-")
        self.requests.append((module_id, request.url.path))
        if not self.online:
            raise httpx.ConnectError("module is stopped")
        if request.url.path == "/icon.svg":
            return httpx.Response(
                200, content=self.icons[module_id], headers={"content-type": self.content_type}
            )
        return httpx.Response(200, json={"status": "ok"})


def nexus(tmp_path, modules, cookies=None):
    client = TestClient(create_app(tmp_path, FakeRuntime(), httpx.MockTransport(modules.handle)))
    if cookies:
        client.cookies.update(cookies)
    return client


def iconic(manifest, module_id, port, icon="/icon.svg"):
    result = copy.deepcopy(manifest)
    result.update(id=module_id, name=module_id.title(), nexus=">=0.1.8,<0.2.0")
    result["container"]["port"] = port
    result["events"] = {"produces": [], "consumes": []}
    result["capabilities"] = []
    for key in ("resources", "references", "backup"):
        result.pop(key, None)
    if icon:
        result["icon"] = icon
    return result


@pytest.fixture
def setup(tmp_path, monkeypatch, manifest):
    monkeypatch.setenv("NEXUS_ALLOW_EXAMPLE", "1")
    monkeypatch.setenv("NEXUS_PUBLIC_ORIGIN", "http://testserver")
    modules = Modules()
    with nexus(tmp_path, modules) as client:
        response = client.post(
            "/api/v1/setup",
            json={
                "username": "owner",
                "password": "a unique long passphrase",
                "installation_name": "Test Nexus",
                "claim_token": (tmp_path / "setup-token").read_text(),
            },
        )
        client.headers["X-Nexus-CSRF"] = response.json()["csrf"]
        for module_id, port in (("alpha", 13333), ("beta", 14333)):
            install(client, iconic(manifest, module_id, port))
            assert client.post(f"/api/v1/modules/{module_id}/enable").status_code == 200
        yield client, modules, tmp_path


def set_manifest(client, module_id, **changes):
    with client.app.state.db.connect() as conn:
        row = conn.execute("SELECT manifest FROM modules WHERE id=?", (module_id,)).fetchone()
        manifest = {**json.loads(row[0]), **changes}
        conn.execute("UPDATE modules SET manifest=? WHERE id=?", (json.dumps(manifest), module_id))


def icon_requests(modules):
    return [r for r in modules.requests if r[1] == "/icon.svg"]


def test_icon_is_fetched_validated_stored_and_served_inert(setup):
    client, modules, path = setup
    response = client.get("/api/v1/modules/alpha/icon")
    assert response.status_code == 200 and response.content == ICON
    assert response.headers["content-type"] == "image/svg+xml"
    assert "sandbox" in response.headers["content-security-policy"]
    assert "script-src" not in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-cache"
    assert (path / "module-icons" / "alpha.icon").read_bytes() == ICON
    assert icon_requests(modules) == [("alpha", "/icon.svg")]
    # Served from the copy: the module is not asked again, and revalidation is a 304.
    etag = response.headers["etag"]
    again = client.get("/api/v1/modules/alpha/icon", headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert len(icon_requests(modules)) == 1
    # Ordinary API responses keep the Nexus policy.
    assert "script-src 'self'" in client.get("/api/v1/modules").headers["content-security-policy"]


def test_outage_and_failed_refresh_keep_the_last_valid_icon(setup):
    client, modules, path = setup
    assert client.get("/api/v1/modules/alpha/icon").content == ICON
    modules.online = False
    assert client.get("/api/v1/modules/alpha/icon").content == ICON
    # The module is updated while unreachable: the refresh fails, the old copy stays.
    set_manifest(client, "alpha", version="9.9.9")
    assert client.get("/api/v1/modules/alpha/icon").content == ICON
    assert (path / "module-icons" / "alpha.icon").exists()
    # A failed refresh is not retried on every request.
    tries = len(icon_requests(modules))
    client.get("/api/v1/modules/alpha/icon")
    assert len(icon_requests(modules)) == tries
    # Status stays independent of the icon.
    assert client.post("/api/v1/modules/alpha/disable").status_code == 200
    assert client.get("/api/v1/modules/alpha/icon").content == ICON


def test_icon_survives_a_nexus_restart_while_the_module_is_offline(setup):
    client, modules, path = setup
    assert client.get("/api/v1/modules/alpha/icon").content == ICON
    modules.online = False
    modules.requests.clear()
    with nexus(path, modules, client.cookies) as restarted:
        response = restarted.get("/api/v1/modules/alpha/icon")
        assert response.status_code == 200 and response.content == ICON
    assert icon_requests(modules) == []


def test_changed_icon_replaces_the_cached_copy(setup):
    client, modules, _ = setup
    first = client.get("/api/v1/modules/alpha/icon")
    modules.icons["alpha"] = OTHER
    # Same version and image: the copy is current, nothing is fetched.
    assert client.get("/api/v1/modules/alpha/icon").content == ICON
    # An update (new version or image) refreshes it.
    set_manifest(client, "alpha", version="1.0.1")
    second = client.get("/api/v1/modules/alpha/icon")
    assert second.content == OTHER and second.headers["etag"] != first.headers["etag"]


def test_invalid_icon_is_rejected_and_never_stored(setup):
    client, modules, path = setup
    modules.icons["alpha"] = (
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    )
    assert client.get("/api/v1/modules/alpha/icon").status_code == 404
    assert not (path / "module-icons" / "alpha.icon").exists()
    # A valid copy is never replaced by an invalid one.
    modules.icons["beta"] = OTHER
    assert client.get("/api/v1/modules/beta/icon").content == OTHER
    modules.icons["beta"] = b"<html>not an icon</html>"
    modules.content_type = "text/html"
    set_manifest(client, "beta", version="2.0.0")
    assert client.get("/api/v1/modules/beta/icon").content == OTHER


@pytest.mark.parametrize(
    "content",
    [
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><foreignObject><p>x</p></foreignObject></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><style>@import url(https://x.test/a.css)</style></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:x="http://www.w3.org/1999/xlink"><use x:href="https://x.test/s.svg#a"/></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><use href="data:image/svg+xml,&lt;svg/&gt;"/></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><rect fill="url(https://x.test/p)"/></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><rect style="fill:url( https://x.test/p)"/></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><a href="javascript:alert(1)"><rect/></a></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><image href="https://x.test/p.png"/></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><set attributeName="href" to="javascript:x"/></svg>',
        b'<!DOCTYPE svg [<!ENTITY a "aaaa">]><svg xmlns="http://www.w3.org/2000/svg">&a;</svg>',
        b'<?xml-stylesheet href="https://x.test/a.css"?><svg xmlns="http://www.w3.org/2000/svg"/>',
        b"<svg><rect/></svg>",
        b"<svg xmlns='http://www.w3.org/2000/svg'><rect></svg>",
        b'<html xmlns="http://www.w3.org/1999/xhtml"/>',
        b"",
        b'<svg xmlns="http://www.w3.org/2000/svg">' + b"<g/>" * 20000 + b"</svg>",
    ],
)
def test_malicious_or_malformed_svg_is_rejected(content):
    with pytest.raises(IconError):
        validate(content, "image/svg+xml", "/icon.svg")


def test_formats_must_match_their_declared_type():
    assert validate(ICON, "image/svg+xml; charset=utf-8", "/icon.svg") == "image/svg+xml"
    assert validate(b"\x89PNG\r\n\x1a\n" + b"\0" * 16, "image/png", "/a/icon.png") == "image/png"
    assert validate(b"RIFF\0\0\0\0WEBPVP8 ", "image/webp", "/icon.webp") == "image/webp"
    for content, content_type, path in (
        (ICON, "text/html", "/icon.svg"),
        (ICON, "image/png", "/icon.svg"),
        (b"GIF89a", "image/png", "/icon.png"),
        (b"\x89PNG\r\n\x1a\n", "image/webp", "/icon.png"),
        (b"RIFF\0\0\0\0AVI ", "image/webp", "/icon.webp"),
    ):
        with pytest.raises(IconError):
            validate(content, content_type, path)


def test_no_icon_yet_or_none_declared_gives_the_letter_fallback(setup, manifest):
    client, modules, _ = setup
    install(client, iconic(manifest, "plain", 15333, icon=None))
    assert client.get("/api/v1/modules/plain/icon").status_code == 404
    # Declared, never fetched, and not running: nothing to show and no request is made.
    install(client, iconic(manifest, "gamma", 16333))
    modules.icons["gamma"] = ICON
    modules.requests.clear()
    assert client.get("/api/v1/modules/gamma/icon").status_code == 404
    assert icon_requests(modules) == []
    assert client.get("/api/v1/modules/missing/icon").status_code == 404


def test_uninstall_removes_the_cached_icon(setup):
    client, _, path = setup
    assert client.get("/api/v1/modules/alpha/icon").status_code == 200
    assert client.post("/api/v1/modules/alpha/disable").status_code == 200
    assert (path / "module-icons" / "alpha.icon").exists()
    assert client.delete("/api/v1/modules/alpha").status_code == 200
    assert not (path / "module-icons" / "alpha.icon").exists()
    assert not (path / "module-icons" / "alpha.json").exists()
    assert client.get("/api/v1/modules/alpha/icon").status_code == 404
    # The other module's copy is untouched.
    assert client.get("/api/v1/modules/beta/icon").content == OTHER


def test_icons_need_the_owner_session(setup):
    client, _, path = setup
    assert client.get("/api/v1/modules/alpha/icon").status_code == 200
    with nexus(path, Modules()) as anonymous:
        assert anonymous.get("/api/v1/modules/alpha/icon").status_code == 401
        module_token = {"Authorization": "Bearer not-an-owner-session"}
        assert anonymous.get("/api/v1/modules/alpha/icon", headers=module_token).status_code == 401


def test_each_module_gets_only_its_own_icon(setup):
    client, _, path = setup
    assert client.get("/api/v1/modules/alpha/icon").content == ICON
    assert client.get("/api/v1/modules/beta/icon").content == OTHER
    # A copy whose metadata names another module, or whose content was swapped, is not served.
    icons = path / "module-icons"
    (icons / "alpha.icon").write_bytes((icons / "beta.icon").read_bytes())
    cache = client.app.state.icons
    assert cache.load("alpha") is None
    meta = json.loads((icons / "beta.json").read_text())
    (icons / "beta.json").write_text(json.dumps({**meta, "module": "alpha"}))
    assert cache.load("beta") is None
    with pytest.raises(IconError):
        cache.load("../beta")
