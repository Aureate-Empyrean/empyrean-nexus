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
JSON body; `navigate` takes module ID or `nexus`; `external` asks to open an
absolute HTTP(S) or mailto URL (≤ 2048 characters, no embedded credentials). An
HTTP(S) URL opens directly only if the owner already trusted its exact origin for
this module; otherwise Nexus asks the owner to trust the origin and opens nothing,
answering `{opened:false, trusted:true}` (or an error if refused). mailto opens only
the reviewed recipient address, never module-supplied fields. Modules own their
navigation and switcher.

`session` (since Nexus 0.1.12 source, released with 0.1.13; on aetest, not yet in production, whose Nexus is 0.1.11 without it) keeps one opaque value per module in the browser tab's
`sessionStorage`, because the opaque-origin sandbox has no storage of its own and a
refresh would otherwise forget a module's own sign-in. `{op:'get'}` answers
`{value}` (or `null`), `{op:'set', value}` stores 1–512 printable ASCII characters,
`{op:'clear'}` removes it. The value is scoped to the module ID of the displayed
frame, ends with the tab, is never put in `localStorage`, and every module session
value is removed when the owner signs out of Nexus or the Nexus session ends. The
module must still validate the value server-side; Nexus does not interpret it. Older
Nexus versions answer `Unsupported bridge action`, so modules must treat the action
as optional. See [security model](security-model.md#external-navigation).

### Local navigation-history extension

Since Nexus 0.1.11 navigation history is enabled by default: the application `context`
result carries `navigation: {versions:[1]}` unless the Nexus process has
`NEXUS_NAVIGATION_HISTORY=0` (an internal kill switch), in which case it reports
`{versions:[]}`. This browser context is distinct from the
bearer-authenticated `/api/v1/module/context`. No new manifest field or grant is
required beyond the existing enabled `ui.application` boundary.

The existing `navigate` action still switches module ID only (and does not reply
on a successful switch). Internal routes use the shared
`empyrean-navigation-v1` SDK: parent history, challenge/session/revision-bound
restores, acknowledged checkpoints and prepare-leave handling. Bundle the client
inline; never relax iframe/CSP restrictions to inspect module state. Meridian 0.4.1
(reported deployed) and Mnemosyne (local tree, not deployed) have adapters; other
modules keep legacy navigation. See the [current contract/adoption guide](navigation-history.md)
for feature activation, old-host fallback, URL grammar, frame retention and draft
security. The host feature is reported deployed in Nexus 0.1.11 (owner confirmed
Mouse 4 / Back in production; other scenarios unverified there). It is a browser
bridge extension and says nothing about the future Android Nexus, whose modules are
separate packages with Nexus-defined IPC (`architecture/modules/nexus.md`).

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
