"""Navigation feature discovery keeps owner authentication and opt-in rollout."""


def test_navigation_is_opt_in_and_owner_authenticated(owner, monkeypatch):
    client, *_ = owner
    monkeypatch.delenv("NEXUS_NAVIGATION_HISTORY", raising=False)
    assert client.get("/api/v1/system").json()["navigation"] == {"versions": []}
    monkeypatch.setenv("NEXUS_NAVIGATION_HISTORY", "1")
    assert client.get("/api/v1/system").json()["navigation"] == {"versions": [1]}
    client.cookies.clear()
    assert client.get("/api/v1/system").status_code == 401
