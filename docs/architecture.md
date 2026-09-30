# Architecture

## Scope and boundaries

Nexus owns platform metadata, not module domain data. V1 proves a single owner can install and operate a separate container without editing Nexus. Domain entities must never be added merely to accommodate one module. Meridian could consume identity, event and routing contracts without Nexus knowing what a person is; richer persistence grants and UI hosting belong to subsequent protocol revisions.

## Repository map

| Path | Responsibility |
| --- | --- |
| `backend/nexus/app.py` | Versioned HTTP routes, sessions, lifecycle coordination and gateway |
| `backend/nexus/db.py` | SQLite connection handling and numbered transactional migrations |
| `backend/nexus/protocol.py` | Manifest semantics and compatibility |
| `backend/nexus/runtime.py` | Private broker client and runtime target naming |
| `backend/broker/app.py` | Fixed-policy Docker operations |
| `frontend/` | Static first-run, dashboard and management interface |
| `protocol/` | Machine-readable, versioned module schema |
| `examples/example-module/` | Independently running reference module |
| `deploy/`, `compose.yaml` | Container builds and topology |
| `tests/`, `scripts/docker_smoke.py` | Contract/security checks and real Docker integration |
| `docs/adr/` | Significant decisions and tradeoffs |

## Control and data paths

Nexus is the only host-published service. The lifecycle broker has no network interface: Nexus reaches its Unix socket through a dedicated shared volume. The broker uses Docker's Unix socket to create bounded, nonprivileged module containers. Each module gets its own internal bridge network; Nexus joins it as `nexus`. The broker and other modules are not members. A stable module DNS alias supplies the route target; arbitrary manifest hosts are not accepted.

Nexus process identity (UID 10001) controls the broker directory. This is a root-equivalent trust boundary, despite narrower requests. A compromise of Nexus still threatens the lifecycle channel. V1 does not pretend to make the broker an independently hardened sandbox.

Owner sessions terminate at Nexus. Module bearer tokens authenticate only `/api/v1/module/*`; these tokens do not grant owner access. Browser cookies and credentials are never forwarded to modules. Module HTML is returned under an opaque browser sandbox with no same-origin, network, form or top-navigation permissions.

## Persistence and migrations

SQLite lives in `/data/nexus.sqlite3` with WAL, foreign keys and a busy timeout. `PRAGMA user_version` selects an ordered, append-only list of transactional migrations; newer databases fail closed on attempted downgrade. The deployment runs one Uvicorn worker. Lifecycle locking and rate limiting are process-local, deliberately incompatible with an unplanned multi-worker deployment.

Users have UUIDs; sessions and module ownership reference them. This is migration preparation, not multi-user authorization. Events and notifications are installation-scoped. Future multi-user work must add visibility/tenant authorization to every contract before exposing another account.

Sessions and module tokens are hashed in the database. Runtime module tokens necessarily exist in their own Docker environment and are visible to host Docker administrators. A module never receives another module's token or an owner session.

## Lifecycle consistency

Install validates and registers a disabled module; it reserves the unique ID and port without downloading or running code. Enabling creates a new token, enters `enabling`, invokes the broker and commits `enabled` only after success. API authentication is unavailable while pending. Disable revokes access before stopping/removing the container and its network. Uninstall releases the registration only after runtime cleanup succeeds. Neither disable nor uninstall deletes a module's retained data volume, shared blobs or references.

The DB and Docker are not one transaction. Requested/completed/failed audit records and explicit transitional/error states expose this. Failed operations retain registration and port ownership and can be retried. After a crash, pending operations become error with revoked tokens. Retry disable/uninstall to clean possible remnants. On restart, enabled modules whose declared Nexus range excludes the running version have their credentials revoked and become error with an `incompatible` health state; remaining enabled containers are inspected and the gateway rejoins their networks; missing/unavailable containers become error. Containers can temporarily remain alive after an interrupted operation, but revoked credentials and gateway state deny their Nexus access.

## Events, notifications and sources

The SQLite event log retains the latest 10,000 envelopes; subscribers poll using a monotonic sequence. A response scans up to 100 global entries, returning only declared subscriptions and advancing the cursor even if none match. This avoids a quiet subscriber becoming stuck behind unrelated events. Clients must continue until caught up, persist their own cursors, deduplicate by event ID and handle retention gaps. No durable delivery or exactly-once guarantee exists.

Notifications retain 500 records; the UI returns the latest 100. Lifecycle failures and module-generated messages are plain text with a server-stamped source. Audit records are not automatically trimmed and require operator disk monitoring.

V1 source ingestion is manual JSON. The source record is distinct from publisher and release metadata and runtime image identity. A future GitHub/OCI provider should resolve content to the same validated manifest plus independently verified provenance; it must not bypass review or add shell execution. No provider-specific identity is used as a module's primary key.

## UI and compatibility

Neutral surfaces use the supplied palette; gold marks identity and actions. No font/CDN service is contacted. Native controls, labeled forms, visible focus, semantic headings, live error messages and responsive layouts establish the shared foundation. The logo is a replaceable typographic placeholder.

Protocol v1 is strict and rejects unknown fields. Breaking fields require a new protocol version, not silent coercion. Nexus compatibility uses documented PEP 440 ranges. Version/release metadata and an explicit `not_checked` state leave room for opt-in release discovery; no fake up-to-date result is shown.

## Resource interoperability (0.1.1)

The [ecosystem architecture](https://github.com/Aureate-Empyrean/architecture) is authoritative for ownership and cross-module privacy. The additive [Entity References v1 extension](cross-module-references.md) reuses the current registry, capability checks and SQLite/event infrastructure. `backend/nexus/references.py` owns parsing, source-owned writes, privacy-filtered backlinks and authenticated owner resolution. Migration 2 adds the relationship index and private resolver keys, without altering domain ownership or deleting module data.

A relation does not reveal itself to a target owner automatically. It has a creator-controlled reader list, and query scopes alone do not bypass that list. Nexus stores relationships, not domain objects; resolutions are bounded and uncached. Uninstalled/disabled targets remain representable. Existing identities with retained relationships require explicit reuse confirmation on reinstall. Sensitive modules can opt out of indexing entirely; this normal metadata index is not a protected vault.

The shell now routes Overview, Modules, Activity, Settings and module views through the History API. Activity adapts actual audit data; no parallel activity database is created. Notifications use a transient panel, Settings/version are sidebar utilities, and the application switcher is separate from Nexus navigation. See [UI behavior](ui.md).
