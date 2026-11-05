"""System capacity reporting uses the cross-platform filesystem API."""

from types import SimpleNamespace


def test_capacity_uses_disk_usage_free(owner, monkeypatch):
    client, _, _, path, _ = owner
    paths = []

    def usage(target):
        paths.append(target)
        return SimpleNamespace(total=1000, used=700, free=300)

    monkeypatch.setattr("nexus.app.shutil.disk_usage", usage)
    response = client.get("/api/v1/system")
    assert response.status_code == 200
    assert response.json()["data_free_bytes"] == 300
    assert paths == [path]
