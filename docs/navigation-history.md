# Navigation history and deep links

**Status, 2026-11-09 (P1 Universal Navigation, aetest only).** Nexus 0.1.15 and every
public module use this contract: Meridian 0.11.0, Mnemosyne 1.5.1, Lyra 0.2.0, Chronos 0.5.0,
Atlas 0.4.0 and Argus 0.3.0, passing automated journeys in Chromium, WebKit and Firefox on
Linux. Production still runs the previous versions, in which Lyra, Chronos, Atlas and Argus
have bootstrap deep links only. Evidence and the checks that remain open are in the
[validation record](../../VALIDATION_P1_NAVIGATION_AETEST_2026-11-09.md). In production the
owner has confirmed only Mouse 4 / browser Back.

The feature is on by default. Zeus and Janus are outside it on purpose: Zeus is private
developer tooling, and Janus is delivered separately and locks when it is left.

This page describes the current integration contract. The [original proposal](proposals/navigation-history/README.md)
is historical design context; [PILOT.md](proposals/navigation-history/PILOT.md)
records the implementation and completed validation. Source of truth for behavior:
[`navigation-protocol.js`](../frontend/navigation-protocol.js),
[`router.js`](../frontend/router.js), and [`app.js`](../frontend/app.js).

## Activation and rollback

The feature is on unless the server process has `NEXUS_NAVIGATION_HISTORY=0`. Only that
literal value disables it. The authenticated `GET /api/v1/system` response and the application
bridge's `context` result expose `navigation: {versions:[1]}` when enabled, or
`{versions:[]}` otherwise. This is not `/api/v1/module/context` and not a manifest capability.

**Compose gap:** the checked-in `compose.yaml` does not forward the flag, so an operator kill
switch has to reach the container through a reviewed override:

```yaml
services:
  nexus:
    environment:
      NEXUS_NAVIGATION_HISTORY: "0"
```

To roll back, set that and restart. Clients fall back to their in-memory navigation when the
advertisement is empty. Saved drafts are not consumed on that path, so recover them first. An
old host cannot reconstruct an arbitrary new internal route.

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

### Shareable identity and private view state

A route reference is what can be copied and shared: a screen and stable IDs. Everything else
about how a view looked is **private per-entry view state**: filters, search text, loaded
ranges, scroll, tabs, a map position, which contact is selected. The browser entry holds only
an opaque ID in `history.state.nexusNavigation.entry`. The value stays in the Nexus page's
`sessionStorage` under `nexus.navigation.views.v1:<owner>:<module>`, at most 16 KiB per entry
and the 40 most recent entries per module. A pushed entry gets a new ID and a replaced entry
keeps its own. Sign-out and uninstall clear it. It is best effort and never blocks navigation.

A module returns this object from `captureView`, and receives it back as `message.viewState`.
It is captured for the entry on screen before the host moves on, which matters because the
browser has already changed entries by the time a `popstate` reaches Nexus. A new tab has none
of it, so a copied URL opens the record with default view settings.

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
place. Its `navigate` action takes a target module ID or `nexus`, plus an optional
`path` for the target's bootstrap grammar (`^/[a-zA-Z0-9/_-]*$`; since Nexus 0.1.14),
which is how backlinks open an exact record. Successful switching has no reply; avoid
making teardown depend on that old request's promise settling. The opt-in extension uses the separate
`empyrean-navigation-v1` channel.

All extension messages contain `channel`. The important fields are:

| Direction/type | Fields and behavior |
| --- | --- |
| Host `probe` | `challenge`; refreshed per frame load |
| Child `hello` | `version:1`, `document`, optional/current `challenge`; an initial hello without the right challenge elicits a probe |
| Host `restore` | `document`, `session`, increasing `revision`, `route`, `legacy`, `cause`; `viewState` for that entry except on a commit echo; initial restore also includes `checkpoint` or null |
| Child `commit` | `session`, `baseRevision`, `route`, `mode:'push'|'replace'`, optional `viewState` of the entry being left; one outstanding client intent; host rejects while leaving or when stale |
| Child `view-state` | `session`, `revision`, object `value`; debounced update for the entry on screen; dropped when stale |
| Child `applied` | `session`, `revision`, `status`: `ok`, `not-found` (the module is showing its own outcome; no host error) or `error` |
| Host `reject` | `session`, `revision`, `code`; stale intent also triggers resynchronization, never automatic rebasing |
| Child `checkpoint` | `session`, positive integer `id`, object `value`; bounded JSON snapshot |
| Host `checkpointed` | `session`, `id`, optional `error`; acknowledges storage or explicit failure |
| Host `prepare-leave` | `session`, increased `revision`, `id`; invalidates pending navigation and invokes the module's `beforeLeave` callback |
| Child `prepared` | `session`, `id`, optional `error`, optional `viewState`; host can then render the latest target or retain the editor on failure |

Host restore causes currently include `initial`, `commit`, `resync`, `resume`,
`traversal` and `navigate`. Do not use the cause string as authorization. The
client serializes application of restores and exposes `message.isCurrent()` to
guard asynchronous writes. An incoming restore/leave invalidates pending work.

| SDK member | Caller responsibility |
| --- | --- |
| `EmpyreanNavigation.createClient({apply,invalidate,onError,beforeLeave,captureView})` | Install callbacks before starting. `beforeLeave` defaults to a no-op: importing the SDK alone supplies no draft safety. `apply` throws on failure and returns `'not-found'` after rendering its own outcome. |
| `await client.start(context)` | Use the existing application `context` result. Resolves false for unsupported hosts/standalone windows and true once negotiated; **rejects on timeout**. Keep a legacy driver for both. Calling it again after a rejection starts a clean attempt. |
| `await client.navigate(reference, mode)` | Validate/save/guard first. Sends one intent; a second pending intent is rejected rather than queued/coalesced. |
| `await client.checkpoint(object)` | Supply module-owned JSON and await storage acknowledgment where safety depends on it. Before negotiation it resolves without storage. |
| `client.viewChanged()` | The private view state of the entry on screen changed (debounced; scrolling is noticed automatically when `captureView` exists). |
| `client.status` | `idle`, `handshaking`, `ready`, `failed` or `unsupported` |
| `client.enabled`, `client.revision`, `client.route` | `enabled` is true only with a granted session and false again after a failed handshake. Runtime state, not auth credentials |

`navigate()` resolves with `{...message, status}` once the restore was applied, and
`status` says whether the target actually rendered. A superseded restore does nothing: an
adapter that sets its "shown route" before loading must clear it when `isCurrent()` turns
false, or the following restore of the same route is skipped.

Current bounds: 40 commits/second and 100 checkpoints/second per bound frame,
2048-byte references, 1 MiB serialized checkpoint, five hello attempts at 500 ms
intervals, 10-second client acknowledgment deadlines, 5-second parent leave
deadline and 20-second host restore acknowledgment deadline. Browser storage
quotas can be lower than the snapshot limit. These are pilot constants in the SDK,
not operator settings or durable delivery guarantees.

## Adopting the contract in another module

Review a module-specific integration first:

1. Vendor the dependency-free SDK from Nexus, keep attribution, and bundle it
   inline using the module's existing HTML packaging. Do not load it from a CDN
   or add same-origin/network CSP privileges. Add the module to the list in
   `scripts/sync-navigation.mjs`. `node scripts/sync-navigation.mjs --check` verifies every
   copy; the command without `--check` writes them.
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

Six adapters now exist, each module's `frontend/navigation.js`. Mnemosyne's
[integration notes](../../mnemosyne/docs/NAVIGATION_HISTORY.md),
[`navigation-routes.js`](../../mnemosyne/frontend/navigation-routes.js) and
[`navigation.js`](../../mnemosyne/frontend/navigation.js) are the first worked
example, not a generic domain router for every AE module.

### Route references per module

| Module | References | Private per-entry state |
| --- | --- | --- |
| Meridian | `/`, `/people[/<id>]`, `/organizations[/<id>]`, `/groups[/<id>]`, `/interactions/<id>`, `/graph`, `/timeline`, `/import`, `/trash`, `/settings` | directory search, filters, sort, loaded count, contact tab, scroll |
| Mnemosyne | see its integration notes | checkpointed search |
| Lyra | `/`, `/series`, `/movies`, `/discover`, `/history`, `/series/<id>`, `/movie/<id>`, `/preview/<movie\|tv>/<tmdb>` | search text, status filters, open season, scroll |
| Chronos | `/<month\|week\|day\|agenda>/<date>`, `/events/<id>[?o=&view=&date=]`, `/projected/<provider>?item=&view=&date=` | search text, category filter, agenda range, scroll |
| Atlas | `/`, `/library`, `/categories`, `/trash`, `/settings`, `/places/<id>[?section=]`, `/map/contact` | who is selected, map position, library search, scroll |
| Argus | `/`, `/photos/<id>`, `/people`, `/clusters/<id>`, `/import`, `/trash`, `/settings`, bootstrap `/pick/...` | loaded count, scroll, import folder, typed settings |

An unknown or malformed reference, and a record that does not exist, render an explicit
not-found view and keep their address. No module falls back to an unrelated screen.

A list arrow inside a module (Lyra's title header, Chronos's and Atlas's close button) is an
ordinary push to the parent view. Browser Back is the traversal. The contract has route
commits, not a traversal command, and none was added.

## Draft recovery and security boundaries

The parent stores snapshots in its own `sessionStorage` under
`nexus.navigation.drafts.v1:<owner-username>:<bound-module-id>`. This is readable
JSON held by the trusted Nexus page, not encrypted vault storage. It is scoped by
origin, tab, owner username and the verified frame binding, not a module-supplied
target. It is neither a server database nor included in Nexus/module backups.
The child cannot directly access parent storage. Only its own snapshot is sent
back on initial restore. The owner/host administrator and compromised parent code
remain within the trust boundary; Janus vault data must not use this mechanism.

### Unsaved editors while the address moves

Native traversal cannot be cancelled, and pushing the old page back would destroy the Forward
branch, so no module ever does that. The rule in every adapter:

| Situation | What happens |
| --- | --- |
| A click inside the module | The module asks first, before any navigation |
| Browser Back/Forward with an unsaved modal editor (Meridian's side panel, Chronos's event editor, Atlas's Place editor) | The address moves. **The screen and the editor stay**, with a notice. Nothing is written to history, so Forward still works. Going back to the editor's address clears the notice; saving or discarding shows the page the address names |
| Leaving the module (Nexus launcher, backlink, sign-out) | `beforeLeave` stores an acknowledged checkpoint, and on return a tray offers **Resume** or **Discard** |
| Reload or tab restore | The checkpoint written about 400 ms after the last keystroke is offered the same way |
| The checkpoint cannot be stored | The leave is refused, the editor stays open, and Nexus shows why |
| A field that saves itself (Lyra's notes, Argus's photo title) | Saved on the way out, since a traversal does not blur it. A Lyra note that cannot be saved becomes a draft; an Argus title that cannot be saved keeps the photo on screen |
| A recovered draft meets a newer saved record (Meridian contacts) | The save is refused as a conflict with the text intact, and the owner can choose **Keep my version**. Sections the draft did not touch keep the newer values |

Mnemosyne keeps its autosave model: edits post asynchronously with an acknowledged final
checkpoint, a failed save retains a copy, and recovering differing versions keeps the draft's
original revision so its conflict rules still apply. Sign-out warns before deleting dirty
tab checkpoints, uninstall removes that module's copy.

If leave/checkpoint fails or times out, the parent reports the failure and retains
the editor. The requested browser address may temporarily differ from that editor;
the host does not call `history.go(1)` to force the browser back. Sandboxed frames cannot
show a `beforeunload` prompt, so a very recent unacknowledged edit, a crash, cleared storage
or a quota failure is not covered by an unconditional no-loss guarantee. Secrets are never
checkpointed: Lyra's TMDB credential field is excluded. In-progress Argus uploads stop if the
frame is replaced, as they always have. Search text is kept in tab state, not shareable URLs.

Navigation is not an authorization grant. Host messages require the connected,
active enabled application's `contentWindow`; comparing an opaque `null` origin
alone is insufficient. The client checks parent source and expected origin.
Challenge/session/revision fences prevent obsolete documents/intents from
controlling a replacement view. Parent-to-opaque-child `'*'` replies are restricted
to the bound frame; no auth credentials are included. Draft and view payloads can contain
private user text by design, so do not describe the channel as carrying only route
metadata. Existing HTTP APIs continue to enforce owner sessions, CSRF and module
gateway keys independently. No blanket sandbox, external-origin trust or capability
expansion is introduced.

## Validation and remaining gates

The current evidence is the [P1 validation record](../../VALIDATION_P1_NAVIGATION_AETEST_2026-11-09.md),
produced by `tests/e2e/universal_navigation_e2e.cjs` against real aetest containers. The
earlier pilot evidence is in [PILOT.md](proposals/navigation-history/PILOT.md). Automated
traversal is not hardware: a physical Mouse 4/5, the browser's own Alt+Left/Right handling and
a real phone remain the owner's checks.

When writing a browser test, note that Nexus changes the address before a leave finishes, so
wait for the frame to be replaced before treating the module as left. WebKit's Back can skip
entries created by script with no user gesture, so build test history with real clicks.
