# Empyrean Nexus implementation checkpoint

Target: a single-owner Docker-first foundation, not a domain application.
License decision: AGPL-3.0-or-later, explicitly selected by the owner.

1. Establish FastAPI/SQLite migrations, claim-protected setup and session authentication.
2. Define strict protocol v1 and reserved-port registry.
3. Implement constrained Docker broker, lifecycle, authenticated gateway and scoped events.
4. Build the neutral charcoal/gold dashboard and independent reference container.
5. Verify security-sensitive contracts, integration, Docker deployment and UI.
6. Finish contributor, deployment, protocol and security documentation.

See architecture.md and adr/ for decisions. Completion and limitations will be recorded here after verification.

## Verification checkpoint — 2026-09-29

Implemented all six planned stages. V1 is an initial, unaudited foundation with the boundaries described below.

Verified:

- 40 pytest checks pass: strict manifest/runtime input validation, compatibility, reserved ports, setup/session security, CSRF/origin protection, rate limits, explicit grants, token revocation, event filtering/cursors, notifications, export exclusions, migrations, failure recovery and broker policy.
- Ruff lint and formatting checks pass for backend, reference module, tests, scripts and deployment Python.
- JavaScript syntax check passes; Compose configuration validates.
- Nexus, broker and reference images build successfully.
- Actual Docker integration passes using an isolated disposable installation: setup, logout/login, manifest review/install, enable, health, gateway HTML, module context API, event publish/consume, notification, forced Nexus recreation/reconnection, disable, uninstall, and healthy Nexus afterward.
- The disposable test installation and its volumes were removed. The normal `nexus` stack remains on loopback port 12333, awaiting the owner's first-run setup. No test credentials were installed there.
- Full upstream AGPL-3.0 license text is included; README explicitly selects AGPL-3.0-or-later. Branding is separate and forks are legitimate.

Findings resolved during verification:

- Quoted Compose tmpfs strings to prevent commas becoming separate mount entries.
- Reconnected existing module networks on gateway recreation and revoked tokens for missing runtimes.
- Rejected image-declared volumes and used resolved image IDs after image inspection.
- Added a broker-only SELinux label exception for the daemon socket on the test host. Nexus/modules retain normal labels. This root-equivalent controller boundary is documented; a custom audited SELinux policy is future hardening.
- Removed generic gateway operations from generated OpenAPI to avoid duplicate operation IDs; its contract is documented separately.

Known verification limits / deferred scope:

- Browser visual/interactive QA could not run: the computer-use tool reported no available browsers or apps. Frontend delivery and JavaScript syntax were checked, but responsive layout/accessibility/CSP interactions still need real-browser review.
- TestClient emits a dependency deprecation warning about its httpx compatibility path; tests pass. No runtime warning is suppressed.
- The current release has no security audit, password recovery UI, persistent module storage, general module SPA hosting, background health scheduler, automatic update/discovery/install provider, signed provenance, multi-user permissions or automated restore.
- Only one Uvicorn worker is supported. Metadata export is not a restorable backup. Runtime containers are outside Compose's service list; disable modules before taking the installation down.

Repository initialized on branch `main`; no remote was configured and no release was published. Final live read-only check returned healthy Nexus, HTTP 200 for the frontend/JavaScript, and `setup.required=true`.

## LAN/origin fix — 2026-09-29

Fixed setup rejection when accessing the default installation through 127.0.0.1 instead of localhost. Loopback aliases are accepted on the configured scheme/port; additional origins use an explicit comma-separated allowlist. Unknown origins and opaque module origins remain rejected. Local `.env` now publishes the gateway on host interfaces and permits this server's LAN address, http://192.168.100.32:12333. Existing database/account/claim token are preserved. Added regression tests for setup through allowed addresses and rejection of unrelated origins and mixed cookie-security schemes.

## Interoperability and UI follow-up plan — 2026-09-29

1. Add an opt-in Entity References v1 extension, strict resource identities and scoped capabilities; preserve existing manifest compatibility.
2. Add migration 2: indexed relationships plus per-enabled-module resolver credentials. Owners retain domain data; references survive runtime/module removal.
3. Implement authenticated resolution, forward/backlink queries, creator-owned updates/removal and scoped event integration; test denied paths and lifecycle behavior.
4. Replace control-panel filler with real state; route Overview/Modules/Activity/Settings/module views using History API and server SPA fallbacks.
5. Build top-bar notification center, bottom Settings/version utility area, conditional release card and a separate ecosystem switcher.
6. Add shared motion tokens/primitives, progress feedback, reduced-motion support and actual request states. No fake updates or activity.
7. Verify contracts, Docker reference interactions, route loading and browser behavior where available, then update documentation/checkpoint.

## Completed follow-up — Nexus 0.1.1, 2026-09-29

Architecture source inspected: `Aureate-Empyrean/architecture`, commit `2f4f018`, including the requested cross-module-reference, architecture, interoperability and Nexus documents. The central correction from that source is enforced: owning a target does not reveal its backlinks. Normal indexed relationships are private to their creator unless readers are explicitly named. Type scopes and edge visibility are separate checks; pagination and internal reference events preserve this boundary.

Delivered:

- Optional Entity References v1 extension with strict stable identities, generic source-owned relationships, outgoing/backlink queries, scoped authenticated resolution and explicit unresolved states. No domain objects, official-module special cases, graph infrastructure or direct database sharing.
- Transactional migration 2; relationships survive disable/uninstall/failure. Reinstall of endpoint identities or retained reader grants requires explicit identity-reuse consent. Resolver credentials are separate, rotated and excluded from exports/inspection.
- Reference-event hints use the existing bounded event log and current sharing authorization. The platform event namespace cannot be impersonated by modules, including legacy registrations.
- Routed Overview/Modules/Activity/Settings/module views with pushState/popstate and server-side SPA fallback. Primary sidebar contains only Overview, Modules, Activity. Settings and version are bottom utilities. The separate application switcher lists only real enabled modules.
- Top-bar recent notifications and unread state, explicit mark-read, and a non-primary notification history route. Activity reads actual audit records with pagination and health/recovery activity.
- Conditional sidebar update card and shared release panel; no fake update discovery, up-to-date claim or install action. Operational filler and the Guide destination are removed.
- Reusable motion tokens/primitives, controlled entrances/state feedback, dialog/popover/section transitions, tactile controls, actual pending indicators and reduced-motion support. Frontend has no runtime package dependencies; DOM tooling is development-only.

Final verification:

- **81 backend tests passed**, including private backlink existence/pagination, sharing revocation, resolver auth/output validation, platform-event spoof prevention, migration and legacy manifest compatibility.
- **8 frontend logic/DOM tests passed**, including real link rendering, Back/Forward, direct routes, notification interaction, separate utilities/switcher, honest release states and reduced motion.
- Ruff lint/format, JavaScript syntax, documentation links and Compose configuration passed. Final images built.
- Final isolated Docker test passed: original auth/lifecycle/event vertical slice plus two independent containers, private/shared backlinks, authenticated owner resolution, forbidden browser resolver impersonation, retained references after target disable/uninstall, Activity, application routes and gateway recreation. Its temporary resources were removed.
- Before deployment, a consistent mode-0600 SQLite backup was saved in the private data volume at `/data/backups/nexus-before-0.1.1-20260929T180740Z.sqlite3`.
- Live deployment runs 0.1.1/schema 2. One administrator and one enabled module were preserved; the existing module's internal health endpoint returned HTTP 200.
- Read-only live probes confirmed health, direct route loading and accepted configured origins on both 127.0.0.1:12333 and 192.168.100.32:12333. An unrelated origin still receives HTTP 403. These are server-side reachability checks, not a test from a second physical LAN device.

Remaining boundaries:

- No connected browser/app surface was available for visual QA. DOM/logic checks do not replace real-browser layout, CSP and assistive-technology review.
- The reference index is normal protected installation metadata, not an encrypted secrets index. Multi-user policy, protected backlinks, merge aliases, automated repair/rebuild/import and federation are not implemented. See cross-module-references.md for exact limits.
- No automatic updates, expanded permissions for existing modules, persistent module storage or general-purpose module SPA hosting was introduced. Existing installed manifests were preserved.
- The dependency TestClient deprecation warning remains visible; no test/runtime errors were suppressed.

## Architecture alignment audit — 2026-09-30

Audited against the hardened ecosystem architecture (`Aureate-Empyrean/architecture` commit `2fbfe12`). Nexus remained domain-ignorant and already matched the lifecycle rule that uninstall never deletes module data.

Changed:

- Startup reconciliation now revokes credentials of enabled modules whose declared Nexus range excludes the running version (state `error`, health `incompatible`, audit and notification) instead of letting them keep API access after a Nexus upgrade.
- The uninstall review no longer claims container data is disposable for modules with `storage.data`; it states that their data volume is retained.
- Documentation: 0.1.2 status, UUID resource identity requirement, mapping of v1 availability values to the architecture's resolution states, and the module-contract gaps (outgoing-reference enumeration, blob usage reporting, export/restore participation) that remain unimplemented.

Verified: 90 backend tests, 9 frontend tests, Ruff lint/format and JavaScript syntax checks. The Docker smoke test was not run: its image build would retag the images used by the live installation on this host.

## Lifecycle and recovery hardening — Nexus 0.1.3, 2026-09-30

- Bridge `external` navigation now requires owner approval of the exact parsed address in a Nexus dialog; module clicks can no longer open arbitrary URLs.
- Entity References v2: UUID resource IDs enforced for v2 owners; outgoing-reference enumeration and owner-triggered reconciliation that never removes edges on failure.
- Backup v1 contract (export/validate/restore/finalize) with purge suspension, blob carry-over, identity checks, reconciliation after restore and explicit `failed`/`needs_attention` states.
- In-place module updates with a capability diff, exact grants, backup hook, health verification and honest failure without claimed rollback.
- Reference module is development-only by default (`NEXUS_ALLOW_EXAMPLE=0`), uses a UUID resource and enumerates its references. Compose image tags moved to `empyrean-nexus:0.1.3` / `empyrean-example:0.1.2`, so building does not retag images of an existing 0.1.2 deployment.

## Verification of 0.1.3 and the redesign (f25919b) — 2026-10-16

Run on a fresh clone in throwaway `python:3.12-slim` and `node:22-slim` containers (the host has no venv or Node).

- 154 backend tests, 18 frontend tests, Ruff lint/format and JavaScript syntax checks passed.
- `scripts/docker_smoke.py` passed against freshly built `empyrean-nexus:0.1.3` / `empyrean-example:0.1.2` images. Its stack and volumes were removed. No live installation existed on this host, so no images in use were retagged.
- Mnemosyne 1.1.0 (references v2 + enumeration, backup v1) passed its disposable integration test against this build: reconciliation, backup, confirmed restore with validate/reconcile/finalize, rebuilt index. Nexus needed no changes.

Still open: real-browser QA of the redesign. The previous live installation (owner, modules, data volumes, `/data/backups`) is no longer present on this host. (Browser QA followed with 0.1.4, below.)

## Shared design tokens — Nexus 0.1.4, 2026-10-16

Architecture ADR 0008: one canonical token file, vendored by every application. `frontend/aureate-tokens.css` is that file unchanged; `style.css` keeps only Nexus specifics (display face, drawer width) and uses the shared names (`--accent*` instead of `--gold*`, `--danger*` instead of `--bad*`, `--surface-1`, `--motion-base`, `--ease-out/--ease-in`). Values are unchanged apart from the canonical shadow and hover alpha. Module applications now receive `font-src data:` so they can embed the shared Roboto face; they still have no network access. A test keeps every used token defined and the token file loaded first.

Real-browser QA (Playwright Chromium, live LAN installation, 0.1.4 with Mnemosyne 1.1.0): Overview, Modules, module detail, Activity, Settings, Notifications at 1440 px, and Overview/Modules at 390 px. Zero page or console errors, no horizontal overflow, gold accent and bundled Roboto from the shared tokens. Mnemosyne's full-window application was exercised through Nexus by Mnemosyne's own browser QA. An in-place module update and owner reconciliation ran on the live installation.

Finding (not fixed): the first enable of a slow-starting module records "stopped responding" before "is healthy", because the initial health check can run before the container listens. Consider retrying the first check before reporting a failure.

## Navigation History — implemented local pilot, 2026-11-05

The current working trees include the shared host/client navigation SDK and the
first Mnemosyne adapter. Default is off; activation requires
`NEXUS_NAVIGATION_HISTORY=1` in the actual Nexus process, plus the matching host
and module builds. Compose does not currently forward the flag. No production
deployment or all-module migration was performed.

The [current integration contract](navigation-history.md) documents host-owned
history, additive internal-route URLs, incremental iframe lifecycle, per-load
challenge/session/revision fencing, tab-local draft checkpoints, leave guards,
old-host/module fallback and adoption requirements. A separate cross-platform
disk-usage fix resolved the Windows `os.statvfs` failure.

Recorded implementation validation: 16 real-app Chrome scenarios; 24 Nexus and
13 Mnemosyne frontend tests; 46 affected Nexus backend tests; 30 Mnemosyne backend
tests. Full Nexus run: 200 passed, one opt-in browser test skipped, two existing
Windows oversized-SVG pytest fixture errors. See [PILOT.md](proposals/navigation-history/PILOT.md)
for evidence, environment qualifications and remaining rollout gates. These
counts describe recorded runs, not a new full-suite run for documentation sync.

## Icon cache and status mark — Nexus 0.1.9, 2026-11-03

- Module icons are now a validated, Nexus-owned copy (`backend/nexus/icons.py`, `docs/module-protocol.md`), so a module keeps its icon while stopped or unreachable and across Nexus restarts; previously the browser loaded it live through the gateway and showed a letter whenever the module was not running. Files live in the data volume (`module-icons/`); no database migration. Tests: `tests/test_icon_cache.py`.
- Overview status: the glossy, glowing orb is a flat ring and check in the muted status colours (warning and error keep theirs).
- Nexus mark in the switcher: its wrapper tile carried the bar tile's 6 px padding while the SVG kept a 26 px size, so the drawing overflowed its 20 px box by 6 px and sat 3 px right and 2.4 px low (and 30 % larger than in the bar). The wrapper now has no padding and the SVG draws 20 px, the same as in the bar; the artwork itself is centred in its viewBox, so no optical offset is applied.

## Application icons — Nexus 0.1.8, 2026-11-03

Modules can declare `icon` (a path they serve, `docs/module-protocol.md`, *Nexus 0.1.8 addition*); Nexus loads it through the owner-only module gateway as a same-origin image, so its policy (`img-src 'self'`) and the module sandbox are unchanged. Module tiles in the switcher, Modules, Overview and the drawer use it, with a neutral letter tile while a module is not enabled or when the image fails. Previously every module showed a gold letter because the manifest had no icon concept and `monogram()` rendered the name's first letter. Chronos 0.1.1, Lyra 0.1.1 and Mnemosyne 1.2.3 serve their own tiles at `/icon.svg` and require `>=0.1.8`.

Switcher geometry: the panel overlapped the bar by 6 px (4 px on phones), because its offset (`top: 54px`) was measured from a container 60 px tall; its icon column started 12 px right of the trigger's mark; and the Nexus glyph (32 px) and module tiles (38 px) differed, so rows were 52 and 56 px tall and the name column drifted. Now the panel hangs 8 px below the bar on the bar's left edge, all tiles are 32 px under the trigger's mark, names share one column, and the shortcut, check mark and chevron share one right edge, at 1440 px, in application mode and at 390 px. Also fixed: the Overview glow widened the page to 452 px on a 390 px phone.

## Interface refinement — Nexus 0.1.7, 2026-11-03

Presentation only. The composition layer in `frontend/style.css` was rewritten around two materials (structure and lens) and one radius scale; see `docs/design-language.md`, *Composition*. Fixed: the application switcher, notifications and account menu let the active module show through unblurred, because the command bar's own `backdrop-filter` made it their backdrop root; the bar's glass now lives on `::before`. No API, schema, protocol, sandbox or data change; markup and the frontend tests are unchanged.

Real-browser QA (Playwright Chromium, `aetest` with Chronos 0.1.0, Lyra 0.1.0, Mnemosyne 1.2.2): Overview, Modules, module drawer, install dialog, Activity, Settings, notifications, sign-in, and the application switcher over Nexus, Chronos and Lyra at 1440 px; Overview, Modules, sign-in and the switcher over Lyra at 390 px; the switcher and notifications over an injected white page and an injected high-contrast colour pattern with large white text. No page errors, no horizontal overflow. Screenshots: `docs/screenshots/` (`before-` original, `previous-` 0.1.6, `after-` 0.1.7).

## Design system 2.1 composition — Nexus 0.1.6, 2026-11-03

Presentation only: `frontend/aureate-tokens.css` re-vendored as token set 2.1, an atmosphere layer in `index.html`, and a composition layer appended to `frontend/style.css` (command center: status console, glass masthead, module cards, platform tiles, floating drawer, dialogs, menus and toasts; solid fallbacks without `backdrop-filter` and under `prefers-reduced-transparency`). No API, schema, protocol, sandbox or data change; markup and the frontend tests are unchanged.

Real-browser QA (Playwright Chromium, disposable `aetest` installation with Chronos, Lyra and Mnemosyne 1.2.1): Overview, Modules, module drawer, install dialog, Activity, Settings, notifications, application switcher, full-window application and sign-in at 1440 px; Overview, Modules and sign-in at 390 px. No page errors, no horizontal overflow; reduced transparency verified by media emulation. Before/after: `docs/screenshots/`.

## Egress and projection queries — Nexus 0.1.5, 2026-11-02

Driven by Chronos (iCalendar subscriptions) and Lyra (TMDB), per architecture ADR 0010 and ADR 0011.

- `network.egress` capability: per-module non-internal bridge attached only to that module's container; removed on disable/uninstall. Install review explains that destinations are not restricted.
- `projections` manifest declaration, `projections.read` capability and `POST /api/v1/module/projections/query`: exact scopes, resolver-key-authenticated forwarding to `POST /empyrean/v1/projections/<name>`, 4 KiB query, 1 MiB / 500-item response, 5 s, availability states, nothing stored.
- Both require a Nexus range excluding 0.1.4. Update review diffs projection scopes. Schema `capabilities.maxItems` raised from 10 to 16. No database migration; existing registrations and manifests are unchanged.
- Verification: 169 pytest (Linux container, Python 3.13) and 18 frontend tests pass; ruff check/format clean. New tests: `tests/test_projections.py` (forwarding contract, scope/capability denial, provider failure mapping, lifecycle states, manifest rules, update diff, broker egress attach/detach).
