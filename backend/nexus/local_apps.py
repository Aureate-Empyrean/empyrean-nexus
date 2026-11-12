"""Private local applications in the launcher (development only; off unless configured).

A development machine can list applications that run beside Nexus but are not Nexus modules,
such as the private Zeus control panel. `NEXUS_LOCAL_APPS` names a JSON file (mounted
read-only) with up to eight entries:

    [{"id": "zeus-local", "name": "Zeus", "description": "...",
      "url": "http://127.0.0.1:65333/", "icon": "zeus.svg",
      "health": "/health", "replaces": "zeus"}]

Each URL must be a loopback address, so a launcher entry can never point to another machine.
The icon is a file next to the JSON file. Nexus validates it exactly like a module icon and
serves its own copy to the owner, so the browser never loads an image from elsewhere. Without
the variable (every server installation, including Exodus) the list is empty. A configured but
invalid file stops Nexus with a clear error instead of being silently ignored.

Optional `health` is a path Nexus probes (GET, 2 s, no redirects, cached 15 s) to show the
application's real status; a Nexus that runs in a container reaches the host through
`NEXUS_LOCAL_APPS_PROBE_HOST` (for example host.docker.internal) while sending the configured
loopback address as the Host header. Optional `replaces` names a module this application
supersedes: while that module is not running, user-facing listings show this application
instead. The module itself, its data and its recovery actions in Modules are unchanged.
"""

import hashlib
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import Depends, HTTPException, Request, Response

from nexus.icons import HEADERS, MODULE_ID, TYPES, IconError, validate

ENV = "NEXUS_LOCAL_APPS"
PROBE_HOST_ENV = "NEXUS_LOCAL_APPS_PROBE_HOST"
PROBE_SECONDS = 15
HOSTNAME = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
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
        if not isinstance(entry, dict) or set(entry) - {
            "id",
            "name",
            "description",
            "url",
            "icon",
            "health",
            "replaces",
        }:
            raise LocalAppError(
                f"{ENV}: each application has only id, name, description, url, icon, health, replaces"
            )
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
        health = entry.get("health")
        if health is not None and (
            not isinstance(health, str)
            or not re.fullmatch(r"/[A-Za-z0-9._/-]{0,100}", health)
            or "//" in health
            or ".." in health
        ):
            raise LocalAppError(f"{ENV}: {app_id} health must be a plain path such as /health")
        replaces = entry.get("replaces")
        if replaces is not None and (
            not isinstance(replaces, str) or not MODULE_ID.fullmatch(replaces)
        ):
            raise LocalAppError(f"{ENV}: {app_id} replaces must be a module id")
        host = f"[{url.hostname}]" if ":" in url.hostname else url.hostname
        apps.append(
            {
                "id": app_id,
                "name": name.strip(),
                "description": description,
                "url": url.geturl(),
                "label": f"{host}:{port}",
                "netloc": f"{host}:{port}",
                "scheme": url.scheme,
                "port": port,
                "health": health,
                "replaces": replaces,
                "media_type": media_type,
                "content": content,
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    return apps


def probe_host() -> str | None:
    host = os.getenv(PROBE_HOST_ENV) or None
    if host and not HOSTNAME.fullmatch(host):
        raise LocalAppError(f"{PROBE_HOST_ENV} must be a host name")
    return host


def add_local_app_routes(app, require_owner, transport=None):
    apps = {a["id"]: a for a in load_local_apps(os.getenv(ENV))}
    gateway = probe_host()
    checks = {}
    app.state.local_apps = apps

    def status(entry):
        """The application's own health answer; never a guess from configuration."""
        if not entry["health"]:
            return {"state": "unchecked", "checked_at": None}
        cached = checks.get(entry["id"])
        if cached and time.monotonic() - cached[0] < PROBE_SECONDS:
            return cached[1]
        target = f"{entry['scheme']}://{gateway or entry['netloc']}"
        if gateway:
            target += f":{entry['port']}"
        try:
            with httpx.Client(
                transport=transport, timeout=2, follow_redirects=False, trust_env=False
            ) as client:
                answer = client.get(target + entry["health"], headers={"Host": entry["netloc"]})
            state = "running" if answer.status_code == 200 else "unhealthy"
        except httpx.HTTPError:
            state = "unavailable"
        result = {"state": state, "checked_at": int(time.time())}
        checks[entry["id"]] = (time.monotonic(), result)
        return result

    @app.get("/api/v1/local-apps")
    def local_apps(owner=Depends(require_owner)):
        return {
            "apps": [
                {k: a[k] for k in ("id", "name", "description", "url", "label", "replaces")}
                | {"icon_sha256": a["sha256"], "status": status(a)}
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
