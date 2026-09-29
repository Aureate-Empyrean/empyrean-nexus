import pytest
from fastapi.testclient import TestClient
from nexus.app import create_app


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:12333",
        "http://127.0.0.1:12333",
        "http://[::1]:12333",
        "http://192.168.100.32:12333",
    ],
)
def test_setup_from_configured_addresses(tmp_path, monkeypatch, origin):
    monkeypatch.setenv("NEXUS_PUBLIC_ORIGIN", "http://localhost:12333")
    monkeypatch.setenv("NEXUS_ALLOWED_ORIGINS", "http://192.168.100.32:12333")
    with TestClient(create_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/setup",
            headers={"Origin": origin},
            json={
                "username": "owner",
                "password": "long test passphrase",
                "installation_name": "Home",
                "claim_token": (tmp_path / "setup-token").read_text(),
            },
        )
        assert response.status_code == 201, response.text


@pytest.mark.parametrize(
    "origin",
    [
        "null",
        "http://evil.example",
        "http://192.168.100.33:12333",
        "http://127.0.0.1:9999",
        "http://localhost.evil.example:12333",
    ],
)
def test_unlisted_addresses_still_rejected(tmp_path, monkeypatch, origin):
    monkeypatch.setenv("NEXUS_PUBLIC_ORIGIN", "http://localhost:12333")
    monkeypatch.setenv("NEXUS_ALLOWED_ORIGINS", "http://192.168.100.32:12333")
    with TestClient(create_app(tmp_path)) as client:
        assert client.post("/api/v1/setup", headers={"Origin": origin}, json={}).status_code == 403


def test_reject_mixed_cookie_security_schemes(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_PUBLIC_ORIGIN", "https://nexus.example.org")
    monkeypatch.setenv("NEXUS_ALLOWED_ORIGINS", "http://192.168.100.32:12333")
    with pytest.raises(ValueError):
        create_app(tmp_path)
