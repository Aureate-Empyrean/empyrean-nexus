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


def maintenance(client, args):
    """Backup, restore and reconciliation run through the same owner APIs as the dashboard."""
    if args.backup:
        response = client.post(f"/api/v1/modules/{args.backup}/backups")
    elif args.restore:
        module_id, backup_id = args.restore
        response = client.post(
            f"/api/v1/modules/{module_id}/backups/{backup_id}/restore",
            json={"confirm_replace": args.confirm_replace},
        )
    else:
        response = client.post(f"/api/v1/modules/{args.reconcile}/references/reconcile")
    print(json.dumps(response.json()))
    response.raise_for_status()


def update(client, manifest, args):
    review = client.post(f"/api/v1/modules/{manifest['id']}/update/review", json=manifest)
    print(json.dumps(review.json()))
    review.raise_for_status()
    if not args.approve:
        raise RuntimeError(
            "Review the update above. Re-run with --approve to grant exactly its capabilities."
        )
    result = client.post(
        f"/api/v1/modules/{manifest['id']}/update",
        json={
            "manifest": manifest,
            "grants": manifest["capabilities"],
            "backup_before": args.backup_first,
            "allow_downgrade": args.allow_downgrade,
        },
    )
    print(json.dumps(result.json()))
    result.raise_for_status()


def main():
    parser = argparse.ArgumentParser(
        description="Install or update a reviewed manifest as the local Docker administrator"
    )
    parser.add_argument("manifest", type=Path, nargs="?")
    parser.add_argument(
        "--reuse-data",
        action="store_true",
        help="Explicitly reuse retained references and the same persistent dataset",
    )
    parser.add_argument("--update", action="store_true", help="Update an installed module in place")
    parser.add_argument(
        "--approve", action="store_true", help="Grant exactly the reviewed update capabilities"
    )
    parser.add_argument(
        "--backup-first", action="store_true", help="Back up module data before updating"
    )
    parser.add_argument("--allow-downgrade", action="store_true")
    parser.add_argument("--backup", metavar="MODULE", help="Create a module backup")
    parser.add_argument("--restore", nargs=2, metavar=("MODULE", "BACKUP_ID"))
    parser.add_argument(
        "--confirm-replace",
        action="store_true",
        help="Confirm that restore replaces the module's current data",
    )
    parser.add_argument("--reconcile", metavar="MODULE", help="Rebuild outgoing references")
    args = parser.parse_args()
    if args.backup or args.restore or args.reconcile:
        with owner_client() as client:
            return maintenance(client, args)
    if not args.manifest:
        parser.error("a manifest is required unless --backup, --restore or --reconcile is used")
    manifest = json.loads(args.manifest.read_text())
    with owner_client() as client:
        if args.update:
            return update(client, manifest, args)
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
                    "A different manifest is installed; use --update to review and apply it in place"
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
