"""Exercise a separate disposable Compose installation through public HTTP contracts.

Requires already-built Nexus and reference images, httpx, and Docker access.
Only this script's uniquely named Compose volumes/containers are removed.
"""

import json
import os
import secrets
import subprocess
import time
import uuid
from pathlib import Path

import httpx


def main():
    installation = "nexus-test-" + uuid.uuid4().hex[:10]
    port = os.getenv("NEXUS_TEST_PORT", "12334")
    origin = "http://127.0.0.1:" + port
    env = {
        **os.environ,
        "NEXUS_INSTALLATION": installation,
        "NEXUS_BIND": "127.0.0.1",
        "NEXUS_ALLOWED_ORIGINS": "",
        "NEXUS_PORT": port,
        "NEXUS_PUBLIC_ORIGIN": origin,
        "NEXUS_ALLOW_EXAMPLE": "1",
    }
    compose = ["docker", "compose", "-p", installation]

    def run(*args, capture=False):
        return subprocess.run(
            [*compose, *args], env=env, check=True, text=True, capture_output=capture
        )

    def check(response, status=200):
        assert response.status_code == status, (
            f"{response.request.url}: {response.status_code} {response.text}"
        )
        return response.json()

    module_id = "empyrean-example"
    client = httpx.Client(base_url=origin, timeout=130, trust_env=False)
    installed = False
    peer_installed = False
    try:
        run("up", "-d", "--wait")
        claim = run("exec", "-T", "nexus", "cat", "/data/setup-token", capture=True).stdout.strip()
        password = secrets.token_urlsafe(24)
        result = check(
            client.post(
                "/api/v1/setup",
                json={
                    "username": "smoke-owner",
                    "password": password,
                    "installation_name": "Disposable contract test",
                    "claim_token": claim,
                },
            ),
            201,
        )
        client.headers["X-Nexus-CSRF"] = result["csrf"]
        check(client.post("/api/v1/auth/logout"))
        result = check(
            client.post(
                "/api/v1/auth/login", json={"username": "smoke-owner", "password": password}
            )
        )
        client.headers["X-Nexus-CSRF"] = result["csrf"]
        manifest = json.loads(Path("examples/example-module/manifest.json").read_text())
        peer_id = "empyrean-example-peer"
        peer_manifest = json.loads(json.dumps(manifest))
        peer_manifest["id"] = peer_id
        peer_manifest["container"]["port"] = 14333
        peer_manifest["events"] = {"produces": [peer_id + ".ping"], "consumes": []}
        manifest["references"]["read"] = [{"module": peer_id, "type": "item"}]
        manifest["references"]["resolve"] = [{"module": peer_id, "type": "item"}]
        check(client.post("/api/v1/modules/validate", json=manifest))
        check(
            client.post(
                "/api/v1/modules", json={"manifest": manifest, "grants": manifest["capabilities"]}
            ),
            201,
        )
        installed = True
        check(client.post(f"/api/v1/modules/{module_id}/enable"))
        for _ in range(20):
            health = check(client.post(f"/api/v1/modules/{module_id}/health"))
            if health["status"] == "healthy":
                break
            time.sleep(0.5)
        assert health["status"] == "healthy", health
        page = client.get(f"/modules/{module_id}/")
        assert page.status_code == 200 and "sandbox" in page.headers["content-security-policy"]
        info = check(client.get(f"/modules/{module_id}/api/info"))
        assert info["nexus"]["id"] == module_id
        event = check(client.post(f"/modules/{module_id}/api/publish", json={}), 201)
        consumed = check(client.get(f"/modules/{module_id}/api/consume"))
        assert consumed["events"][0]["event"]["id"] == event["event"]["id"]
        assert check(client.get("/api/v1/notifications"))[0]["source"] == module_id
        check(
            client.post(
                "/api/v1/modules",
                json={"manifest": peer_manifest, "grants": peer_manifest["capabilities"]},
            ),
            201,
        )
        peer_installed = True
        check(client.post(f"/api/v1/modules/{peer_id}/enable"))
        for _ in range(20):
            if check(client.post(f"/api/v1/modules/{peer_id}/health"))["status"] == "healthy":
                break
            time.sleep(0.5)
        target = f"nexus:v1:{peer_id}:item:sample"
        private = check(client.post(f"/modules/{module_id}/api/reference", json={"target": target}))
        assert private["created"]
        assert check(client.get(f"/modules/{peer_id}/api/backlinks"))["references"] == []
        shared = check(
            client.post(
                f"/modules/{module_id}/api/reference", json={"target": target, "readers": [peer_id]}
            )
        )
        assert not shared["created"]
        assert len(check(client.get(f"/modules/{peer_id}/api/backlinks"))["references"]) == 1
        resolved = check(
            client.post(f"/modules/{module_id}/api/resolve", json={"resource": target})
        )
        assert resolved["availability"] == "available" and resolved["label"] == "Example item"
        # Browser/owner gateway cannot impersonate a Nexus-to-module resolver call.
        assert (
            client.post(
                f"/modules/{peer_id}/empyrean/v1/resources/resolve", json={"resource": target}
            ).status_code
            == 403
        )
        for path in ["overview", "modules", "settings", "activity", "modules/" + module_id]:
            assert client.get("/app/" + path).status_code == 200
        assert check(client.get("/api/v1/activity/entries"))["items"]
        # Recreate the gateway while preserving owner/session and module container.
        run("up", "-d", "--force-recreate", "--no-deps", "--wait", "nexus")
        assert check(client.get(f"/modules/{module_id}/api/info"))["nexus"]["id"] == module_id
        check(client.post(f"/api/v1/modules/{peer_id}/disable"))
        assert (
            check(client.post(f"/modules/{module_id}/api/resolve", json={"resource": target}))[
                "availability"
            ]
            == "module_disabled"
        )
        check(client.delete(f"/api/v1/modules/{peer_id}"))
        peer_installed = False
        assert (
            check(client.post(f"/modules/{module_id}/api/resolve", json={"resource": target}))[
                "availability"
            ]
            == "module_uninstalled"
        )
        assert len(check(client.get("/api/v1/export"))["references"]) == 1
        check(client.post(f"/api/v1/modules/{module_id}/disable"))
        assert client.get(f"/modules/{module_id}/").status_code == 409
        check(client.delete(f"/api/v1/modules/{module_id}"))
        installed = False
        assert check(client.get("/api/v1/modules")) == []
        assert check(client.get("/healthz"))["status"] == "ok"
        print(
            "PASS: setup, login, manifest, install, enable, health, gateway, API, event publish/consume, notification, private/shared cross-module backlinks, authenticated resolution, retained unresolved references, SPA routes, activity, gateway recreation, disable, uninstall, Nexus health"
        )
    except Exception:
        run("logs", "--tail", "80")
        raise
    finally:
        if peer_installed:
            try:
                client.delete("/api/v1/modules/empyrean-example-peer")
            except httpx.HTTPError:
                pass
        if installed:
            try:
                client.delete(f"/api/v1/modules/{module_id}")
            except httpx.HTTPError:
                pass
        client.close()
        run("down", "-v")


if __name__ == "__main__":
    main()
