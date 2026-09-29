import copy

import pytest
from nexus.protocol import PORTS, validate_manifest


def test_reference_manifest_and_ports(manifest):
    assert validate_manifest(manifest, True) == manifest
    assert all("333" in str(p) and p <= 65535 for p in PORTS)
    assert 12333 not in PORTS


@pytest.mark.parametrize(
    "field,value",
    [
        ("protocol", 2),
        ("id", "../host"),
        ("id", "x;sh"),
        ("trust", "official"),
        ("nexus", ">=99"),
        ("nexus", "broken"),
        ("capabilities", ["host.exec"]),
        ("version", "latest"),
    ],
)
def test_reject_invalid_contract(manifest, field, value):
    manifest[field] = value
    with pytest.raises(ValueError):
        validate_manifest(manifest, True)


@pytest.mark.parametrize(
    "key,value",
    [
        ("privileged", True),
        ("mounts", ["/:/host"]),
        ("command", "sh"),
        ("environment", {"SECRET": "x"}),
        ("port", 12333),
        ("port", 80),
        ("image", "python:latest"),
    ],
)
def test_reject_runtime_privilege_knobs(manifest, key, value):
    manifest["container"][key] = value
    with pytest.raises(ValueError):
        validate_manifest(manifest, True)


def test_digest_and_example_exception(manifest):
    with pytest.raises(ValueError):
        validate_manifest(manifest)
    manifest["container"]["image"] = "ghcr.io/example/module@sha256:" + "a" * 64
    assert validate_manifest(manifest)


def test_event_namespace_and_capability_pairing(manifest):
    bad = copy.deepcopy(manifest)
    bad["events"]["produces"] = ["other-module.secret"]
    with pytest.raises(ValueError):
        validate_manifest(bad, True)
    manifest["capabilities"].remove("events.publish")
    with pytest.raises(ValueError):
        validate_manifest(manifest, True)


@pytest.mark.parametrize(
    "route", ["http://localhost", "//169.254.169.254", "/../admin", "/?x=1", "/%2fadmin"]
)
def test_route_injection_rejected(manifest, route):
    manifest["routes"]["health"] = route
    with pytest.raises(ValueError):
        validate_manifest(manifest, True)
