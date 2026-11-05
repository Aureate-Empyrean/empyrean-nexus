# Nexus + Mnemosyne navigation pilot

Implementation/validation record. For current activation, the shared SDK API,
adoption and failure-mode limits, use [navigation-history.md](../../navigation-history.md).
The current Compose file does not forward the flag; `.env` alone is insufficient.

Implemented locally on 2026-11-05 after approval of the proposal. Only Nexus and
Mnemosyne were changed for this work. Chronos is an unchanged legacy participant
in the browser tests. No Exodus access, deployment, container build or production
data access was performed. Existing working-tree edits in both repositories were
preserved; temporary baseline copies were used to review this task's changes.

## Runtime behavior

Nexus advertises `navigation: {versions:[1]}` in its authenticated system response
and application context **only when `NEXUS_NAVIGATION_HISTORY=1`**. Default is off.
Mnemosyne detects support before starting the navigation channel; without it,
the existing memory navigation remains in use. Manifests, grants, auth cookies,
CSRF rules, gateway credentials, module API restrictions, CSP and sandbox flags
are unchanged. There is no same-origin or top-navigation permission added.

Nexus owns `pushState`/`replaceState` and restores on native `popstate`. Mouse4/5
use native traversal, with no mouse-button interception. Same-module navigation
and routine data refresh preserve the mounted iframe. Module/path changes and
module code identity changes mount a fresh iframe. Lifecycle refresh takes a
checkpoint before rendering a disabled or replaced participating view; it does not
delay an already requested server-side stop. Module session/revision fences reject
stale/foreign intents. Nexus never uses the internal reference as an API/proxy
target; the module may call its normal APIs to resolve and render that reference.

Old `/app/modules/<id>` and `?path=/w/<workspace>/r/<resource>` links still work.
`path` retains its original role as a validated HTTP bootstrap path. The additive
`nav=1&route=<encoded-reference>` carries internal state, query included. The
URL alone selects the module, workspace, view, resource, task drawer and selected
tab after reload. Missing resources retain the requested address and show an
error rather than selecting a different note. Initial normalization uses replace;
duplicate routes do not push new entries. Other shell query fields/state survive.

### Shared transport additions used by the pilot

The original proposal's hello/restore/commit/applied/reject messages remain the
core. These additions close real lifecycle/draft gaps found while integrating:

| Message | Behavior |
| --- | --- |
| Host `probe {challenge}`; child `hello {...,challenge}` | Fresh challenge per iframe load. Only the currently loaded document receives it; an old document's queued hello cannot establish a new live session. Random IDs use `getRandomValues`, which also supports existing HTTP LAN installations without `randomUUID`'s secure-context requirement. |
| Child `checkpoint {session,id,value}`; host `checkpointed {session,id,error?}` | Host stores JSON in sessionStorage under authenticated owner + bound module ID, then acknowledges. The body is bounded to 1 MiB and 100 checkpoints/second. No draft text, API token or credential is put in a URL. `value.dirty` is transport metadata for the sign-out warning. |
| Host `prepare-leave {session,revision,id}`; child `prepared {session,id,error?}` | Before parent routing/traversal changes a participating view, freeze its UI, invalidate obsolete work and take a final acknowledged draft checkpoint. Parent rejects late commits during this interval. Rapid traversals share that checkpoint and only the latest requested target renders. Legacy frames do not wait. |

If the final checkpoint fails or the child does not respond within five seconds,
Nexus keeps the editor available for recovery and reports the error; it never
tries to reverse browser history with `go(1)`. The browser's requested address
may then differ from the retained editor until the owner retries. This explicit
failure state is preferable to unmounting uncheckpointed drafts. A failed module
render has a separate 20-second acknowledgment timeout and retains the address.

The shared dependency-free source is `frontend/navigation-protocol.js` in Nexus.
`node scripts/sync-navigation.mjs` vendors the identical source into Mnemosyne;
`--check` and a regression test enforce byte identity. The Mnemosyne HTML response
bundles it inline with its route codec/adapter, matching the existing gateway CSP.
Future modules can reuse the same client without sharing Mnemosyne's domain router.

### Mnemosyne routes

References use `/w/<workspace-uuid>/<view>`. Views: `home`, `notes`, `tasks`,
`projects`, `collections`, `trash`, `workspaces`, `search`. Resource identities
are UUIDs, not titles. Optional fields are bounded by the module-owned codec:

* Notes: `note=<uuid>`, `preview=1`.
* Tasks: `taskView=today|all|inbox|upcoming|completed`, `task=<uuid>` for an open
  task detail drawer. Task drawers can also be opened from other views.
* Projects: `project=<uuid>`, `projectTab=board|overview|tasks|notes`.
* Collections: `collection=<uuid>`, `collectionNote=<uuid>`, `preview=1`.
* Resource details: `details=<uuid>`.
* Legacy `/w/<workspace>/r/<resource>` references resolve the resource kind and
  normalize to the corresponding view without adding a Back step.

Search view navigation is linkable; search text stays in this tab's checkpoint,
not in the URL. A search link in a fresh tab has an empty search prompt. Graph
coordinates, scroll, caret position, transient pickers and personal text are not
part of the shareable routing contract. Notes/Tasks, resource opening, task/detail
drawer changes, project tabs, workspace changes, preview and search use the adapter.

### Draft policy

Editor changes are posted asynchronously for checkpointing, and an acknowledged
final checkpoint precedes parent SPA traversal/unmount. Click navigation still calls Mnemosyne's existing flush
and conflict guard. Native traversal cannot be canceled: it retains dirty editor
sessions/recovery copies and attempts background saving, while restoring the new
view. A recovery banner opens retained drafts in their original workspace.
Quick-capture and quick-add inputs are retained before they become resources.

After reload, drafts are reconciled against the saved resource. A differing draft
keeps its original revision and requires review/retry; it cannot silently overwrite
a newer server revision. Existing Keep mine / Use saved choices remain explicit.
Use saved refreshes the actual editor, fixing the list-only render that otherwise
left discarded text visible in the pilot. Stale loads/guards cannot navigate over
a subsequent traversal. In-flight saves stay bound to their original workspace.

Recovery copies are readable JSON in the trusted parent's sessionStorage, keyed
by origin/tab, owner username and bound module ID. They are removed/reconciled when
saved/discarded, on module uninstall, or on sign-out. Sign-out now warns and allows
canceling if any module has retained dirty checkpoints. They are not a replacement
for server saves/backups; closing/clearing the tab can remove sessionStorage.
Storage/quota failures are explicit and prevent a checkpoint-dependent unmount.
Full-document reload/close relies on previously acknowledged snapshots and the
existing unload warning; tab/browser failure or an unacknowledged latest edit is
not covered by an unconditional no-loss promise. The SDK's `navigate()` promise
can resolve despite a failed application restore: inspect `onError`/visible status.

## Validation

The regression starts **real Nexus, Mnemosyne and Chronos ASGI apps as separate
loopback HTTP processes**, with fresh SQLite data. Only the container broker is
replaced by a test-only local process launcher. Login UI, owner session, CSRF,
authenticated gateway, gateway-key validation, actual module HTML/JS/CSP, domain
APIs, optimistic revisions and module-to-Nexus calls run normally. No domain API
or frontend is synthesized. Save-failure phases intentionally reject browser-origin
PUTs in the composite regression; concurrency conflicts come from the real backend.

Chrome 157.0.8103.39 / Playwright 1.64.1 / Windows passed **16 browser scenarios**:

1. Authenticated direct note deep link and opaque-origin isolation.
2. Notes → Tasks → Back → Notes; Back → Forward; no duplicate history entry;
   same-module iframe identity preserved.
3. Tasks → task detail → Back → Tasks; Forward restores detail.
4. Mnemosyne → unchanged Chronos → Back restores the previous internal view.
5. Reload restores list + selected task detail.
6. CDP Mouse4/Mouse5 events perform native traversal to actual module views.
7. A fresh editor change saves before click navigation.
8. Unsubmitted quick-capture text survives navigation and reload.
9. Failed-save draft survives traversal + full reload, with no text in URL.
10. Failed-save click guard and recovery after real module unmount.
11. Real server revision conflict preserves text until an explicit choice.
12. Deep links choose their own workspace rather than the most recent one.
13. Preview/search views participate in history; search text stays out of URLs.
14. Missing-resource link retains its address and reports an error.
15. Legacy `?path=/w/.../r/...` link opens the expected note.
16. Sign-out warns before clearing drafts and revokes the session normally.

Evidence: [browser results](pilot-evidence/chrome-results.json) and
[actual Mnemosyne screenshot](pilot-evidence/mnemosyne.png), visually inspected.

Other checks:

| Suite | Result |
| --- | --- |
| Nexus frontend + SDK | 24 passed |
| Mnemosyne frontend + route codec | 13 passed |
| Affected Nexus backend/auth/navigation/system suites | 46 passed |
| Mnemosyne backend | 30 passed, with timezone data available on Windows |
| Nexus full backend suite | 200 passed, 1 opt-in browser test skipped, 2 existing Windows pytest fixture errors described below |
| Targeted Python Ruff, JS syntax, vendored-source identity | Passed |

The full Nexus suite's two errors are the setup and teardown of the existing
oversized-SVG parameter in `tests/test_icon_cache.py`. Pytest tries to put that
complete node ID into `PYTEST_CURRENT_TEST`, exceeding Windows' 32767-character
environment-variable limit. The test body does not run. This task does not modify
those existing icon tests. No failures were hidden by mocks or test deselection.
An initial Mnemosyne run without Windows timezone data also failed workspace
setup; the suite passed after using the same temporary `tzdata` dependency as the
real-app browser test. The existing Starlette/httpx deprecation warning remains.

### Separate Windows capacity fix

`backend/nexus/app.py` now reports free space through `shutil.disk_usage(data).free`
instead of POSIX-only `os.statvfs`. `tests/test_system_portability.py` independently
checks the data directory and returned available bytes. The formerly failing
`test_locale_preserved` passes on Windows. No filesystem/auth policy changed.

### Reproduce

Use the repositories' normal Python dependencies (Nexus + Mnemosyne + Chronos)
and installed Chrome. The test runtime uses each module's `.venv` if present,
otherwise its own Python environment. On Windows, timezone data must be importable.
The following uses temporary extra packages without changing runtime lockfiles:

```powershell
# In G:/AureateEmpyrean/empyrean-nexus
python -m pip install --target "$env:TEMP\nexus-navigation-proof-python" playwright==1.64.1 'icalendar>=7,<8' 'python-dateutil>=2.9,<5' tzdata
$env:PYTHONPATH = "$env:TEMP\nexus-navigation-proof-python"
$env:NEXUS_BROWSER_TESTS = '1'
.\.venv\Scripts\python.exe -X utf8 -m pytest -q -s tests/test_navigation_browser.py
Remove-Item Env:NEXUS_BROWSER_TESTS
node scripts/sync-navigation.mjs --check
npm test
npm run check
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/test_navigation.py tests/test_application.py tests/test_nexus.py tests/test_navigation_history.py tests/test_system_portability.py

# In G:/AureateEmpyrean/mnemosyne, with the same temporary PYTHONPATH:
npm test
npm run check
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
```

For a manually run local Nexus, set `NEXUS_NAVIGATION_HISTORY=1` on its process
and restart it using the usual local setup. Do not change production Compose or
Exodus configuration. To roll back, unset the flag/restart Nexus: new modules
detect the missing advertisement and use their legacy navigation; old bootstrap
links still work. An old host cannot reconstruct new internal state, as documented
in the original compatibility plan.

## Changed files for this task

Paths below are relative to each repository; unrelated pre-existing changes are
excluded from this list.

| Repository | Files | Purpose |
| --- | --- | --- |
| Nexus | `frontend/navigation-protocol.js` (new) | Shared host/client SDK, validation, handshake, history and checkpoints |
| Nexus | `frontend/router.js`, `frontend/app.js` | Envelope routing, opt-in bridge, incremental frame rendering, checkpointed routing and sign-out |
| Nexus | `backend/nexus/app.py` | Feature advertisement and independent disk-usage portability fix |
| Nexus | `scripts/sync-navigation.mjs` (new) | Explicit build-time adapter vendoring/check |
| Nexus | `package.json` | SDK regression/syntax checks |
| Nexus | `tests/navigation.test.mjs`, `tests/test_navigation_history.py`, `tests/test_system_portability.py` (new) | SDK/security/backward-compatibility, feature flag/auth, capacity checks |
| Nexus | `tests/navigation_pilot_runtime.py`, `tests/test_navigation_browser.py` (new) | Disposable real-app HTTP runtime and Playwright integration |
| Nexus | `docs/proposals/navigation-history/README.md`, `VALIDATION.md`, `PILOT.md`, `pilot-evidence/chrome-results.json`, `pilot-evidence/mnemosyne.png` | Historical links, implementation record and browser evidence |
| Mnemosyne | `frontend/navigation-routes.js`, `frontend/navigation.js` (new) | Domain route codec, state restoration and draft recovery |
| Mnemosyne | `frontend/vendor/nexus-navigation.js` (new) | Exact shared SDK copy for inline bundling |
| Mnemosyne | `frontend/app.js`, `backend/mnemosyne/app.py` | Opt-in routing hooks, editor/session safety and inline script bundling |
| Mnemosyne | `tests/frontend.test.cjs`, `tests/navigation-routes.test.cjs` (new), `package.json` | Legacy frontend regressions with the real bundle and codec/syntax checks |

## Rollout decision

**Ready for controlled local pilot use behind the default-off flag. Production
rollout is not signed off.** Required user-requested local flows pass with real
apps. Other modules have not been migrated. Remaining production gates from the
approved plan are Firefox/WebKit, physical mouse hardware, BFCache behavior,
container-broker/image lifecycle and authenticated deployment-environment testing.
The unrelated Windows SVG pytest fixture issue also prevents a completely green
full Nexus suite on this machine. No automatic deployment has been initiated.
