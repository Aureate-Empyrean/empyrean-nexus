"""Protocol v1 is intentionally closed: unknown privilege knobs are rejected."""

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import Version

from nexus import VERSION

ROOT = Path(__file__).resolve().parents[2]
PORTS = tuple(range(13333, 65334, 1000))
CAPABILITIES = {
    "storage.data",
    "blobs.read",
    "blobs.write",
    "ui.application",
    "events.publish",
    "events.subscribe",
    "notifications.publish",
    "references.create",
    "references.read",
    "references.resolve",
}
SCHEMA = json.loads((ROOT / "protocol/module-v1.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def validate_manifest(manifest: dict, allow_example: bool = False) -> dict:
    errors = sorted(VALIDATOR.iter_errors(manifest), key=lambda e: str(e.path))
    if errors:
        raise ValueError(f"{'.'.join(map(str, errors[0].path))}: {errors[0].message}")
    if manifest["id"] == "nexus":
        raise ValueError("The nexus module ID and event namespace are reserved for the platform")
    try:
        if Version(VERSION) not in SpecifierSet(manifest["nexus"]):
            raise ValueError("This module is incompatible with Nexus " + VERSION)
    except InvalidSpecifier as exc:
        raise ValueError("nexus must be a PEP 440 compatibility range") from exc
    image = manifest["container"]["image"]
    if not re.fullmatch(
        r"(?:sha256:[a-f0-9]{64}|[a-z0-9][a-z0-9./:_-]*@sha256:[a-f0-9]{64})", image
    ):
        if not (allow_example and image in {"empyrean-example:0.1.0", "empyrean-example:0.1.1"}):
            raise ValueError("Images must be pinned by sha256 digest")
    caps = set(manifest["capabilities"])
    if caps & {"storage.data", "blobs.read", "blobs.write", "ui.application"} and Version(
        "0.1.1"
    ) in SpecifierSet(manifest["nexus"]):
        raise ValueError("Application infrastructure requires Nexus >=0.1.2")
    events = manifest["events"]
    if events["produces"] and "events.publish" not in caps:
        raise ValueError("Declared producers require events.publish")
    if events["consumes"] and "events.subscribe" not in caps:
        raise ValueError("Declared consumers require events.subscribe")
    if any(not event.startswith(manifest["id"] + ".") for event in events["produces"]):
        raise ValueError("Produced events must use the module ID namespace")
    resources = manifest.get("resources", [])
    if len({r["type"] for r in resources}) != len(resources):
        raise ValueError("Resource types must be unique")
    refs = manifest.get("references")
    if (
        refs is not None
        or "resources" in manifest
        or any(c.startswith("references.") for c in caps)
    ):
        if refs is None:
            raise ValueError("Entity reference features require references.version=1")
        # The extension was introduced in Nexus 0.1.1; older implementations reject these fields.
        if Version("0.1.0") in SpecifierSet(manifest["nexus"]):
            raise ValueError("Entity reference features require a Nexus range excluding 0.1.0")
    if refs:
        for scope in ("read", "resolve"):
            if refs[scope] and "references." + scope not in caps:
                raise ValueError("Reference scopes require their matching capability")
    return manifest
