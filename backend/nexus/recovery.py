"""Module backup/restore orchestration. Module data is an opaque, module-owned artifact."""

import hashlib
import json
import os
import re
import shutil
import tarfile
import tempfile
import uuid
from datetime import datetime

import httpx
from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, ConfigDict
from starlette.background import BackgroundTask

from nexus import VERSION
from nexus.references import ReconcileError, enumerable, reconcile_outgoing

MAX_ARTIFACT = 256 * 1024 * 1024
FORMAT = re.compile(r"^[a-z][a-z0-9.-]{0,63}$")
HEADER = "X-Empyrean-Backup-"


class Confirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_replace: bool = False


class RecoveryError(Exception):
    pass


def sha256_file(path):
    hasher, size = hashlib.sha256(), 0
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(block)
            size += len(block)
    return hasher.hexdigest(), size


def backup_metadata(row, headers, artifact_sha, artifact_size, blobs):
    """Validate module-declared metadata; Nexus never interprets the artifact itself."""
    manifest = json.loads(row["manifest"])
    value = {
        k[len(HEADER) :].lower(): v
        for k, v in headers.items()
        if k.lower().startswith(HEADER.lower())
    }
    if value.get("module") != row["id"]:
        raise RecoveryError("Backup module identity does not match")
    if value.get("module-version") != manifest["version"]:
        raise RecoveryError("Backup module version does not match the installed version")
    if not FORMAT.fullmatch(value.get("format", "")):
        raise RecoveryError("Backup format name is missing or invalid")
    try:
        format_version = int(value.get("format-version", ""))
        created = datetime.fromisoformat(value.get("created-at", ""))
        restorable = value.get("restorable-by") or "==" + manifest["version"]
        SpecifierSet(restorable)
    except (ValueError, InvalidSpecifier) as exc:
        raise RecoveryError("Backup metadata is invalid") from exc
    if not 1 <= format_version <= 1_000_000 or created.tzinfo is None:
        raise RecoveryError("Backup format version or creation time is invalid")
    return {
        "format": "empyrean-module-backup",
        "version": 1,
        "module": row["id"],
        "module_version": manifest["version"],
        "module_format": value["format"],
        "module_format_version": format_version,
        "created_at": created.isoformat(),
        "restorable_by": restorable,
        "nexus_version": VERSION,
        "artifact": {"sha256": artifact_sha, "size": artifact_size},
        "blobs": blobs,
    }


def add_recovery_routes(app, ctx):
    root = ctx.data / "backups" / "modules"

    def directory(module_id, backup_id):
        return root / module_id / backup_id

    def call(row, path, content=None, headers=None, timeout=300):
        """Returns the owner's JSON reply or raises RecoveryError; redirects are refused."""
        try:
            with httpx.Client(
                transport=ctx.transport, timeout=timeout, follow_redirects=False, trust_env=False
            ) as client:
                response = client.post(
                    ctx.runtime.target(row["id"], row["port"]) + path,
                    content=content,
                    headers={"X-Nexus-Resolver-Key": row["resolver_key"], **(headers or {})},
                )
        except httpx.HTTPError as exc:
            raise RecoveryError("Module did not respond") from exc
        if response.status_code != 200:
            detail = ""
            try:
                detail = str(response.json().get("detail", ""))[:200]
            except (ValueError, AttributeError):
                pass
            raise RecoveryError(f"Module answered HTTP {response.status_code}. {detail}".strip())
        try:
            return response.json()
        except ValueError as exc:
            raise RecoveryError("Module reply is not JSON") from exc

    def module(module_id):
        with ctx.db.connect() as conn:
            row = conn.execute("SELECT * FROM modules WHERE id=?", (module_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Module not found")
        return dict(row)

    def require_running_participant(row):
        if "backup" not in json.loads(row["manifest"]):
            raise HTTPException(409, "This module does not implement the backup contract")
        if row["state"] != "enabled" or not row["resolver_key"]:
            raise HTTPException(409, "The module must be enabled")

    def create_backup(row, actor):
        """Caller holds the lifecycle lock. Nothing is recorded unless every part is complete."""
        require_running_participant(row)
        backup_id = str(uuid.uuid4())
        target = directory(row["id"], backup_id)
        target.mkdir(parents=True, mode=0o700)
        try:
            hasher, size = hashlib.sha256(), 0
            try:
                with httpx.Client(
                    transport=ctx.transport, timeout=300, follow_redirects=False, trust_env=False
                ) as client:
                    with client.stream(
                        "POST",
                        ctx.runtime.target(row["id"], row["port"]) + "/empyrean/v1/backup/export",
                        headers={"X-Nexus-Resolver-Key": row["resolver_key"]},
                    ) as response:
                        if response.status_code != 200:
                            raise RecoveryError(f"Module answered HTTP {response.status_code}")
                        headers = dict(response.headers)
                        with open(target / "artifact", "wb") as out:
                            for chunk in response.iter_bytes():
                                size += len(chunk)
                                if size > MAX_ARTIFACT:
                                    raise RecoveryError("Backup artifact exceeds 256 MiB")
                                hasher.update(chunk)
                                out.write(chunk)
                            out.flush()
                            os.fsync(out.fileno())
            except httpx.HTTPError as exc:
                raise RecoveryError("Module did not respond") from exc
            blobs = []
            with ctx.db.connect() as conn:
                granted = [
                    r["blob"]
                    for r in conn.execute(
                        "SELECT blob FROM blob_grants WHERE module=? ORDER BY blob", (row["id"],)
                    )
                ]
            if granted:
                (target / "blobs").mkdir(mode=0o700)
            for digest in granted:
                source = ctx.data / "blobs" / digest
                if not source.exists():
                    raise RecoveryError("A shared file used by this module is missing: " + digest)
                shutil.copyfile(source, target / "blobs" / digest)
                blobs.append({"sha256": digest, "size": (target / "blobs" / digest).stat().st_size})
            metadata = backup_metadata(row, headers, hasher.hexdigest(), size, blobs)
            metadata["id"] = backup_id
            metadata["exported_at"] = ctx.now()
            (target / "metadata.json").write_text(json.dumps(metadata, indent=2))
            with ctx.db.connect() as conn:
                conn.execute(
                    "INSERT INTO module_backups(id,module,metadata,created_at) VALUES(?,?,?,?)",
                    (backup_id, row["id"], json.dumps(metadata), metadata["exported_at"]),
                )
                ctx.audit(conn, actor, "module.backup.completed", row["id"])
            return metadata
        except RecoveryError as exc:
            shutil.rmtree(target, ignore_errors=True)
            with ctx.db.connect() as conn:
                ctx.audit(conn, actor, "module.backup.failed", row["id"])
                ctx.notice(conn, "nexus", f"Backup of module {row['id']} failed: {exc}")
            raise HTTPException(502, "Backup failed: " + str(exc)) from exc

    def load_backup(module_id, backup_id):
        with ctx.db.connect() as conn:
            record = conn.execute(
                "SELECT metadata FROM module_backups WHERE id=? AND module=?",
                (backup_id, module_id),
            ).fetchone()
        if not record:
            raise HTTPException(404, "Backup not found")
        return json.loads(record["metadata"])

    def verify_backup(metadata):
        target = directory(metadata["module"], metadata["id"])
        artifact = target / "artifact"
        if not artifact.exists() or sha256_file(artifact) != (
            metadata["artifact"]["sha256"],
            metadata["artifact"]["size"],
        ):
            raise HTTPException(409, "Backup artifact is missing or damaged; nothing was changed")
        for blob in metadata["blobs"]:
            path = target / "blobs" / blob["sha256"]
            if not path.exists() or sha256_file(path)[0] != blob["sha256"]:
                raise HTTPException(409, "A backed-up shared file is damaged; nothing was changed")
        return artifact

    def job(conn, job_id, state, stage, detail=""):
        conn.execute(
            "UPDATE module_restores SET state=?,stage=?,detail=?,updated_at=? WHERE id=?",
            (state, stage, detail, ctx.now(), job_id),
        )

    def finish(module_id, job_id, actor):
        """Reconcile derived Nexus state, then let the module resume retention (finalize)."""
        row = module(module_id)
        manifest = json.loads(row["manifest"])
        warnings = []
        try:
            if enumerable(manifest):
                with ctx.db.connect() as conn:
                    job(conn, job_id, "running", "reconcile")
                reconcile_outgoing(ctx.db, ctx.runtime, ctx.transport, module_id)
            elif "references.create" in manifest["capabilities"]:
                warnings.append(
                    "Reference index not reconciled: the module does not enumerate outgoing references."
                )
        except ReconcileError as exc:
            with ctx.db.connect() as conn:
                job(conn, job_id, "needs_attention", "reconcile", str(exc))
                ctx.audit(conn, actor, "module.restore.failed", module_id)
                ctx.notice(
                    conn,
                    "nexus",
                    f"Restore of {module_id} needs attention: references were not reconciled ({exc}). Automatic purges stay suspended until the restore is finalized.",
                )
            raise HTTPException(
                502, "Restored data is in place, but reconciliation failed"
            ) from exc
        try:
            with ctx.db.connect() as conn:
                job(conn, job_id, "running", "finalize")
            if call(row, "/empyrean/v1/backup/finalize").get("finalized") is not True:
                raise RecoveryError("Module did not confirm finalization")
        except RecoveryError as exc:
            with ctx.db.connect() as conn:
                job(conn, job_id, "needs_attention", "finalize", str(exc))
                ctx.audit(conn, actor, "module.restore.failed", module_id)
                ctx.notice(
                    conn,
                    "nexus",
                    f"Restore of {module_id} needs attention: finalization failed ({exc}). Retry finalization.",
                )
            raise HTTPException(502, "Restored data is in place, but finalization failed") from exc
        with ctx.db.connect() as conn:
            job(conn, job_id, "completed", "done", " ".join(warnings))
            ctx.audit(conn, actor, "module.restore.completed", module_id)
            ctx.notice(conn, "nexus", f"Module {module_id} was restored from backup.")
        return {"id": job_id, "state": "completed", "warnings": warnings}

    def restore(row, backup_id, actor):
        metadata = load_backup(row["id"], backup_id)
        require_running_participant(row)
        installed = json.loads(row["manifest"])["version"]
        try:
            compatible = Version(installed) in SpecifierSet(metadata["restorable_by"])
        except (InvalidVersion, InvalidSpecifier):
            compatible = False
        if not compatible:
            raise HTTPException(
                409,
                f"Installed version {installed} cannot restore this backup (requires {metadata['restorable_by']})",
            )
        artifact = verify_backup(metadata)
        headers = {
            "Content-Type": "application/octet-stream",
            HEADER + "Module": metadata["module"],
            HEADER + "Module-Version": metadata["module_version"],
            HEADER + "Format": metadata["module_format"],
            HEADER + "Format-Version": str(metadata["module_format_version"]),
            HEADER + "Created-At": metadata["created_at"],
        }
        job_id = str(uuid.uuid4())
        with ctx.db.connect() as conn:
            conn.execute(
                "INSERT INTO module_restores(id,module,backup,state,stage,detail,started_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (job_id, row["id"], backup_id, "running", "validate", "", ctx.now(), ctx.now()),
            )
            # Module API access and the gateway are paused while its data is replaced.
            conn.execute("UPDATE modules SET state='restoring' WHERE id=?", (row["id"],))
            ctx.audit(conn, actor, "module.restore.requested", row["id"])
        try:
            with open(artifact, "rb") as body:
                if (
                    call(row, "/empyrean/v1/backup/validate", body, headers).get("valid")
                    is not True
                ):
                    raise RecoveryError("Module did not confirm the backup is valid")
        except RecoveryError as exc:
            with ctx.db.connect() as conn:
                conn.execute("UPDATE modules SET state='enabled' WHERE id=?", (row["id"],))
                job(conn, job_id, "failed", "validate", str(exc))
                ctx.audit(conn, actor, "module.restore.failed", row["id"])
            raise HTTPException(422, "The module rejected the backup; nothing was changed") from exc
        with ctx.db.connect() as conn:
            job(conn, job_id, "running", "blobs")
        # Shared files are only ever added, never removed, so this step is safe to repeat.
        try:
            for blob in metadata["blobs"]:
                path = ctx.data / "blobs" / blob["sha256"]
                if not path.exists():
                    fd, temp = tempfile.mkstemp(dir=ctx.data / "blobs")
                    os.close(fd)
                    shutil.copyfile(
                        directory(row["id"], backup_id) / "blobs" / blob["sha256"], temp
                    )
                    os.replace(temp, path)
                with ctx.db.connect() as conn:
                    conn.execute(
                        "INSERT INTO blobs(id,size) VALUES(?,?) ON CONFLICT(id) DO NOTHING",
                        (blob["sha256"], blob["size"]),
                    )
                    conn.execute(
                        "INSERT INTO blob_grants(blob,module) VALUES(?,?) ON CONFLICT(blob,module) DO NOTHING",
                        (blob["sha256"], row["id"]),
                    )
        except OSError as exc:
            with ctx.db.connect() as conn:
                conn.execute("UPDATE modules SET state='enabled' WHERE id=?", (row["id"],))
                job(conn, job_id, "failed", "blobs", "Shared files could not be restored")
                ctx.audit(conn, actor, "module.restore.failed", row["id"])
            raise HTTPException(
                502, "Shared files could not be restored; module data was not changed"
            ) from exc
        try:
            with ctx.db.connect() as conn:
                job(conn, job_id, "running", "restore")
            with open(artifact, "rb") as body:
                if (
                    call(row, "/empyrean/v1/backup/restore", body, headers).get("restored")
                    is not True
                ):
                    raise RecoveryError("Module did not confirm the restore")
        except RecoveryError as exc:
            with ctx.db.connect() as conn:
                conn.execute(
                    "UPDATE modules SET state='error',token=NULL,resolver_key=NULL,health='restore_failed' WHERE id=?",
                    (row["id"],),
                )
                job(conn, job_id, "failed", "restore", str(exc))
                ctx.audit(conn, actor, "module.restore.failed", row["id"])
                ctx.notice(
                    conn,
                    "nexus",
                    f"Restore of {row['id']} failed while replacing data ({exc}). Its data state is unknown and its access was revoked. Enable it and retry the restore.",
                )
            raise HTTPException(502, "Restore failed; the module requires intervention") from exc
        with ctx.db.connect() as conn:
            conn.execute("UPDATE modules SET state='enabled' WHERE id=?", (row["id"],))
        return finish(row["id"], job_id, actor)

    @app.post("/api/v1/modules/{module_id}/backups", status_code=201)
    def create(module_id: str, owner=Depends(ctx.require_owner)):
        with ctx.lock:
            return create_backup(module(module_id), owner["user_id"])

    @app.get("/api/v1/modules/{module_id}/backups")
    def backups(module_id: str, owner=Depends(ctx.require_owner)):
        with ctx.db.connect() as conn:
            return [
                json.loads(r["metadata"])
                for r in conn.execute(
                    "SELECT metadata FROM module_backups WHERE module=? ORDER BY created_at DESC",
                    (module_id,),
                )
            ]

    @app.get("/api/v1/modules/{module_id}/backups/{backup_id}/download")
    def download(module_id: str, backup_id: str, owner=Depends(ctx.require_owner)):
        metadata = load_backup(module_id, backup_id)
        verify_backup(metadata)
        source = directory(module_id, backup_id)
        fd, bundle = tempfile.mkstemp(dir=ctx.data, suffix=".tar")
        os.close(fd)
        with tarfile.open(bundle, "w") as archive:
            archive.add(source / "metadata.json", "metadata.json")
            archive.add(source / "artifact", "artifact")
            for blob in metadata["blobs"]:
                archive.add(source / "blobs" / blob["sha256"], "blobs/" + blob["sha256"])
        with ctx.db.connect() as conn:
            ctx.audit(conn, owner["user_id"], "module.backup.exported", module_id)
        return FileResponse(
            bundle,
            media_type="application/x-tar",
            filename=f"{module_id}-{backup_id}.empyrean-backup.tar",
            background=BackgroundTask(os.unlink, bundle),
        )

    @app.post("/api/v1/modules/{module_id}/backups/{backup_id}/restore")
    def restore_route(
        module_id: str, backup_id: str, body: Confirm, owner=Depends(ctx.require_owner)
    ):
        if not body.confirm_replace:
            raise HTTPException(
                422, "Restoring replaces the module's current data; confirm_replace is required"
            )
        with ctx.lock:
            return restore(module(module_id), backup_id, owner["user_id"])

    @app.get("/api/v1/modules/{module_id}/restores")
    def restores(module_id: str, owner=Depends(ctx.require_owner)):
        with ctx.db.connect() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM module_restores WHERE module=? ORDER BY started_at DESC",
                    (module_id,),
                )
            ]

    @app.post("/api/v1/modules/{module_id}/restores/{job_id}/finalize")
    def retry_finalize(module_id: str, job_id: str, owner=Depends(ctx.require_owner)):
        with ctx.lock:
            with ctx.db.connect() as conn:
                record = conn.execute(
                    "SELECT * FROM module_restores WHERE id=? AND module=?", (job_id, module_id)
                ).fetchone()
            if not record:
                raise HTTPException(404, "Restore not found")
            if record["state"] != "needs_attention" or record["stage"] not in {
                "reconcile",
                "finalize",
            }:
                raise HTTPException(
                    409, "Only restores waiting for reconciliation/finalization can be finalized"
                )
            if module(module_id)["state"] != "enabled":
                raise HTTPException(409, "The module must be enabled")
            return finish(module_id, job_id, owner["user_id"])

    @app.post("/api/v1/modules/{module_id}/references/reconcile")
    def reconcile(module_id: str, owner=Depends(ctx.require_owner)):
        with ctx.lock:
            module(module_id)
            try:
                summary = reconcile_outgoing(ctx.db, ctx.runtime, ctx.transport, module_id)
            except ReconcileError as exc:
                with ctx.db.connect() as conn:
                    ctx.audit(conn, owner["user_id"], "module.references.failed", module_id)
                raise HTTPException(
                    502, "Reconciliation failed; the index was not changed: " + str(exc)
                ) from exc
            with ctx.db.connect() as conn:
                ctx.audit(conn, owner["user_id"], "module.references.reconciled", module_id)
            return {"module": module_id, **summary}

    return create_backup
