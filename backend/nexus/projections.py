"""Projection queries (0.1.5): forward scope-granted queries to the owning module.

Nexus never stores, caches, indexes or interprets projected items. Item meaning is an
ecosystem contract (architecture `concepts/projections.md`); Nexus bounds the envelope."""

import json

import httpx
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

NAME = r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
MAX_QUERY = 4096
MAX_RESPONSE = 1024 * 1024
MAX_ITEMS = 500


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectionQuery(Strict):
    module: str = Field(pattern=NAME, max_length=48)
    projection: str = Field(pattern=NAME, max_length=48)
    query: dict = Field(default_factory=dict)
    cursor: str | None = Field(default=None, min_length=1, max_length=200)


class ProjectionPage(BaseModel):
    # Items are opaque to Nexus; only the envelope is checked.
    items: list[dict] = Field(max_length=MAX_ITEMS)
    next_cursor: str | None = Field(default=None, min_length=1, max_length=200)


def granted(module, target, projection):
    declared = module["manifest"].get("projections") or {}
    return {"module": target, "projection": projection} in declared.get("read", [])


def add_projection_routes(app, db, require_module, runtime, transport):
    @app.post("/api/v1/module/projections/query")
    def query_projection(body: ProjectionQuery, module=Depends(require_module)):
        if "projections.read" not in module["manifest"]["capabilities"]:
            raise HTTPException(403, "Capability was not granted: projections.read")
        if not granted(module, body.module, body.projection):
            raise HTTPException(403, "Projection is outside the granted read scope")
        if len(json.dumps(body.query).encode()) > MAX_QUERY:
            raise HTTPException(422, "Projection query exceeds 4 KiB")
        base = {"module": body.module, "projection": body.projection}
        with db.connect() as conn:
            row = conn.execute("SELECT * FROM modules WHERE id=?", (body.module,)).fetchone()
        if not row:
            return {**base, "availability": "module_uninstalled"}
        if row["state"] != "enabled":
            return {
                **base,
                "availability": "module_disabled"
                if row["state"] == "disabled"
                else "temporarily_unavailable",
            }
        provides = (json.loads(row["manifest"]).get("projections") or {}).get("provides", [])
        if body.projection not in provides:
            return {**base, "availability": "not_provided"}
        if not row["resolver_key"]:
            return {**base, "availability": "temporarily_unavailable"}
        url = runtime.target(row["id"], row["port"]) + f"/empyrean/v1/projections/{body.projection}"
        try:
            with httpx.Client(
                transport=transport, timeout=5, follow_redirects=False, trust_env=False
            ) as client:
                with client.stream(
                    "POST",
                    url,
                    json={"requester": module["id"], "query": body.query, "cursor": body.cursor},
                    headers={"X-Nexus-Resolver-Key": row["resolver_key"]},
                ) as response:
                    if response.status_code == 403:
                        return {**base, "availability": "forbidden"}
                    if response.status_code != 200:
                        return {**base, "availability": "temporarily_unavailable"}
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > MAX_RESPONSE:
                            raise ValueError("Oversized projection response")
                    page = ProjectionPage.model_validate_json(data)
        except (httpx.HTTPError, ValueError, ValidationError):
            return {**base, "availability": "temporarily_unavailable"}
        return {
            **base,
            "availability": "available",
            "items": page.items,
            "next_cursor": page.next_cursor,
        }
