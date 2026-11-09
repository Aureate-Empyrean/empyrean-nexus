"""Navigation is on by default; `NEXUS_NAVIGATION_HISTORY=0` switches it off."""


def test_navigation_is_on_by_default_and_owner_authenticated(owner, monkeypatch):
    client, *_ = owner
    monkeypatch.delenv("NEXUS_NAVIGATION_HISTORY", raising=False)
    assert client.get("/api/v1/system").json()["navigation"] == {"versions": [1]}
    monkeypatch.setenv("NEXUS_NAVIGATION_HISTORY", "0")
    assert client.get("/api/v1/system").json()["navigation"] == {"versions": []}
    monkeypatch.setenv("NEXUS_NAVIGATION_HISTORY", "1")
    assert client.get("/api/v1/system").json()["navigation"] == {"versions": [1]}
    client.cookies.clear()
    assert client.get("/api/v1/system").status_code == 401
