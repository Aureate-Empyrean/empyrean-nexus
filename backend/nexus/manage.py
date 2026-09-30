"""Local Docker-administrator CLI. Credentials never leave this process."""

import argparse
import hashlib
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

import httpx


@contextmanager
def owner_client():
    """An administrator with direct database access can issue a short-lived session."""
    db = sqlite3.connect(Path(os.getenv("NEXUS_DATA", "/data")) / "nexus.sqlite3")
    owners = db.execute("SELECT id FROM users").fetchall()
    if len(owners) != 1:
        raise RuntimeError("CLI requires exactly one configured installation owner")
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    hashed = hashlib.sha256(token.encode()).hexdigest()
    db.execute(
        "INSERT INTO sessions VALUES(?,?,?,?)", (hashed, owners[0][0], csrf, int(time.time()) + 300)
    )
    db.commit()
    try:
        with httpx.Client(
            base_url="http://127.0.0.1:12333",
            cookies={"nexus_session": token},
            headers={"X-Nexus-CSRF": csrf},
            timeout=120,
            trust_env=False,
        ) as client:
            yield client
    finally:
        db.execute("DELETE FROM sessions WHERE token=?", (hashed,))
        db.commit()
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Install a reviewed manifest as the local Docker administrator"
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--reuse-data",
        action="store_true",
        help="Explicitly reuse retained references and the same persistent dataset",
    )
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    with owner_client() as client:
        review = client.post("/api/v1/modules/validate", json=manifest)
        review.raise_for_status()
        existing = client.get("/api/v1/modules/" + manifest["id"])
        if existing.status_code == 404:
            result = client.post(
                "/api/v1/modules",
                json={
                    "manifest": manifest,
                    "grants": manifest["capabilities"],
                    "reuse_reference_identity": args.reuse_data,
                },
            )
            result.raise_for_status()
        else:
            existing.raise_for_status()
            if existing.json()["manifest"] != manifest:
                raise RuntimeError(
                    "A different manifest is installed; review and explicitly uninstall before replacing it"
                )
        enabled = client.post("/api/v1/modules/" + manifest["id"] + "/enable")
        enabled.raise_for_status()
        for attempt in range(10):
            health = client.post("/api/v1/modules/" + manifest["id"] + "/health")
            health.raise_for_status()
            if health.json()["status"] == "healthy":
                break
            time.sleep(1)
        print(
            json.dumps(
                {
                    "module": manifest["id"],
                    "health": health.json(),
                    "capabilities": manifest["capabilities"],
                }
            )
        )
        if health.json()["status"] != "healthy":
            raise RuntimeError("Module did not become healthy")


if __name__ == "__main__":
    main()
