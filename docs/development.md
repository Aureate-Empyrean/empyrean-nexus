# Development

## Toolchain

Python >=3.12 (Docker/CI target 3.13), Node for the JavaScript syntax check, and Linux Docker/Compose for runtime integration. Runtime and development dependency snapshots are in `requirements.lock` and `requirements-dev.lock`; `pyproject.toml` declares intentional direct dependency ranges. Update locks together after tests, rather than mixing new transient versions into deployments.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.lock
.venv/bin/ruff check backend examples tests scripts deploy
.venv/bin/ruff format --check backend examples tests scripts deploy
.venv/bin/python -m pytest -q
npm ci
npm run check
npm test
```

Native UI/API development:

```sh
NEXUS_ALLOW_EXAMPLE=1 PYTHONPATH=backend .venv/bin/uvicorn nexus.app:create_app --factory --host 127.0.0.1 --port 12333 --no-proxy-headers
```

Read `.data/setup-token` locally, then initialize at http://localhost:12333. Native mode persists `.data/nexus.sqlite3` (ignored by Git). Never commit `.data` or passwords. Without a broker, validation/registration work but Enable returns an explicit runtime error. Use Compose for real lifecycle testing, not a fake success runtime in production.

## Real integration test

```sh
docker compose --profile example build
.venv/bin/python scripts/docker_smoke.py
```

The script creates a unique `nexus-test-*` Compose project on loopback port 12334, creates random temporary credentials, drives public APIs, enables the real reference container, checks gateway/API/event/notification behavior, recreates Nexus, then disables/uninstalls the module. It removes only its own test stack/volumes. `NEXUS_TEST_PORT` changes its host port if occupied. No administrator credentials are printed.

Unit/contract tests inject an in-memory runtime stand-in and HTTP transport for deterministic failures. They do not substitute for the Docker smoke test. CI runs both. ASGI TestClient uses local event-loop communication; environments that prohibit local socket operations can hang even without outgoing network calls. Run in an environment permitting local test execution.

## Navigation History pilot

The shared SDK and Mnemosyne adapter are locally implemented, not production
deployment. Read [the current protocol/adoption guide](navigation-history.md)
before changing navigation; its flag defaults off and is not forwarded by the
checked-in Compose file. A native Nexus process without a broker still cannot
enable real containers merely by setting the flag.

The opt-in `tests/test_navigation_browser.py` starts real Nexus, Mnemosyne and
unchanged Chronos HTTP apps against disposable SQLite data. Only the container
broker is replaced by `tests/navigation_pilot_runtime.py`'s loopback process
launcher. Authentication, gateway keys, module HTML/CSP and domain APIs remain
real. This test is distinct from both the old synthetic fixture and Docker smoke;
never use the process launcher in production.

Requirements: sibling Mnemosyne/Chronos checkouts, each application's Python
dependencies, installed Chrome and Python Playwright. The launcher uses a
module's `.venv` when present, or the test Python otherwise. Windows also needs
importable timezone data and UTF-8 mode. With those dependencies installed:

```powershell
# From empyrean-nexus; use an environment with Playwright and module dependencies:
$env:NEXUS_BROWSER_TESTS = '1'
.\.venv\Scripts\python.exe -X utf8 -m pytest -q -s tests/test_navigation_browser.py
Remove-Item Env:NEXUS_BROWSER_TESTS
node scripts/sync-navigation.mjs --check
npm test
npm run check
```

The opt-in browser test is skipped in a default backend run. The SDK tests are
included in Nexus `npm test`; Mnemosyne's own `npm test` includes its route codec
and legacy frontend regression suite. The sync script without `--check` writes
the fixed Mnemosyne vendor target; it is not a general adopter installer. Do not
run that mutation during a documentation-only task.

[PILOT.md](proposals/navigation-history/PILOT.md) records the 16 completed Chrome
scenarios, exact recorded tool versions, setup commands and environment-specific
suite failures. These are previous implementation results, not a declaration
that this documentation pass reran the applications. Outstanding browser,
container-lifecycle and failure-mode gates remain explicit.

## Contributing structure

Keep module-specific code in independent examples/modules, not in Nexus routes. Add new metadata migrations at the end of `MIGRATIONS`; do not edit an already released migration. Test migration idempotence and reject newer schema versions. Protocol additions need a compatibility decision and schema/semantic/security tests.

The frontend uses platform APIs with no bundler or runtime packages. Node tests exercise routing and motion; DOM tests use a development-only DOM implementation. Use `textContent` or the existing escaping function for untrusted metadata, and keep security headers enforceable without inline Nexus scripts/styles. Module HTML has a different, stricter sandbox policy; never copy its allowances into the parent.

One Uvicorn worker is an architectural constraint: lifecycle locking and rate limits are process-local. Do not add `--workers` without redesigning those mechanisms. Keep credentials out of command arguments/logs and avoid broad Docker SDK wrappers.

## Visual checks

Verify setup, sign-in, empty dashboard, manifest review/grant, enabled module, API explorer, notifications and settings in a real browser. Check keyboard focus, narrow screens, escaped hostile strings, failure messages and no console/CSP errors. This is a manual QA checklist, not a claim that every browser has been tested. Consult the implementation checkpoint for checks actually completed in this build.
