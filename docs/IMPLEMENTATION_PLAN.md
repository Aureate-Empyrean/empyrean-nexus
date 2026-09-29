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
