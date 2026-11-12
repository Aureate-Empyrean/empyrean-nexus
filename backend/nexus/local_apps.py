"""Private local applications in the launcher (development only; off unless configured).

A development machine can list applications that run beside Nexus but are not Nexus modules,
such as the private Zeus control panel. `NEXUS_LOCAL_APPS` names a JSON file (mounted
read-only) with up to eight entries:

    [{"id": "zeus-local", "name": "Zeus", "description": "...",
      "url": "http://127.0.0.1:65333/", "icon": "zeus.svg"}]

Each URL must be a loopback address, so a launcher entry can never point to another machine.
The icon is a file next to the JSON file. Nexus validates it exactly like a module icon and
serves its own copy to the owner, so the browser never loads an image from elsewhere. Without
the variable (every server installation, including Exodus) the list is empty. A configured but
invalid file stops Nexus with a clear error instead of being silently ignored.
"""

import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, Response

from nexus.icons import HEADERS, MODULE_ID, TYPES, IconError, validate

ENV = "NEXUS_LOCAL_APPS"
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
MAX_APPS = 8


class LocalAppError(ValueError):
    pass


def load_local_apps(path: str | None) -> list[dict]:
    if not path:
        return []
    source = Path(path)
    try:
        entries = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LocalAppError(f"{ENV}: cannot read {source}") from exc
    if not isinstance(entries, list) or not 0 < len(entries) <= MAX_APPS:
        raise LocalAppError(f"{ENV}: expected a list of 1 to {MAX_APPS} applications")
    apps, seen = [], set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) - {"id", "name", "description", "url", "icon"}:
            raise LocalAppError(f"{ENV}: each application has only id, name, description, url, icon")
        app_id = entry.get("id")
        if not isinstance(app_id, str) or not MODULE_ID.fullmatch(app_id) or app_id in seen:
            raise LocalAppError(f"{ENV}: invalid or duplicate application id")
        seen.add(app_id)
        name, description = entry.get("name"), entry.get("description", "")
        if not isinstance(name, str) or not 0 < len(name.strip()) <= 40:
            raise LocalAppError(f"{ENV}: {app_id} needs a name of at most 40 characters")
        if not isinstance(description, str) or len(description) > 120:
            raise LocalAppError(f"{ENV}: {app_id} description is longer than 120 characters")
        url = urlsplit(entry.get("url") or "")
        try:
            port = url.port
        except ValueError:
            port = None
        if (
            url.scheme not in {"http", "https"}
            or url.hostname not in LOOPBACK
            or not port
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise LocalAppError(f"{ENV}: {app_id} must open a loopback address with a port")
        icon = entry.get("icon")
        if not isinstance(icon, str) or not re.fullmatch(r"[A-Za-z0-9._-]+\.(svg|png|webp)", icon):
            raise LocalAppError(f"{ENV}: {app_id} icon must be a file next to {source.name}")
        try:
            content = (source.parent / icon).read_bytes()
            media_type = validate(content, TYPES[icon.rsplit(".", 1)[1].lower()], icon)
        except (OSError, IconError) as exc:
            raise LocalAppError(f"{ENV}: {app_id} icon is missing or not a valid icon") from exc
        host = f"[{url.hostname}]" if ":" in url.hostname else url.hostname
        apps.append(
            {
                "id": app_id,
                "name": name.strip(),
                "description": description,
                "url": url.geturl(),
                "label": f"{host}:{port}",
                "media_type": media_type,
                "content": content,
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    return apps


def add_local_app_routes(app, require_owner):
    apps = {a["id"]: a for a in load_local_apps(os.getenv(ENV))}
    app.state.local_apps = apps

    @app.get("/api/v1/local-apps")
    def local_apps(owner=Depends(require_owner)):
        return {
            "apps": [
                {k: a[k] for k in ("id", "name", "description", "url", "label")}
                | {"icon_sha256": a["sha256"]}
                for a in apps.values()
            ]
        }

    @app.get("/api/v1/local-apps/{app_id}/icon")
    def local_app_icon(app_id: str, request: Request, owner=Depends(require_owner)):
        entry = apps.get(app_id)
        if not entry:
            raise HTTPException(404, "No such local application")
        etag = f'"{entry["sha256"]}"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={**HEADERS, "ETag": etag})
        return Response(
            entry["content"], media_type=entry["media_type"], headers={**HEADERS, "ETag": etag}
        )
