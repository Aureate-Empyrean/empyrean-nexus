"""Module application icons (manifest `icon`, Nexus 0.1.8): a validated copy owned by Nexus.

Nexus fetches the icon a module declares from that module (over its private port, as the
gateway does), validates it, and keeps the last valid copy in its own data volume. The copy is
served to the owner from `/api/v1/modules/<id>/icon`, so a module's icon survives the module
being stopped or unreachable and Nexus restarting. It is refreshed when the manifest's icon
path, version or image changes; a refresh that fails keeps the previous copy. Uninstalling a
module deletes its copy. Being offline never does.
"""

import hashlib
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from fastapi import Depends, HTTPException, Request, Response

MAX_BYTES = 64 * 1024
TYPES = {"svg": "image/svg+xml", "png": "image/png", "webp": "image/webp"}
# After a failed fetch, wait before asking the module again (each attempt can take 5 s).
RETRY_SECONDS = 60
MODULE_ID = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
SVG = "{http://www.w3.org/2000/svg}"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
# Static drawing only: no script, foreignObject, style sheets, images, links or animation.
ELEMENTS = {
    "svg", "g", "defs", "title", "desc", "path", "circle", "ellipse", "rect", "line",
    "polyline", "polygon", "linearGradient", "radialGradient", "stop", "clipPath", "mask",
    "symbol", "use",
}  # fmt: skip
# Served with the icon: an SVG opened directly is an inert, sandboxed document.
HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    "Cache-Control": "private, no-cache",
    "Content-Disposition": "inline",
}


class IconError(ValueError):
    pass


def validate(content: bytes, content_type: str, path: str) -> str:
    """Return the media type of a valid icon, or raise IconError."""
    kind = path.rsplit(".", 1)[-1].lower()
    media_type = TYPES.get(kind)
    if not media_type or content_type.split(";")[0].strip().lower() != media_type:
        raise IconError("The icon's content type does not match its declared format")
    if not content or len(content) > MAX_BYTES:
        raise IconError("The icon is empty or larger than 64 KiB")
    if kind == "png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise IconError("Not a PNG image")
    if kind == "webp" and not (content[:4] == b"RIFF" and content[8:12] == b"WEBP"):
        raise IconError("Not a WebP image")
    if kind == "svg":
        validate_svg(content)
    return media_type


def validate_svg(content: bytes) -> None:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IconError("SVG must be UTF-8") from exc
    # No DTDs or entities (expansion attacks) and no style sheet processing instructions.
    if re.search(r"<!DOCTYPE|<!ENTITY|<\?xml-stylesheet", text, re.IGNORECASE):
        raise IconError("SVG must not contain a DTD, entities or style sheet instructions")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise IconError("SVG is not well-formed") from exc
    if root.tag != SVG + "svg":
        raise IconError("The root element must be an SVG element")
    for element in root.iter():
        if not element.tag.startswith(SVG) or element.tag[len(SVG) :] not in ELEMENTS:
            raise IconError("SVG contains an element that is not a static drawing")
        for name, value in element.attrib.items():
            local = name.rsplit("}", 1)[-1].lower()
            lowered = re.sub(r"\s+", "", value).lower()
            if local.startswith("on"):
                raise IconError("SVG must not contain event handlers")
            if (local == "href" or name == XLINK_HREF) and not value.startswith("#"):
                raise IconError("SVG may reference only its own elements")
            if "javascript:" in lowered or "data:" in lowered or "@import" in lowered:
                raise IconError("SVG contains an active or external reference")
            if re.search(r"url\((?!['\"]?#)", lowered):
                raise IconError("SVG may reference only its own elements")


class IconCache:
    """One validated icon per module, stored as `<id>.icon` plus `<id>.json` metadata."""

    def __init__(self, data: Path):
        self.directory = data / "module-icons"
        self.failed = {}

    def _paths(self, module_id: str):
        if not MODULE_ID.fullmatch(module_id):
            raise IconError("Invalid module identity")
        return self.directory / f"{module_id}.icon", self.directory / f"{module_id}.json"

    def load(self, module_id: str):
        content_path, meta_path = self._paths(module_id)
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            content = content_path.read_bytes()
        except (OSError, ValueError):
            return None
        # The pair must belong to this module and match: never serve another module's icon.
        if meta.get("module") != module_id or hashlib.sha256(content).hexdigest() != meta.get(
            "sha256"
        ):
            return None
        return meta, content

    def store(self, module_id: str, key: dict, media_type: str, content: bytes):
        content_path, meta_path = self._paths(module_id)
        self.directory.mkdir(parents=True, exist_ok=True)
        meta = {
            "module": module_id,
            **key,
            "media_type": media_type,
            "sha256": hashlib.sha256(content).hexdigest(),
            "fetched_at": int(time.time()),
        }
        for path, payload in ((content_path, content), (meta_path, json.dumps(meta).encode())):
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_bytes(payload)
            os.replace(temporary, path)
        self.failed.pop(module_id, None)
        return meta, content

    def forget(self, module_id: str):
        self.failed.pop(module_id, None)
        for path in self._paths(module_id):
            path.unlink(missing_ok=True)


def icon_key(manifest: dict) -> dict:
    # An update with a new image may change the icon even when the version does not.
    return {
        "icon": manifest["icon"],
        "version": manifest["version"],
        "image": manifest["container"]["image"],
    }


def add_icon_routes(app, data: Path, get_module, upstream, require_owner):
    cache = IconCache(data)
    app.state.icons = cache

    def refresh(row, manifest, key):
        """Fetch and store the module's icon; keep the previous copy if anything fails."""
        failed = cache.failed.get(row["id"])
        if failed and failed[0] == key and time.monotonic() - failed[1] < RETRY_SECONDS:
            return None
        try:
            code, content_type, content = upstream(row, "GET", manifest["icon"])
            if code != 200:
                raise IconError(f"The module answered {code}")
            media_type = validate(content, content_type, manifest["icon"])
        except (HTTPException, IconError):
            cache.failed[row["id"]] = (key, time.monotonic())
            return None
        return cache.store(row["id"], key, media_type, content)

    @app.get("/api/v1/modules/{module_id}/icon")
    def module_icon(module_id: str, request: Request, owner=Depends(require_owner)):
        row = get_module(module_id)
        manifest = json.loads(row["manifest"])
        if not manifest.get("icon"):
            raise HTTPException(404, "This module declares no icon")
        key = icon_key(manifest)
        cached = cache.load(module_id)
        current = cached and all(cached[0].get(k) == v for k, v in key.items())
        if not current and row["state"] == "enabled":
            cached = refresh(row, manifest, key) or cached
        if not cached:
            raise HTTPException(404, "No icon is available for this module yet")
        meta, content = cached
        etag = f'"{meta["sha256"]}"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={**HEADERS, "ETag": etag})
        return Response(content, media_type=meta["media_type"], headers={**HEADERS, "ETag": etag})

    return cache
