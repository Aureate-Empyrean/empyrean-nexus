import copy

import pytest
from nexus.protocol import validate_manifest


def test_icon_is_a_module_relative_image_path(manifest):
    declared = copy.deepcopy(manifest)
    declared.update(nexus=">=0.1.8,<0.2.0", icon="/icon.svg")
    assert validate_manifest(copy.deepcopy(declared), True)["icon"] == "/icon.svg"
    for icon in ("/static/app-icon.png", "/assets/tile.webp"):
        assert validate_manifest(dict(copy.deepcopy(declared), icon=icon), True)
    for icon in (
        "https://example.com/icon.svg",
        "//example.com/icon.svg",
        "/../icon.svg",
        "icon.svg",
        "/icon.svg?x=1",
        "/icon.gif",
        "/icon",
    ):
        with pytest.raises(ValueError):
            validate_manifest(dict(copy.deepcopy(declared), icon=icon), True)


def test_icon_requires_a_range_excluding_older_nexus(manifest):
    older = copy.deepcopy(manifest)
    older.update(nexus=">=0.1.5,<0.2.0", icon="/icon.svg")
    with pytest.raises(ValueError, match="excluding 0.1.7"):
        validate_manifest(older, True)
    without = copy.deepcopy(manifest)
    without.update(nexus=">=0.1.5,<0.2.0")
    without.pop("icon", None)
    assert validate_manifest(without, True)
