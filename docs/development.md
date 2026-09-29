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

## Contributing structure

Keep module-specific code in independent examples/modules, not in Nexus routes. Add new metadata migrations at the end of `MIGRATIONS`; do not edit an already released migration. Test migration idempotence and reject newer schema versions. Protocol additions need a compatibility decision and schema/semantic/security tests.

The frontend uses platform APIs with no bundler or runtime packages. Node tests exercise routing and motion; DOM tests use a development-only DOM implementation. Use `textContent` or the existing escaping function for untrusted metadata, and keep security headers enforceable without inline Nexus scripts/styles. Module HTML has a different, stricter sandbox policy; never copy its allowances into the parent.

One Uvicorn worker is an architectural constraint: lifecycle locking and rate limits are process-local. Do not add `--workers` without redesigning those mechanisms. Keep credentials out of command arguments/logs and avoid broad Docker SDK wrappers.

## Visual checks

Verify setup, sign-in, empty dashboard, manifest review/grant, enabled module, API explorer, notifications and settings in a real browser. Check keyboard focus, narrow screens, escaped hostile strings, failure messages and no console/CSP errors. This is a manual QA checklist, not a claim that every browser has been tested. Consult the implementation checkpoint for checks actually completed in this build.
