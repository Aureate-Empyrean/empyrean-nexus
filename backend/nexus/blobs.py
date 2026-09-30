"""Bounded shared blob storage. A digest is identity, never authorization."""

import base64
import hashlib
import os
import re
import tempfile

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field


class Upload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(max_length=1400000)


def add_blob_routes(app, db, data, require_module, capability):
    directory = data / "blobs"
    directory.mkdir(mode=0o700, exist_ok=True)

    @app.post("/api/v1/module/blobs", status_code=201)
    def upload(body: Upload, module=Depends(require_module)):
        capability(module, "blobs.write")
        try:
            content = base64.b64decode(body.content, validate=True)
        except ValueError:
            raise HTTPException(422, "Invalid base64")
        if len(content) > 1024 * 1024:
            raise HTTPException(413, "Blob exceeds 1 MiB")
        key = hashlib.sha256(content).hexdigest()
        fd, temp = tempfile.mkstemp(dir=directory)
        try:
            with os.fdopen(fd, "wb") as out:
                out.write(content)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp, directory / key)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        with db.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO blobs VALUES(?,?)", (key, len(content)))
            conn.execute("INSERT OR IGNORE INTO blob_grants VALUES(?,?)", (key, module["id"]))
        return {"id": key, "size": len(content)}

    @app.get("/api/v1/module/blobs/{key}")
    def download(key: str, module=Depends(require_module)):
        capability(module, "blobs.read")
        if not re.fullmatch("[a-f0-9]{64}", key):
            raise HTTPException(404, "Blob not found")
        with db.connect() as conn:
            if not conn.execute(
                "SELECT 1 FROM blob_grants WHERE blob=? AND module=?", (key, module["id"])
            ).fetchone():
                raise HTTPException(404, "Blob not found")
        path = directory / key
        if not path.exists():
            raise HTTPException(503, "Blob unavailable")
        return {"id": key, "content": base64.b64encode(path.read_bytes()).decode()}
