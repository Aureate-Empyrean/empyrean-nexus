"""In-place module updates: same identity and data, explicit capability approval, no fake rollback."""

import hashlib
import json
import os
import secrets
import time
import uuid

from fastapi import Depends, HTTPException
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, ConfigDict, Field

sleep = time.sleep  # Replaceable in tests; health verification waits between attempts.


class UpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest: dict
    grants: list[str] = Field(max_length=10)
    backup_before: bool = False
    allow_downgrade: bool = False


def _set_diff(old, new):
    return {"added": sorted(set(new) - set(old)), "removed": sorted(set(old) - set(new))}


def _scopes(manifest, name):
    refs = manifest.get("references") or {}
    return [f"{s['module']}:{s['type']}" for s in refs.get(name, [])]


def backup_policy(old):
    """Where a backup belongs in the update lifecycle. Requirement strength is configurable."""
    if "storage.data" not in old["capabilities"]:
        return "not_applicable"
    return "recommended" if "backup" in old else "unavailable"


def _order(version):
    """Manifest versions are semver-like; prerelease tags PEP 440 cannot parse compare by release."""
    try:
        return Version(version)
    except InvalidVersion:
        return Version(version.split("-", 1)[0])


def review(old, new):
    old_version, new_version = _order(old["version"]), _order(new["version"])
    return {
        "module": new["id"],
        "from_version": old["version"],
        "to_version": new["version"],
        "downgrade": new_version < old_version,
        "image_changed": old["container"]["image"] != new["container"]["image"],
        "port": {"from": old["container"]["port"], "to": new["container"]["port"]},
        "nexus_range": {"from": old["nexus"], "to": new["nexus"]},
        "capabilities": _set_diff(old["capabilities"], new["capabilities"]),
        "events": {
            "produces": _set_diff(old["events"]["produces"], new["events"]["produces"]),
            "consumes": _set_diff(old["events"]["consumes"], new["events"]["consumes"]),
        },
        "resources": _set_diff(
            [r["type"] for r in old.get("resources", [])],
            [r["type"] for r in new.get("resources", [])],
        ),
        "reference_scopes": {
            "read": _set_diff(_scopes(old, "read"), _scopes(new, "read")),
            "resolve": _set_diff(_scopes(old, "resolve"), _scopes(new, "resolve")),
        },
        "persistent_data": ("retained" if "storage.data" in old["capabilities"] else "none")
        + (
            "; no longer mounted by the new version"
            if "storage.data" in old["capabilities"] and "storage.data" not in new["capabilities"]
            else ""
        ),
        "backup": backup_policy(old),
        "migrations": "Data migrations, if any, are run by the module itself. Nexus does not change module data.",
    }


def add_update_routes(app, ctx, create_backup):
    def module(module_id):
        with ctx.db.connect() as conn:
            row = conn.execute("SELECT * FROM modules WHERE id=?", (module_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Module not found")
        return dict(row)

    def prepare(row, manifest):
        new = ctx.validate(manifest)
        old = json.loads(row["manifest"])
        if new["id"] != row["id"]:
            raise HTTPException(422, "An update must keep the module identity")
        if new == old:
            raise HTTPException(409, "This manifest is already installed")
        return old, new, review(old, new)

    def record(conn, update_id, state, stage, detail=""):
        conn.execute(
            "UPDATE module_updates SET state=?,stage=?,detail=?,updated_at=? WHERE id=?",
            (state, stage, detail, ctx.now(), update_id),
        )

    @app.post("/api/v1/modules/{module_id}/update/review")
    def update_review(module_id: str, manifest: dict, owner=Depends(ctx.require_owner)):
        row = module(module_id)
        _, _, diff = prepare(row, manifest)
        return {**diff, "state": row["state"], "requires_approval": diff["capabilities"]["added"]}

    @app.get("/api/v1/modules/{module_id}/updates")
    def updates(module_id: str, owner=Depends(ctx.require_owner)):
        with ctx.db.connect() as conn:
            rows = conn.execute(
                "SELECT id,module,from_version,to_version,state,stage,detail,started_at,updated_at FROM module_updates WHERE module=? ORDER BY started_at DESC",
                (module_id,),
            )
            return [dict(r) for r in rows]

    @app.post("/api/v1/modules/{module_id}/update")
    def apply(module_id: str, body: UpdateBody, owner=Depends(ctx.require_owner)):
        actor = owner["user_id"]
        with ctx.lock:
            row = module(module_id)
            if row["state"] not in {"enabled", "disabled", "error"}:
                raise HTTPException(409, "Module is busy (" + row["state"] + ")")
            old, new, diff = prepare(row, body.manifest)
            if set(body.grants) != set(new["capabilities"]):
                missing = sorted(set(new["capabilities"]) - set(body.grants))
                raise HTTPException(
                    422,
                    "Grants must match the reviewed capability request"
                    + (": approve " + ", ".join(missing) if missing else ""),
                )
            if diff["downgrade"] and not body.allow_downgrade:
                raise HTTPException(
                    409,
                    "This is a downgrade. Data written by the newer version may not be readable; confirm allow_downgrade.",
                )
            required = os.getenv("NEXUS_UPDATE_BACKUP", "recommend") == "require"
            if body.backup_before:
                if diff["backup"] != "recommended":
                    raise HTTPException(422, "This module cannot create a backup")
                create_backup(row, actor)  # Raises on failure: nothing below runs.
            elif required and diff["backup"] == "recommended":
                raise HTTPException(
                    409, "This installation requires a backup before updating persistent modules"
                )
            update_id = str(uuid.uuid4())
            with ctx.db.connect() as conn:
                conn.execute(
                    "INSERT INTO module_updates(id,module,from_version,to_version,from_manifest,to_manifest,state,stage,detail,started_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        update_id,
                        module_id,
                        old["version"],
                        new["version"],
                        json.dumps(old),
                        json.dumps(new),
                        "applying",
                        "prepare",
                        "",
                        ctx.now(),
                        ctx.now(),
                    ),
                )
                ctx.audit(conn, actor, "module.update.requested", module_id)
            start = row["state"] in {"enabled", "error"}
            with ctx.db.connect() as conn:
                taken = conn.execute(
                    "SELECT 1 FROM modules WHERE port=? AND id<>?",
                    (new["container"]["port"], module_id),
                ).fetchone()
                if taken:
                    record(
                        conn, update_id, "failed", "prepare", "Reserved port is already registered"
                    )
            if taken:
                raise HTTPException(409, "The new version's reserved port is already registered")
            with ctx.db.connect() as conn:
                conn.execute(
                    "UPDATE modules SET manifest=?,port=?,state=?,token=NULL,resolver_key=NULL,health='unknown' WHERE id=?",
                    (
                        json.dumps(new),
                        new["container"]["port"],
                        "updating" if start else "disabled",
                        module_id,
                    ),
                )
            if not start:
                with ctx.db.connect() as conn:
                    record(
                        conn,
                        update_id,
                        "applied",
                        "not_started",
                        "Applied while disabled; health is verified when enabled.",
                    )
                    ctx.audit(conn, actor, "module.update.completed", module_id)
                return {"state": "disabled", "update": update_id, "health": "not_verified", **diff}
            token, resolver_key = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            recovery = f"No automatic rollback was performed and its data was not deleted. To recover, review and apply the previous manifest (v{old['version']}); if v{new['version']} migrated data, restore a backup instead."
            try:
                # The broker replaces the container and keeps the module's named data volume.
                ctx.runtime.call("enable", module_id, new, token, resolver_key)
            except RuntimeError as exc:
                with ctx.db.connect() as conn:
                    conn.execute("UPDATE modules SET state='error' WHERE id=?", (module_id,))
                    record(conn, update_id, "failed", "start", str(exc))
                    ctx.audit(conn, actor, "module.update.failed", module_id)
                    ctx.notice(
                        conn,
                        "nexus",
                        f"Update of {module_id} to v{new['version']} failed to start. {recovery}",
                    )
                raise HTTPException(502, "Update failed to start; the module is in error") from exc
            with ctx.db.connect() as conn:
                conn.execute(
                    "UPDATE modules SET state='enabled',token=?,resolver_key=? WHERE id=?",
                    (hashlib.sha256(token.encode()).hexdigest(), resolver_key, module_id),
                )
                record(conn, update_id, "applying", "health")
            target = {
                "id": module_id,
                "port": new["container"]["port"],
                "resolver_key": resolver_key,
            }
            healthy = False
            attempts = max(1, int(os.getenv("NEXUS_UPDATE_HEALTH_ATTEMPTS", "10")))
            for attempt in range(attempts):
                try:
                    healthy = ctx.upstream(target, "GET", new["routes"]["health"])[0] == 200
                except HTTPException:
                    healthy = False
                if healthy:
                    break
                if attempt + 1 < attempts:
                    sleep(1)
            with ctx.db.connect() as conn:
                if healthy:
                    conn.execute("UPDATE modules SET health='healthy' WHERE id=?", (module_id,))
                    record(conn, update_id, "completed", "done")
                    ctx.audit(conn, actor, "module.update.completed", module_id)
                    ctx.notice(
                        conn,
                        "nexus",
                        f"Module {module_id} updated from v{old['version']} to v{new['version']}.",
                    )
                    return {"state": "enabled", "update": update_id, "health": "healthy", **diff}
                conn.execute(
                    "UPDATE modules SET state='error',token=NULL,resolver_key=NULL,health='unhealthy' WHERE id=?",
                    (module_id,),
                )
                record(conn, update_id, "failed", "health", "Post-update health check did not pass")
                ctx.audit(conn, actor, "module.update.failed", module_id)
                ctx.notice(
                    conn,
                    "nexus",
                    f"Module {module_id} v{new['version']} did not become healthy; its access was revoked. {recovery}",
                )
            raise HTTPException(502, "The updated module did not become healthy; it is in error")
