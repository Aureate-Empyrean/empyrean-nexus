# Navigation history and deep links

**Status update, 2026-11-07.** Nexus 0.1.11 is reported deployed on Exodus with
this feature **enabled by default** (`NEXUS_NAVIGATION_HISTORY=0` is an internal kill
switch; the backend treats unset as on). Meridian 0.4.1 added the first deployed
adapter (routes `/`, `/people[/<id>]`, `/organizations[/<id>]`, `/groups[/<id>]`,
`/graph`, `/timeline`, `/import`, `/trash`, `/settings`; tabs and filters are not in
URLs). Source: workspace `DEPLOYMENT_NAVIGATION_2026-11-07.md`. Automated aetest
checks: Meridian navigation 17/17 (Back/Forward, person, Mouse 4/5 through CDP,
direct link, refresh, Nexus↔Meridian, Chronos switch, invalid routes, unsaved-edit
guard, 390 px). In production the owner has confirmed only **Mouse 4 / browser Back**;
Forward, direct links, refresh, Mouse 5, Firefox/WebKit, BFCache and physical mouse
buttons are not verified there. Mnemosyne's adapter is in the local tree and **not
deployed**; Chronos, Lyra and Argus keep legacy navigation. It remains adapter-specific,
not an all-module commitment. The bridge action `session` is separate (Nexus 0.1.12
source, not deployed).

The sections below were written on 2026-11-05 for the then default-off pilot. Where
they say "off by default", "pilot" or that Mnemosyne is the only adapter, read the
status above; they are otherwise the current integration contract.

*Original 2026-11-05 note:* the Nexus + Mnemosyne pilot existed in the local working
trees and was off by default. Chronos remained an unmodified legacy module in the
browser test.

This page describes the current integration contract. The [original proposal](proposals/navigation-history/README.md)
is historical design context; [PILOT.md](proposals/navigation-history/PILOT.md)
records the implementation and completed validation. Source of truth for behavior:
[`navigation-protocol.js`](../frontend/navigation-protocol.js),
[`router.js`](../frontend/router.js), and [`app.js`](../frontend/app.js).

## Activation and rollback

**As of Nexus 0.1.11 the feature is on unless the server process has
`NEXUS_NAVIGATION_HISTORY=0`.** (2026-11-05 pilot wording, superseded: the process
had to receive exactly `NEXUS_NAVIGATION_HISTORY=1`; unset, `0` or any other value
meant off.) The authenticated `GET /api/v1/system`
response and the application bridge's `context` result expose
`navigation: {versions:[1]}` when enabled, or `{versions:[]}` otherwise. This is
not `/api/v1/module/context` and not a new manifest capability or schema version.

Activation requires all three:

1. Nexus backend and frontend containing the pilot, restarted/reloaded together.
2. The flag in the actual Nexus process environment.
3. An enabled `ui.application` module containing the shared client and its own
   route/draft adapter. Mnemosyne is the only integrated application today.

For a normally configured **local native** server, the flag can be supplied before
starting it. This example starts no broker or modules:

```powershell
# From empyrean-nexus, with normal dependencies installed in .venv:
$env:NEXUS_NAVIGATION_HISTORY = '1'
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -X utf8 -m uvicorn nexus.app:create_app --factory --host 127.0.0.1 --port 12333 --no-proxy-headers
```

Use the [disposable real-app browser test](development.md#navigation-history-pilot)
to exercise local module lifecycle without a Docker broker. Do not connect its
test-only process runtime to a real installation.

**Compose gap:** checked-in `compose.yaml` and `.env.example` do not forward or
declare this flag. Adding it to `.env`, or to the host shell, alone does not put it
inside the Nexus container. A separately reviewed local Compose override must
explicitly add the following environment entry to the `nexus` service, and the
local container must use the pilot build and be recreated. No such override or
deployment is supplied/applied by this documentation update:

```yaml
services:
  nexus:
    environment:
      NEXUS_NAVIGATION_HISTORY: "1"
```

To roll back, remove the flag from the actual server/container environment and
restart/reload the host and module UI. New clients fall back to legacy navigation
when the version advertisement is missing/empty. Keep saved drafts or recover
them before disabling the feature: the old path does not consume the checkpoint
channel. An old host cannot reconstruct an arbitrary new internal route.

## Ownership and URLs

Nexus owns the top-level browser URL and History API writes. Modules own domain
route parsing, normalization, rendering, save/conflict behavior and UX. Nexus
treats a route reference as data; it never uses it as an API or proxy fetch target.
Resource UUIDs/references remain independent of UI addresses.

| Address/data | Meaning |
| --- | --- |
| `/app/modules/<id>` | Existing Nexus module route; bootstrap defaults to `/` |
| `?path=<simple-path>` | Existing iframe HTTP bootstrap path, unchanged |
| `&nav=1&route=<encoded-reference>` | Additive internal route envelope |
| `/modules/<id><path>` | Owner-authenticated gateway document loaded in the iframe |

For example, using documentation-only UUIDs:

```text
/app/modules/mnemosyne?nav=1&route=%2Fw%2F11111111-1111-1111-1111-111111111111%2Ftasks%3FtaskView%3Dall
```

The decoded route is `/w/11111111-1111-1111-1111-111111111111/tasks?taskView=all`.
Build the outer query with `URLSearchParams` once. Queries/fragments inside a
reference are encoded inside `route`; an outer fragment is not a second route
store. The generic validator accepts inner fragments, but Mnemosyne's codec
currently rejects them. Bootstrap `path` keeps its older simple-path grammar;
it is not expanded to accept internal queries or arbitrary URLs.

References must begin with one `/`, be at most 2048 UTF-8 bytes and exclude
authority URLs, whitespace/control characters, backslashes, malformed escapes,
dot segments and encoded separators in the pathname. The host rejects duplicate
reserved envelope parameters, an unsupported version, or a missing/invalid route.
Legacy URLs without an envelope retain first-value `path` behavior. The module
codec applies additional domain validation; the generic validator is not a domain
schema. The new router parses envelopes even when the feature is off, so a
malformed envelope can still produce a host not-found view in that configuration.

User navigation pushes one entry; normalization/filter updates may replace it.
Repeated identical URLs do not push. The SDK preserves unrelated query fields,
the outer hash and other `history.state` keys. URL reconstruction, not hidden
JavaScript history state, identifies the resource after reload. Search text,
drafts, credentials and resource bodies must not be placed in route references.

## Module loading and iframe lifecycle

The host authenticates the owner and loads module metadata before showing the
application. Enabled `ui.application` modules use an opaque iframe with
`sandbox="allow-scripts allow-downloads"`. Non-application module views retain
their existing restricted iframe/API-explorer path; they do not receive this SDK
bridge. Gateway authentication, proxy path checks and CSP remain separate.

With the flag enabled, a frame is retained for the same module, bootstrap path,
manifest version and image identity. Internal route changes restore into it;
routine refresh does not reload it. A module/path/code identity change mounts a
fresh frame. Refresh that detects disable/removal/code replacement first requests
a participating frame's checkpoint; this is a browser UI guard, not a transaction
that delays an already requested server lifecycle operation. Without the flag,
the legacy module-render path remains in use.

Each frame load rotates a challenge; the loaded client answers it with a fresh
document identity, and the host assigns a frame session. Unmount/auth-screen reset
retires the binding. `popstate` restores same-module views or mounts the appropriate
module. Rapid parent routing requests keep only the latest target after the shared
leave checkpoint. `pageshow.persisted` requests refresh/resynchronization, but
BFCache behavior has not yet been signed off in a real-browser test.

Participating clients must not also write child history, change `location`, or use
hash/document navigation for internal views. Child document history can create
extra tab traversal steps. Native Back/Forward, keyboard traversal and Mouse4/5
are used without global mouse/keyboard interception. Legacy modules still own
their existing internal behavior; private memory state cannot be restored by an
SDK they do not implement.

## Shared transport and client API

The existing `empyrean-v1` API/context/external/module-switch bridge remains in
place. Its `navigate` action takes a target module ID or `nexus`, not an internal
route. Successful switching currently has no reply; avoid making teardown depend
on that old request's promise settling. The opt-in extension uses the separate
`empyrean-navigation-v1` channel.

All extension messages contain `channel`. The important fields are:

| Direction/type | Fields and behavior |
| --- | --- |
| Host `probe` | `challenge`; refreshed per frame load |
| Child `hello` | `version:1`, `document`, optional/current `challenge`; an initial hello without the right challenge elicits a probe |
| Host `restore` | `document`, `session`, increasing `revision`, `route`, `legacy`, `cause`; initial restore also includes `checkpoint` or null |
| Child `commit` | `session`, `baseRevision`, `route`, `mode:'push'|'replace'`; one outstanding client intent; host rejects while leaving or when stale |
| Child `applied` | `session`, `revision`, `status`; current SDK emits `ok` or `error`; host also accepts `not-found` |
| Host `reject` | `session`, `revision`, `code`; stale intent also triggers resynchronization, never automatic rebasing |
| Child `checkpoint` | `session`, positive integer `id`, object `value`; bounded JSON snapshot |
| Host `checkpointed` | `session`, `id`, optional `error`; acknowledges storage or explicit failure |
| Host `prepare-leave` | `session`, increased `revision`, `id`; invalidates pending navigation and invokes the module's `beforeLeave` callback |
| Child `prepared` | `session`, `id`, optional `error`; host can then render the latest target or retain the editor on failure |

Host restore causes currently include `initial`, `commit`, `resync`, `resume`,
`traversal` and `navigate`. Do not use the cause string as authorization. The
client serializes application of restores and exposes `message.isCurrent()` to
guard asynchronous writes. An incoming restore/leave invalidates pending work.

| SDK member | Caller responsibility |
| --- | --- |
| `EmpyreanNavigation.createClient({apply,invalidate,onError,beforeLeave})` | Install callbacks before starting. `beforeLeave` defaults to a no-op: importing the SDK alone supplies no draft safety. |
| `await client.start(context)` | Use the existing application `context` result. Returns false for unsupported hosts/standalone windows; retain a legacy driver. |
| `await client.navigate(reference, mode)` | Validate/save/guard first. Sends one intent; a second pending intent is rejected rather than queued/coalesced. |
| `await client.checkpoint(object)` | Supply module-owned JSON and await storage acknowledgment where safety depends on it. Before negotiation it resolves without storage. |
| `client.enabled`, `client.revision`, `client.route` | Runtime negotiation/revision state, not auth credentials |

The current `navigate()` promise can resolve after a restore callback reports an
application error; use `onError`, module error UI and host status as well. Promise
resolution alone is not proof that the target resource rendered successfully.
`apply` return values do not select an `applied` status: throw on failure.

Current bounds: 40 commits/second and 100 checkpoints/second per bound frame,
2048-byte references, 1 MiB serialized checkpoint, five hello attempts at 500 ms
intervals, 10-second client acknowledgment deadlines, 5-second parent leave
deadline and 20-second host restore acknowledgment deadline. Browser storage
quotas can be lower than the snapshot limit. These are pilot constants in the SDK,
not operator settings or durable delivery guarantees.

## Adopting the pilot in another module

No automatic migration is enabled. Review a module-specific integration first:

1. Vendor the dependency-free SDK from Nexus, keep attribution, and bundle it
   inline using the module's existing HTML packaging. Do not load it from a CDN
   or add same-origin/network CSP privileges. The current sync script is fixed to
   Mnemosyne; it is not a general module installer. `node scripts/sync-navigation.mjs --check`
   verifies the existing copy; the command without `--check` writes that copy.
2. Define a strict module-owned parse/serialize codec using stable IDs. Preserve
   old bootstrap/resource paths. Decide which views are shareable and which
   ephemeral/private state stays out of URLs.
3. Create the client with `apply` (restore without echoing a commit), `invalidate`
   (cancel/fence old requests and UI work), `onError` and `beforeLeave` (take an
   acknowledged recovery checkpoint). Use `isCurrent()` before async state/DOM
   writes. Snapshot contents and recovery/version migration remain module-owned.
4. Discover support from the existing bridge context. Start only after the module
   can restore its initial route. If unsupported, keep memory/legacy navigation.
   Supply the original bootstrap path for older hosts where it is meaningful.
5. Audit every navigation source: sidebar, rows, drawers, tabs, workspace changes,
   shortcuts, reference opening and direct state assignments. Save/guard then send
   the intent; render committed state from restore. Use replace for initial
   canonicalization; do not push for polling, typing editor text or mutation-only
   updates. Serialize intents in the module and handle supersession explicitly.
6. Test the real authenticated host/module, old/new host combinations, failed saves,
   conflicts, quotas, frame reload/replacement, Back/Forward, Mouse4/5, copy/reload,
   stale messages and module lifecycle. Do not claim a new module is supported
   merely because its manifest grants `ui.application`.

Mnemosyne's [integration notes](../../mnemosyne/docs/NAVIGATION_HISTORY.md),
[`navigation-routes.js`](../../mnemosyne/frontend/navigation-routes.js) and
[`navigation.js`](../../mnemosyne/frontend/navigation.js) are the first worked
example, not a generic domain router for every AE module.

## Draft recovery and security boundaries

The parent stores snapshots in its own `sessionStorage` under
`nexus.navigation.drafts.v1:<owner-username>:<bound-module-id>`. This is readable
JSON held by the trusted Nexus page, not encrypted vault storage. It is scoped by
origin, tab, owner username and the verified frame binding, not a module-supplied
target. It is neither a server database nor included in Nexus/module backups.
The child cannot directly access parent storage. Only its own snapshot is sent
back on initial restore. The owner/host administrator and compromised parent code
remain within the trust boundary; Janus vault data must not use this mechanism.

Mnemosyne posts edits asynchronously and takes an acknowledged final checkpoint
before parent SPA navigation/unmount. Click navigation retains its save/conflict
guard. Native history traversal cannot be canceled; a failed save retains a copy
and provides recovery in the original workspace. Recovering differing saved/draft
versions preserves the draft's original revision so existing conflict rules still
apply. Quick-capture input is also retained. Sign-out warns before deleting dirty
tab checkpoints, uninstall removes that module's copy, and saved/discarded editor
copies are reconciled by later checkpoints. Opening a deep link still requires
owner authentication and normal module/resource checks.

If leave/checkpoint fails or times out, the parent reports the failure and retains
the editor. The requested browser address may temporarily differ from that editor;
the host does not call `history.go(1)` to force the browser back. Full-document
reload/close does not run the SPA leave handshake: it relies on snapshots already
acknowledged and Mnemosyne's existing `beforeunload` warning. A tab/browser crash,
cleared storage, quota failure or a very recent unacknowledged edit is not covered
by an unconditional no-loss guarantee. Search text is kept in tab checkpoints,
not shareable URLs; a clean tab gets an empty search prompt.

Navigation is not an authorization grant. Host messages require the connected,
active enabled application's `contentWindow`; comparing an opaque `null` origin
alone is insufficient. The client checks parent source and expected origin.
Challenge/session/revision fences prevent obsolete documents/intents from
controlling a replacement view. Parent-to-opaque-child `'*'` replies are restricted
to the bound frame; no auth credentials are included. Draft payloads can contain
private user text by design, so do not describe the channel as carrying only route
metadata. Existing HTTP APIs continue to enforce owner sessions, CSRF and module
gateway keys independently. No blanket sandbox, external-origin trust or capability
expansion is introduced.

## Validation and remaining gates

[Recorded real-app evidence](proposals/navigation-history/pilot-evidence/chrome-results.json)
contains 16 scenarios on Chrome 157.0.8103.39 / Playwright 1.64.1 / Windows:
authenticated direct links; Notes/Tasks and task-detail Back/Forward; unchanged
Chronos switching; reload; synthetic CDP Mouse4/5; successful-save, quick-capture,
failed-save and real revision-conflict recovery; workspace links; preview/search;
missing resources; legacy paths; sign-out warning/session revocation.

The test uses actual Nexus, Mnemosyne and Chronos HTML, APIs, databases and gateway
over loopback HTTP. Only container lifecycle is substituted with a disposable
process launcher. Browser PUT-failure injection tests recovery; the conflict is
from the real backend. This is stronger than the original synthetic fixture and
still not a production/container-broker deployment test.

Recorded suites: 24 Nexus frontend/SDK, 13 Mnemosyne frontend/codec, 46 affected
Nexus backend and 30 Mnemosyne backend tests passed. Full Nexus: 200 passed, one
opt-in browser test skipped, two existing Windows oversized-SVG pytest fixture
errors. The separate `shutil.disk_usage` change resolved the `os.statvfs` failure;
its portability test and the prior locale test passed. [PILOT.md](proposals/navigation-history/PILOT.md)
has reproduction details, warning/environment notes and the implementation file
inventory. These are recorded implementation runs; documentation synchronization
does not imply a new test run or production verification.

Remaining gates include Firefox/WebKit, physical mouse hardware, BFCache,
container/image/broker lifecycle, session-expiry/relogin, disabled/uninstalled
module behavior under live transitions, quota/checkpoint timeout recovery,
rapid traversal under slow APIs, HTTP LAN origin handling, and deployment-specific
authentication/proxy/CSP verification. Some defensive paths have unit coverage;
that is not equivalent to real-app browser sign-off for all failure combinations.
The SDK, snapshot schema and module adoption remain pilot contracts pending that
review. No production rollout, other-module migration, commit or push is implied.
