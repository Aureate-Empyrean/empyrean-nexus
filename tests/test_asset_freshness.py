"""Frontend updates are picked up on a normal reload: the shell and every asset are no-store.

The asset URLs are not versioned, so this guarantee relies on browsers never storing them.
"""

from pathlib import Path

import pytest

FRONTEND = Path(__file__).parents[1] / "frontend"
ASSETS = sorted(
    p.relative_to(FRONTEND).as_posix()
    for p in FRONTEND.rglob("*")
    if p.is_file() and p.suffix in {".js", ".css", ".html", ".woff2"}
)


def test_every_module_script_is_covered():
    assert {"app.js", "router.js", "motion.js", "navigation-protocol.js"} <= set(ASSETS)


@pytest.mark.parametrize("path", ["/", "/app/overview", *("/assets/" + a for a in ASSETS)])
def test_shell_and_assets_are_never_stored_by_the_browser(env, path):
    client = env[0]
    # Pages are loaded with GET; static assets also answer HEAD (revalidation probes).
    for method in (client.get, client.head) if path.startswith("/assets/") else (client.get,):
        response = method(path)
        assert response.status_code == 200, path
        assert response.headers["cache-control"] == "no-store", path


def test_no_service_worker_can_serve_stale_frontend_code():
    assert not any(
        "serviceWorker" in (FRONTEND / a).read_text(encoding="utf-8")
        for a in ASSETS
        if a.endswith(".js")
    )
