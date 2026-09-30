# Empyrean Nexus

**Aureate Empyrean — Open software. Private by design.**

Empyrean Nexus is the small, self-hosted control plane for an open ecosystem of independent applications. It connects modules through local identity, a gateway, explicit capabilities and versioned contracts. Your installation does not depend on an Aureate Empyrean cloud service. No telemetry, external fonts, analytics or background update requests are included.

## Status

**0.1.2 foundation / pre-release.** The reference vertical slice implements first-run setup, owner login, a dashboard, manifest review, registration, container enable/disable/removal, health checks, sandboxed routing, event publication/polling, notifications, private-by-default resource references, owner-authorized resolution, backlinks, real Activity, metadata export and opt-in persistent application infrastructure (full-window sandboxed UI, retained module data volumes, shared blobs). This is an initial implementation, not a security-audited production platform.

Nexus is **not** a people database, media library, location tracker, messaging product or calendar. Meridian, Atlas, Mnemosyne, Argus, Hermes and Chronos are future independent applications; none is implemented here. Nexus has no knowledge of their domain entities.

## Start with Docker

Requires Linux Docker Engine and the Compose plugin, with permission to use Docker. From this repository:

```sh
docker compose up -d --build
docker compose exec nexus cat /data/setup-token
```

Open **http://localhost:12333**. Enter the locally generated claim token and create your owner account. There are no default credentials. Passwords require at least 12 characters and are hashed with Argon2id. The claim token is removed after setup.

The default bind is loopback. For remote access, configure an HTTPS reverse proxy and `NEXUS_PUBLIC_ORIGIN`; see [deployment](docs/deployment.md). Do not expose the initial HTTP installation directly to the Internet.

## Prove the module contract

```sh
docker compose --profile example build example
```

1. In **Modules → Install module**, choose **Load reference manifest**.
2. Review the image, publisher, reserved port and capabilities. Grant them and install disabled.
3. Enable the module, check health, and open it through Nexus.
4. In its API explorer, GET `/info`, POST `/publish`, then GET `/consume`.
5. POST `/reference`, GET `/references` or `/backlinks`, and POST `/resolve` to exercise the sample resource.
6. Observe its notification, disable it, and uninstall it.

The reference imports no Nexus code. Any conforming module can be registered without modifying Nexus. V1 accepts manually supplied JSON manifests, including files downloaded from a repository or release. It never clones or runs repository installation scripts. Apart from the explicit local reference image, images must be pinned by SHA-256 digest. Set `NEXUS_ALLOW_EXAMPLE=0` to disable that development exception.

## Architecture

```text
Browser / optional TLS reverse proxy
                  |
            Nexus :12333
     dashboard + API + gateway ── SQLite volume
           |              |
     Unix socket      private network per module
           |              |
     lifecycle broker    independent module container
           |
       Docker Engine
```

Nexus is a Python/FastAPI modular monolith with a dependency-free browser frontend. The narrow lifecycle broker is a separate trust boundary, not a general Docker API proxy. Only it mounts the Docker socket. Modules run non-root with a read-only filesystem, no host ports, no host mounts, capability dropping and resource limits. The broker is root-equivalent; containers are not perfect sandboxes. Read the [security model](docs/security-model.md) before installing untrusted code.

## Development and verification

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.lock
.venv/bin/ruff check backend examples tests scripts deploy
.venv/bin/ruff format --check backend examples tests scripts deploy
.venv/bin/python -m pytest -q
npm ci
npm test
npm run check
NEXUS_ALLOW_EXAMPLE=1 PYTHONPATH=backend .venv/bin/uvicorn nexus.app:create_app --factory --host 127.0.0.1 --port 12333 --no-proxy-headers
```

Native development can exercise setup, metadata and the UI; real container lifecycle requires the Compose broker. [Development guide](docs/development.md) explains the isolated Docker integration test and repository layout.

## Deliberate boundaries

- One primary owner; user IDs and ownership columns preserve a migration path.
- Persistent module data only through the opt-in `storage.data` volume, which is retained across disable, uninstall and reinstall; uninstall never deletes module data, shared blobs or references.
- Module UI always runs in an opaque-origin sandbox (full-window with `ui.application`); no WebSockets or streaming proxy.
- Events are bounded polling, not durable business workflow messaging.
- Health is checked on demand; no background monitoring scheduler.
- Release URLs and version metadata exist; update discovery and automatic updates do not.
- Manual manifest source only; source providers can be added without changing runtime contracts.
- All manual installations are shown as Community/unreviewed; publisher identity is not authenticated.
- Export is portable JSON, not a restore system. See offline backup instructions.
- No multi-user sharing, permission editor, module dependencies, registry, in-place module updates, signed packages, TLS termination or password recovery UI yet.

## Documentation

- [Cross-module references](docs/cross-module-references.md) and [UI navigation/motion](docs/ui.md)
- [Architecture](docs/architecture.md) and [decisions](docs/adr/0001-foundation.md)
- [Module protocol](docs/module-protocol.md), [JSON Schema](protocol/module-v1.schema.json), [API](docs/api.md)
- [Security model](docs/security-model.md), [security reporting](SECURITY.md)
- [Ports](docs/ports.md), [deployment](docs/deployment.md), [development](docs/development.md)
- [Contribution guide](CONTRIBUTING.md), [branding policy](docs/branding.md)
- [Implementation and verification checkpoint](docs/IMPLEMENTATION_PLAN.md)

## License and community

Copyright © 2026 Aureate Empyrean contributors. Software in this repository is licensed under **AGPL-3.0-or-later**; see [LICENSE](LICENSE). Forking, modifying and redistributing are legitimate. Generally useful improvements are encouraged upstream, without restricting independent forks. Names, logos, visual identity and official status are separate from the software license. A fork must not falsely present itself as an official Aureate Empyrean release.
