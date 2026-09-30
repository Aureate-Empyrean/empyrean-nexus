# Application infrastructure extension (0.1.2)

Generic opt-in Module Protocol v1 capabilities implement the canonical full
application boundary. A manifest must exclude Nexus 0.1.1 and explicitly grant:

- `ui.application`: full-window opaque-origin sandbox at `/app/modules/<id>`.
  Nexus management chrome disappears. No allow-same-origin, owner cookie, bearer
  token or CSRF value reaches the application. The message bridge checks current
  frame identity, module state, action, method, own API prefix, path and body size.
- `storage.data`: a broker-owned named volume at `/data`, retained across disable,
  uninstall and reinstall. Images create `/data` owned by UID/GID 10001 without a
  Docker VOLUME declaration. Custom mounts, commands and host paths remain forbidden.
- `blobs.write` and `blobs.read`: POST `/api/v1/module/blobs` with `{content:base64}`
  and GET `/api/v1/module/blobs/<sha256>`. Maximum raw file: 1 MiB. Upload grants
  that module read access; knowing a digest does not grant access. Bytes live in
  Nexus shared storage, with module-specific grants. Removing an attachment does
  not delete potentially shared bytes. Garbage collection is not implemented.

Gateway-to-module authentication uses `X-Nexus-Gateway-Key` with that module's
resolver credential. It is server-injected, never forwarded from browsers.
Module APIs must verify it. Module body/response limits are 2 MiB; other owner
API request limits remain 64 KiB. Internal health and shell routes can be public.
The sandbox allows downloads but keeps network connections and forms disabled.

Bridge requests are `{channel:'empyrean-v1',id,action,...}`; responses contain the
same channel/ID and `result` or `error`. Actions: `context` returns enabled app
names/IDs and Nexus locale; `request` takes module API path, method and optional
JSON body; `navigate` takes module ID or `nexus`; `external` opens only HTTP(S) or
mailto URLs with noopener/noreferrer. Modules own their navigation and switcher.

Locally built images can use immutable Docker image IDs `sha256:<64 hex>` (local
lookup only); remote images still require repository digests. Tags are not a
production image identity. Locale is an optional installation setting, default en.

Migration 3 adds blob grants and retained-volume identity markers. Existing users,
sessions, settings, references and module registrations remain unchanged. Retained
references OR data require explicit reuse_reference_identity on reinstall. Existing
modules gain no privileges automatically. Back up both Nexus data (including blobs)
and all module data volumes. Stop modules before copying their SQLite/WAL files.

A Docker administrator may install an already reviewed manifest with
`python -m nexus.manage /path/manifest.json` inside the gateway container. This uses
normal validation/install/enable APIs through a five-minute owner session removed
in finally; it never changes passwords or prints credentials. --reuse-data confirms
restoring the same dataset. Direct Docker/database administrator access is required.
