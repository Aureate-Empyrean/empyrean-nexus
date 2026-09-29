"""Entity References v1: identities and relationships, never module domain objects."""

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, ValidationError

MODULE = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
TYPE = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
RESOURCE_PATTERN = rf"^nexus:v1:({MODULE}):({TYPE}):([A-Za-z0-9][A-Za-z0-9._~-]{{0,127}})$"
RESOURCE = re.compile(RESOURCE_PATTERN, flags=re.ASCII)


def parse_resource(value: str):
    match = RESOURCE.fullmatch(value)
    if not match or len(match[1]) > 48 or len(match[2]) > 48:
        raise ValueError("Expected nexus:v1:<module>:<type>:<stable-id>")
    return {"version": 1, "module": match[1], "type": match[2], "id": match[3]}


def parsed(value):
    try:
        return parse_resource(value)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReferenceWrite(Strict):
    source: str = Field(max_length=240)
    target: str = Field(max_length=240)
    relation: str = Field(pattern=r"^[a-z][a-z0-9-]*\.[a-z][a-z0-9_.-]*$", max_length=120)
    metadata: dict = Field(default_factory=dict)
    readers: list[str] = Field(default_factory=list, max_length=32)


class ResolveRequest(Strict):
    resource: str = Field(max_length=240)


class Representation(Strict):
    resource: str = Field(max_length=240)
    label: str = Field(min_length=1, max_length=200)
    open_path: str | None = Field(default=None, max_length=256, pattern=r"^/[A-Za-z0-9/_-]*$")
    representation: dict | None = None


def permitted(module, resource, scope):
    identity = parse_resource(resource)
    if identity["module"] == module["id"]:
        return True
    return {"module": identity["module"], "type": identity["type"]} in module["manifest"].get(
        "references", {}
    ).get(scope, [])


def visible(module, edge):
    if "references.read" not in module["manifest"]["capabilities"]:
        return False
    readers = edge["readers"]
    if isinstance(readers, str):
        readers = json.loads(readers)
    return edge["creator"] == module["id"] or module["id"] in readers


def event_visible(module, envelope, db):
    if envelope["source"] != "nexus" or not envelope["type"].startswith("nexus.reference."):
        return True
    if "references.read" not in module["manifest"]["capabilities"]:
        return False
    payload = envelope["payload"]
    if not isinstance(payload, dict) or not all(
        isinstance(payload.get(key), str) for key in ("creator", "id")
    ):
        return False
    if payload["creator"] == module["id"]:
        return True
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM resource_references WHERE id=?", (payload["id"],)
        ).fetchone()
    # Use CURRENT sharing state so revoking access also hides previously queued events.
    # Once deleted, events are creator-only; there is no retained audience/tombstone index.
    return bool(
        row
        and visible(module, row)
        and any(permitted(module, row[field], "read") for field in ("source", "target"))
    )


def edge_json(row):
    data = dict(row)
    data["metadata"] = json.loads(data["metadata"])
    data["readers"] = json.loads(data["readers"])
    return data


def add_reference_routes(app, db, require_module, require_owner, runtime, transport):
    def require_cap(module, capability):
        if capability not in module["manifest"]["capabilities"]:
            raise HTTPException(403, "Capability required: " + capability)

    def declared(conn, identity):
        row = conn.execute(
            "SELECT manifest FROM modules WHERE id=?", (identity["module"],)
        ).fetchone()
        if not row:
            raise HTTPException(422, "Reference endpoint module is not registered")
        resources = json.loads(row["manifest"]).get("resources", [])
        if not any(r["type"] == identity["type"] for r in resources):
            raise HTTPException(422, "Resource type is not declared by its owner")

    def record_event(conn, action, edge):
        stamp = utcnow()
        # Do not broadcast arbitrary edge metadata. Polling also applies reference visibility.
        payload = {name: edge[name] for name in ("id", "creator")}
        envelope = {
            "id": str(uuid.uuid4()),
            "schema_version": 1,
            "type": "nexus.reference." + action,
            "source": "nexus",
            "timestamp": stamp,
            "payload": payload,
            "correlation_id": None,
        }
        conn.execute(
            "INSERT INTO events(id,type,source,timestamp,envelope) VALUES(?,?,?,?,?)",
            (envelope["id"], envelope["type"], "nexus", stamp, json.dumps(envelope)),
        )
        conn.execute(
            "DELETE FROM events WHERE seq <= (SELECT COALESCE(MAX(seq),0)-10000 FROM events)"
        )

    @app.post("/api/v1/module/references")
    def create_reference(body: ReferenceWrite, module=Depends(require_module)):
        require_cap(module, "references.create")
        source, target = parsed(body.source), parsed(body.target)
        if source["module"] != module["id"] or not body.relation.startswith(module["id"] + "."):
            raise HTTPException(
                403, "Only source owners may write their own namespaced relationships"
            )
        if any(not re.fullmatch(MODULE, item) or len(item) > 48 for item in body.readers):
            raise HTTPException(422, "Readers must be explicit module IDs")
        readers = json.dumps(sorted(set(body.readers)))
        try:
            metadata = json.dumps(body.metadata, sort_keys=True, allow_nan=False)
        except ValueError as exc:
            raise HTTPException(422, "Metadata must contain finite JSON values") from exc
        if len(metadata.encode()) > 2048:
            raise HTTPException(422, "Reference metadata exceeds 2 KiB")
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            old = conn.execute(
                "SELECT * FROM resource_references WHERE source=? AND target=? AND relation=?",
                (body.source, body.target, body.relation),
            ).fetchone()
            if not old:
                declared(conn, source)
                declared(conn, target)
                count = conn.execute(
                    "SELECT COUNT(*) FROM resource_references WHERE creator=?", (module["id"],)
                ).fetchone()[0]
                if count >= 100000:
                    raise HTTPException(409, "Module reference limit reached (100,000)")
                stamp = utcnow()
                conn.execute(
                    "INSERT INTO resource_references(id,source,target,relation,creator,metadata,readers,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        str(uuid.uuid4()),
                        body.source,
                        body.target,
                        body.relation,
                        module["id"],
                        metadata,
                        readers,
                        stamp,
                        stamp,
                    ),
                )
            elif old["metadata"] != metadata or old["readers"] != readers:
                conn.execute(
                    "UPDATE resource_references SET metadata=?,readers=?,updated_at=? WHERE id=?",
                    (metadata, readers, utcnow(), old["id"]),
                )
            row = conn.execute(
                "SELECT * FROM resource_references WHERE source=? AND target=? AND relation=?",
                (body.source, body.target, body.relation),
            ).fetchone()
            if not old or old["metadata"] != metadata or old["readers"] != readers:
                record_event(conn, "created" if not old else "updated", row)
            return {"created": old is None, "reference": edge_json(row)}

    @app.delete("/api/v1/module/references/{reference_id}")
    def delete_reference(reference_id: uuid.UUID, module=Depends(require_module)):
        require_cap(module, "references.create")
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM resource_references WHERE id=? AND creator=?",
                (str(reference_id), module["id"]),
            ).fetchone()
            if not row:
                raise HTTPException(404, "Owned reference not found")
            record_event(conn, "deleted", row)
            conn.execute("DELETE FROM resource_references WHERE id=?", (str(reference_id),))
        return {"deleted": True}

    def query(resource, direction, after, limit, module=None):
        parsed(resource)
        if module:
            require_cap(module, "references.read")
            if not permitted(module, resource, "read"):
                raise HTTPException(403, "Resource type is outside the granted read scope")
        column = "target" if direction == "incoming" else "source"
        predicate = ""
        values = [resource, after]
        if module:
            predicate = " AND (creator=? OR EXISTS (SELECT 1 FROM json_each(resource_references.readers) WHERE value=?))"
            values.extend([module["id"], module["id"]])
        values.append(limit)
        with db.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM resource_references WHERE {column}=? AND seq>?{predicate} ORDER BY seq LIMIT ?",
                values,
            ).fetchall()
        # Pagination itself must not reveal hidden incoming edges.
        return {
            "references": [edge_json(row) for row in rows],
            "next_cursor": rows[-1]["seq"] if rows else after,
            "has_more": len(rows) == limit,
        }

    @app.get("/api/v1/module/references")
    def query_references(
        resource: str = Query(max_length=240),
        direction: Literal["incoming", "outgoing"] = "outgoing",
        after: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        module=Depends(require_module),
    ):
        return query(resource, direction, after, limit, module)

    @app.get("/api/v1/references")
    def owner_references(
        resource: str = Query(max_length=240),
        direction: Literal["incoming", "outgoing"] = "outgoing",
        after: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        owner=Depends(require_owner),
    ):
        return query(resource, direction, after, limit)

    @app.post("/api/v1/module/resources/resolve")
    def resolve_resource(body: ResolveRequest, module=Depends(require_module)):
        require_cap(module, "references.resolve")
        identity = parsed(body.resource)
        if not permitted(module, body.resource, "resolve"):
            raise HTTPException(403, "Resource type is outside the granted resolve scope")
        base = {"resource": body.resource, "identity": identity}
        with db.connect() as conn:
            row = conn.execute("SELECT * FROM modules WHERE id=?", (identity["module"],)).fetchone()
        if not row:
            return {**base, "availability": "module_uninstalled"}
        if row["state"] != "enabled":
            return {
                **base,
                "availability": "module_disabled"
                if row["state"] == "disabled"
                else "temporarily_unavailable",
            }
        types = json.loads(row["manifest"]).get("resources", [])
        if not any(r["type"] == identity["type"] and r["resolvable"] for r in types):
            return {**base, "availability": "not_resolvable"}
        if not row["resolver_key"]:
            return {**base, "availability": "temporarily_unavailable"}
        url = runtime.target(row["id"], row["port"]) + "/empyrean/v1/resources/resolve"
        try:
            with httpx.Client(
                transport=transport, timeout=5, follow_redirects=False, trust_env=False
            ) as client:
                with client.stream(
                    "POST",
                    url,
                    json={"resource": body.resource, "requester": module["id"]},
                    headers={"X-Nexus-Resolver-Key": row["resolver_key"]},
                ) as response:
                    if response.status_code in {403, 404, 410}:
                        return {
                            **base,
                            "availability": {403: "forbidden", 404: "not_found", 410: "deleted"}[
                                response.status_code
                            ],
                        }
                    if response.status_code != 200:
                        return {**base, "availability": "temporarily_unavailable"}
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > 4096:
                            raise ValueError("Oversized resolver response")
                    value = Representation.model_validate_json(data)
                    if value.resource != body.resource or (
                        value.open_path and value.open_path.startswith("//")
                    ):
                        raise ValueError("Invalid resolver identity or open path")
                    if len(json.dumps(value.representation).encode()) > 2048:
                        raise ValueError("Oversized representation")
        except (httpx.HTTPError, ValueError, ValidationError):
            return {**base, "availability": "temporarily_unavailable"}
        return {
            **base,
            "availability": "available",
            "label": value.label,
            "representation": value.representation,
            "open": {"route": f"/app/modules/{row['id']}", "module_path": value.open_path}
            if value.open_path
            else None,
        }
