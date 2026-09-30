"""Per-module trusted external origins for bridge navigation. Trust names an origin, never a URL."""

import ipaddress
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_PORTS = {"https": 443, "http": 80}


class OriginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    origin: str = Field(max_length=300)


def canonical_origin(value: str) -> str:
    """Accept exactly the WHATWG serialization `scheme://host[:port]` and nothing more.

    Hosts must already be ASCII (browsers serialize IDNs as punycode), so a deceptive Unicode
    hostname is a different origin from the name it imitates. Default ports are omitted; any
    path, query, fragment, credentials or trailing slash is rejected rather than normalized."""
    parts = urlsplit(value)
    if parts.scheme not in DEFAULT_PORTS or "@" in parts.netloc:
        raise ValueError("Only http(s) origins without credentials can be trusted")
    if parts.path or parts.query or parts.fragment or "?" in value or "#" in value:
        raise ValueError("An origin has no path, query or fragment")
    host = parts.hostname or ""
    try:
        port = parts.port
        address = ipaddress.ip_address(host) if host and ":" in host else None
    except ValueError as exc:
        raise ValueError("Invalid origin port or address") from exc
    if not address and not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9.])?", host):
        raise ValueError("Origin host must be an ASCII hostname or IP address")
    netloc = f"[{address.compressed}]" if address else host
    if port and port != DEFAULT_PORTS[parts.scheme]:
        netloc += f":{port}"
    canonical = f"{parts.scheme}://{netloc}"
    if canonical != value:
        raise ValueError("Origin is not in canonical form: expected " + canonical)
    return canonical


def trusted_origins(conn, module_id):
    return [
        row["origin"]
        for row in conn.execute(
            "SELECT origin FROM module_external_origins WHERE module=? ORDER BY origin",
            (module_id,),
        )
    ]


def add_navigation_routes(app, db, require_owner, audit):
    def module(conn, module_id):
        row = conn.execute("SELECT manifest FROM modules WHERE id=?", (module_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Module not found")
        if "ui.application" not in json.loads(row["manifest"])["capabilities"]:
            raise HTTPException(409, "Only application modules request external navigation")

    def checked(value):
        try:
            return canonical_origin(value)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/v1/modules/{module_id}/external-origins")
    def trust(module_id: str, body: OriginBody, owner=Depends(require_owner)):
        origin = checked(body.origin)
        with db.connect() as conn:
            module(conn, module_id)
            conn.execute(
                "INSERT INTO module_external_origins(module,origin,approved_at) VALUES(?,?,?) ON CONFLICT(module,origin) DO NOTHING",
                (module_id, origin, datetime.now(timezone.utc).isoformat()),
            )
            audit(conn, owner["user_id"], "module.external.trusted", module_id)
            return {"module": module_id, "external_origins": trusted_origins(conn, module_id)}

    @app.delete("/api/v1/modules/{module_id}/external-origins")
    def revoke(module_id: str, origin: str = Query(max_length=300), owner=Depends(require_owner)):
        with db.connect() as conn:
            removed = conn.execute(
                "DELETE FROM module_external_origins WHERE module=? AND origin=?",
                (module_id, origin),
            ).rowcount
            if removed:
                audit(conn, owner["user_id"], "module.external.revoked", module_id)
            remaining = trusted_origins(conn, module_id)
        if not removed:
            raise HTTPException(404, "This origin is not trusted for the module")
        return {"module": module_id, "external_origins": remaining}
