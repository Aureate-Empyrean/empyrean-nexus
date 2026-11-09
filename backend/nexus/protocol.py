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
    "network.egress",
    "projections.read",
}
EXAMPLE_IMAGES = {"empyrean-example:0.1.0", "empyrean-example:0.1.1", "empyrean-example:0.1.2"}
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
        if not (allow_example and image in EXAMPLE_IMAGES):
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
        if refs["version"] == 2 and not excludes(manifest, "0.1.2"):
            raise ValueError("Entity References v2 requires a Nexus range excluding 0.1.2")
        if refs.get("enumerate"):
            if refs["version"] != 2:
                raise ValueError("Outgoing-reference enumeration requires references.version=2")
            if "references.create" not in caps:
                raise ValueError("Outgoing-reference enumeration requires references.create")
    projections = manifest.get("projections")
    if projections is not None or "projections.read" in caps:
        if projections is None:
            raise ValueError("projections.read requires a projections declaration")
        if projections["read"] and "projections.read" not in caps:
            raise ValueError("Projection read scopes require projections.read")
        if len(set(projections["provides"])) != len(projections["provides"]):
            raise ValueError("Provided projections must be unique")
        if not excludes(manifest, "0.1.4"):
            raise ValueError("Projections require a Nexus range excluding 0.1.4")
    if "network.egress" in caps and not excludes(manifest, "0.1.4"):
        raise ValueError("network.egress requires a Nexus range excluding 0.1.4")
    if "backup" in manifest:
        if "storage.data" not in caps:
            raise ValueError("The backup contract applies to modules with storage.data")
        if not excludes(manifest, "0.1.2"):
            raise ValueError("The backup contract requires a Nexus range excluding 0.1.2")
        if manifest["backup"].get("objects") and not excludes(manifest, "0.1.13"):
            raise ValueError("Backup objects require a Nexus range excluding 0.1.13")
    if "runtime" in manifest and not excludes(manifest, "0.1.13"):
        raise ValueError("A runtime memory grant requires a Nexus range excluding 0.1.13")
    if "icon" in manifest and not excludes(manifest, "0.1.7"):
        raise ValueError("An application icon requires a Nexus range excluding 0.1.7")
    return manifest


def excludes(manifest: dict, version: str) -> bool:
    """True when the manifest's range rejects this Nexus release and every earlier one."""
    spec = SpecifierSet(manifest["nexus"])
    return not any(
        Version(old) in spec
        for old in (f"0.1.{n}" for n in range(14))
        if Version(old) <= Version(version)
    )


def uses_uuid_identity(manifest: dict) -> bool:
    """Entity References v2: every resource ID this module exposes is a canonical UUID."""
    refs = manifest.get("references") or {}
    return refs.get("version") == 2
