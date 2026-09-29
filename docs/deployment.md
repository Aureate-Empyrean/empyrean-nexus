# Deployment

## Local first run

Use Linux Docker Engine with the Compose plugin. The operator must already have permission to access the daemon. The supplied topology assumes `/var/run/docker.sock`; rootless/custom daemon deployments need an explicitly adapted socket mount and are not yet verified.

```sh
cp .env.example .env
docker compose up -d --build
docker compose exec nexus cat /data/setup-token
```

Visit http://localhost:12333, supply the claim token, choose an installation name and create a unique owner username/passphrase. The token is sensitive; do not paste it in issue reports. It is generated inside the data volume and deleted after successful setup. Existing installations present login instead. Do not delete the data volume to reset a forgotten password; that destroys installation metadata.

After the initial build, `docker compose up -d` is sufficient. There are no mandatory external services. Dependencies/base images must be available for building; remote module images require access from the Docker daemon when first enabled. Module containers themselves do not receive external network access.

## Reference module

```sh
docker compose --profile example build example
```

This builds only the reference image. Do not run it with `docker compose --profile example up`; Nexus's broker manages the actual container. Use the dashboard's manifest review/install/enable flow. The default `.env` permits only this exact local tag as a development exception. For other modules use immutable digest image references.

The expected round trip is described in [README](../README.md). Disable stops and removes the container/network; uninstall also removes registration and releases the port. The reference has no persistent data. Do not use protocol v1 for modules requiring durable storage.

## Host binding and TLS

Only Nexus publishes a port. Default: `127.0.0.1:12333`. Modules and broker publish none. For remote access, place your chosen TLS reverse proxy in front of Nexus and set the external origin exactly, for example:

```dotenv
NEXUS_PUBLIC_ORIGIN=https://nexus.example.org
NEXUS_BIND=127.0.0.1
NEXUS_PORT=12333
```

A host reverse proxy should forward the entire origin (including `/modules/`), preserve paths and support normal HTTP methods. No per-module rules are needed. Terminate HTTPS at the proxy; route to `127.0.0.1:12333`. A containerized proxy requires intentional network/bind configuration; its localhost is not the host localhost. Restrict untrusted access to the raw HTTP listener with host firewall rules. Do not use a subpath deployment for Nexus v1.

Nexus does not trust forwarded headers. `NEXUS_PUBLIC_ORIGIN` determines Origin checks and Secure cookie policy. Loopback names (`localhost`, `127.0.0.1`, `[::1]`) are interchangeable at the configured port. Other addresses must be listed in `NEXUS_ALLOWED_ORIGINS`; unlisted origins still reject browser mutations. Do not set HTTPS origin while testing through plain HTTP: Secure cookies will not work. The default HTTP/loopback setup is for the local host, not a production TLS substitute.

## State and recovery

Compose volumes `nexus_nexus-data` and `nexus_broker-control` hold metadata and a private runtime socket. `NEXUS_INSTALLATION` changes the Compose project/resource namespace. Keep it stable across upgrades; changing it starts a different installation and does not migrate module resources.

Managed module containers and networks are deliberately created outside Compose's service list. `docker compose down` removes Nexus/broker but does **not** stop enabled modules. Disable modules in the dashboard before taking the whole installation offline. On `up`, Nexus reconciles existing enabled containers and rejoins networks. Never use `down -v` on an installation you want to keep.

After failed/interrupted lifecycle work, a module remains registered in error. Retry Disable or Uninstall to remove runtime remnants, then enable/install again as needed. The token is revoked during failures; registration and port ownership are retained until cleanup succeeds. Docker image layers are not deleted by uninstall because other installations may use them; use normal operator Docker image maintenance when appropriate.

## Offline backup

There is no backup scheduler or restore UI. Settings' JSON export is useful for portability but deliberately excludes authentication secrets and is not directly restorable.

For a consistent full Nexus backup:

1. Disable modules, then stop Nexus and broker with `docker compose stop`.
2. Copy the complete Nexus data volume using your normal trusted Docker volume-backup tooling. Include the database and any WAL/SHM files together; never copy just a live SQLite file. Record the application version, configuration and module manifests/image digests alongside the backup.
3. Protect the backup: it contains password hashes and private metadata. Do not publish `.env` or volume contents.
4. Restart with `docker compose up -d --wait`.

To restore, stop the same installation, restore the full data volume into an empty replacement volume with UID/GID 10001 and private file permissions, and start the same application version first. Test this procedure on a separate host before relying on backups. After restoring older metadata, inspect and reconcile module state carefully; runtime containers are not part of the database backup. No module-domain backups are supported by this reference protocol.

## Updates and operational checks

No automatic update discovery or migration rollback exists. Back up first, review release/source changes and migrations, rebuild, then `docker compose up -d --build --wait`. SQLite migrations run at startup; attempting to run older code against a newer schema fails rather than guessing.

```sh
docker compose ps
docker compose logs --tail 100 nexus broker
```

`/healthz` is minimal public liveness. Dashboard health covers Nexus API/DB; module health is checked explicitly. Lifecycle failures produce notifications. Monitor host disk because audit history grows over time. Keep Docker and the host kernel updated independently of Nexus.

On SELinux hosts, do not blindly relabel the system Docker socket or disable SELinux globally. Diagnose actual denials and use an operator-reviewed policy for the broker. The trusted broker alone uses `label:disable` so it can access the daemon socket on SELinux hosts. This does not disable host SELinux or change Nexus/module labels, but it removes SELinux confinement from this already root-equivalent controller. For stricter hosts, replace this documented broker-only exception with an audited custom policy.

## Access from the local network

Set the following in `.env`, substituting the server's actual LAN IP:

```dotenv
NEXUS_BIND=0.0.0.0
NEXUS_PORT=12333
NEXUS_PUBLIC_ORIGIN=http://localhost:12333
NEXUS_ALLOWED_ORIGINS=http://192.168.100.32:12333
```

Apply with `docker compose up -d --build --wait`. This exposes the gateway on host interfaces; modules still publish no ports. Both localhost/loopback and the listed LAN address work. Separate multiple allowed origins with commas, and use the same HTTP/HTTPS scheme as the primary origin because it controls Secure cookies. Do not use wildcards or automatically trust the request Host header. Add any other hostname explicitly. Sessions are host-specific, so signing in on one address does not sign you in on another.

Other devices can open `http://192.168.100.32:12333` if host/network firewall rules permit it. Plain HTTP on the LAN is unencrypted; use the HTTPS reverse-proxy configuration above when transporting sensitive data. No firewall is disabled by this configuration.

## Upgrading the initial foundation to 0.1.1

Migration 2 adds the reference index and per-module resolver credentials; it preserves users, sessions, settings and existing module registrations. Existing modules are not silently granted reference capabilities or rewritten to a newer manifest. To try the updated disposable reference module, build its 0.1.1 image, uninstall the old reference registration if present, then review/install the new manifest. Never use this procedure as an assumed data-preserving update path for future persistent modules.

UI routes now use `/app/overview`, `/app/modules`, `/app/activity`, `/app/settings` and `/app/modules/<id>`. Your proxy must forward `/app/*` and static `/assets/*` to Nexus unchanged; Nexus serves the SPA fallback for application routes itself.
