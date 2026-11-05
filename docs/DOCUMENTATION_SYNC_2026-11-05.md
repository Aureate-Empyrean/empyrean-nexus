# Nexus documentation synchronization — 2026-11-05

Documentation-only review of the current Nexus/Mnemosyne working trees. Only
Markdown was edited: no source/configuration/test-file changes, runtime test
reruns, deployments, Git commits or pushes. Zeus and Dev Orchestrator were not edited.

## Ownership and scope

This task owns the Markdown changes listed below. The central
`G:\AureateEmpyrean\architecture` repository is **read-only for this task**, as
requested; another agent owns its implementation updates. Existing/concurrent
changes were preserved using contextual patches, not file resets or whole-file
replacement. Concurrent edits were observed in central architecture files and
Nexus `docs/ports.md`; those edits are not attributed to this task.

The review inspected the actual shared SDK, shell router/render/refresh/auth
hooks, server feature advertisement, Compose environment, sync script, Mnemosyne
codec/adapter/HTML bundling, regression sources and recorded browser evidence.
The conclusions concern local working-tree code, not released/deployed images.

## Documentation changed by this task

Paths are relative to each repository.

| Repository | Files | Change |
| --- | --- | --- |
| Nexus | `README.md` | Pilot status, default-off flag, Compose activation caveat and entry points |
| Nexus | `docs/navigation-history.md` (new) | Current contract: activation/rollback, URLs, iframe lifecycle, wire/API details, adoption, draft/security limits and evidence/gates |
| Nexus | `docs/architecture.md` | Implemented full-application infrastructure, SDK/test map, frame ownership and tab-storage boundary |
| Nexus | `docs/application-infrastructure.md`, `docs/module-protocol.md` | Existing bridge vs opt-in navigation, discovery, packaging, manifest compatibility and current browser/container contract |
| Nexus | `docs/api.md`, `docs/security-model.md` | System vs bridge context, message/auth separation, readable private checkpoints and actual gateway body-size exception |
| Nexus | `docs/ui.md`, `docs/lifecycle-and-recovery.md` | Traversal/frame behavior, recovery UI, lifecycle guard limits and saved data vs checkpoint removal |
| Nexus | `docs/development.md`, `docs/deployment.md` | Real-app test prerequisites and scope, process-level flag activation, missing Compose forwarding and rollback |
| Nexus | `docs/IMPLEMENTATION_PLAN.md` | Dated local pilot checkpoint, recorded tests, Windows portability fix and open gates |
| Nexus | `docs/proposals/navigation-history/README.md`, `docs/proposals/navigation-history/PILOT.md` | Historical/current distinction; corrected lifecycle, API-call and draft-safety overclaims; pointer to current guide |
| Nexus | `docs/DOCUMENTATION_SYNC_2026-11-05.md` (new) | This change inventory, discrepancy record and central-architecture handoff |
| Mnemosyne | `README.md`, `docs/EXPERIENCE.md` | Local navigation entry point and accurate traversal/save-safety qualifications |
| Mnemosyne | `docs/NAVIGATION_HISTORY.md` (new) | Actual codec coverage, legacy links, SDK ownership, checkpoints/conflicts and validation limits |

The original synthetic `VALIDATION.md` and recorded JSON/image evidence remain
historical artifacts, not rewritten results from this documentation task.

## Discrepancies resolved or made explicit

| Finding from code/document comparison | Documentation resolution |
| --- | --- |
| Main docs did not expose the implemented pilot, while the proposal still read as only a design/prototype | Current guide and README/checkpoint links distinguish local implementation, old fixture evidence and production rollout |
| `NEXUS_NAVIGATION_HISTORY` is read by the backend but is not in `compose.yaml` or `.env.example` | Flag must reach the real process; `.env` alone cannot enable a container; no config file changed |
| Older architecture/protocol wording deferred persistent/full applications to future work | Existing `ui.application`, `storage.data` and inline opaque bridge are documented as implemented opt-ins |
| Manifest routes, gateway bootstrap `path`, and internal route references were conflated | Separate grammars/roles, version negotiation and no new manifest field are explicit |
| Bridge docs covered module-ID switching but omitted the navigation extension | Separate channel, SDK callbacks, probe/session/revision messages, checkpoint/leave messages and actual limits documented |
| Pilot wording said URLs never cause module API calls | Corrected: Nexus never fetches the route as an API/proxy target; a module normally uses its API to resolve/render it |
| Lifecycle refresh was described as checkpointing before stopping the application | Corrected: browser UI checkpoint is not a transaction delaying a server-side lifecycle action |
| Save-safety language implied an unconditional guarantee | Asynchronous checkpoint acknowledgment, SPA vs full-document leave, quotas/crashes, cleanup and recovery failure states are qualified |
| Shared SDK alone could be mistaken for draft safety or successful rendering | `beforeLeave` is a no-op unless supplied; `navigate()` can resolve after `apply` reports an error, so visible/onError state matters |
| Generic host fragments could be mistaken for Mnemosyne support | Mnemosyne rejects inner fragments; its accepted UUID/view/query grammar and current normalization limitations are listed |
| Gateway documentation still stated a universal 64 KiB body limit | Ordinary owner 64 KiB vs gateway/blob 2 MiB exceptions now match `BodyLimit` |
| Saved module volumes and unsaved browser copies had indistinguishable deletion wording | Uninstall retains saved module data but removes the tab checkpoint; sign-out has a dirty-copy warning, uninstall does not add that separate warning |

## Recorded validation, not a new runtime run

The implementation's checked-in [browser evidence](proposals/navigation-history/pilot-evidence/chrome-results.json)
contains 16 scenarios for actual Nexus + Mnemosyne + unchanged Chronos over local
HTTP on Chrome 157.0.8103.39 / Playwright 1.64.1. The container broker alone was
replaced by a disposable process launcher. It covered requested Notes/Tasks/detail
Back/Forward, synthetic Mouse4/5, switching, deep links/reload and draft/conflict
flows. It is neither merely a synthetic iframe fixture nor a production Docker
deployment test.

Recorded test counts are 24 Nexus frontend/SDK, 13 Mnemosyne frontend/codec,
46 affected Nexus backend and 30 Mnemosyne backend passes. The full Nexus run
recorded 200 passes, an opt-in browser skip, and two Windows setup/teardown errors
from an oversized SVG parameter exceeding pytest's environment-variable limit.
The separate `shutil.disk_usage` portability fix and former locale test passed.
Timezone-data requirements and the existing Starlette/httpx warning are retained
in the implementation record. No suite is claimed rerun for documentation sync.

Documentation QA checked **18 Markdown files and 94 local link/anchor targets**:
zero missing targets/anchors or duplicate headings. Scoped diff whitespace checks
passed. A 300-file initial hash snapshot showed **zero non-Markdown changes**
during this synchronization. Seven existing central Markdown files changed
concurrently; this task performed no writes there. Existing source changes from
the implementation are preserved, not attributed to this documentation task.

## Central architecture handoff — recommendations only

Re-read these shared files before patching: concurrent edits are in progress.
Do not replace their existing work or promote a local implementation into an
ecosystem-wide/production decision. Exact wire specifications belong in Nexus's
[current guide](navigation-history.md), not duplicated across central files.

| Exact file path | Recommended change for the owning agent |
| --- | --- |
| `G:\AureateEmpyrean\architecture\architecture.md` | Under Application boundary, distinguish module-owned domain routes from Nexus-owned top history/opaque-frame lifecycle. Add a dated local-pilot implementation note and implementation-spec link; qualify illustrative `/modules/mnemosyne/` and entirely Open embedding/switcher wording against actual `/app/modules/<id>` + gateway separation. Preserve independent-client exceptions and planned long-term scope. |
| `G:\AureateEmpyrean\architecture\modules\nexus.md` | Add the default-off local shared navigation/deep-link pilot, iframe/session fencing, module adoption boundary and non-authoritative tab draft copies. Keep actual wire/activation details linked to Nexus and state that production rollout is unvalidated. |
| `G:\AureateEmpyrean\architecture\concepts\module-contract.md` | Replace the stale reference to implementation “protocol version 0” with the actual Module Protocol v1 reference. Add opt-in browser version discovery as a separate local extension, not a mandatory manifest field/grant; distinguish planned contract responsibilities from implemented wire forms. |
| `G:\AureateEmpyrean\architecture\modules\mnemosyne.md` | Add a dated pilot note near Integrations/Navigation: workspace/resource views restore through host history; module retains codec/autosave authority. Link the Mnemosyne navigation doc and qualify tab-local draft recovery vs durable saves/backups. Preserve conceptual future scope and status vocabulary. |
| `G:\AureateEmpyrean\architecture\README.md` | Add a dated implementation pointer for the default-off local pilot to current direction/reading links, without implying release, migration of all modules or production deployment. |

## Remaining documentation and rollout gaps

* Central navigation synchronization is delegated above and was not implemented
  here. Any future central concept/ADR should be reviewed by that owner, rather
  than assigning an uncoordinated ADR number in this task.
* Production gate evidence is still absent for other browsers, physical mouse
  hardware, BFCache, real container/image lifecycle, expiry/relogin and deployment
  proxy/auth/CSP behavior. Quota/timeouts, live disable/removal and rapid traversal
  under slow APIs have not all received real-app browser sign-off. The docs mark
  these as open, not completed.
* The SDK/wire and Mnemosyne snapshot/codec remain local pilot contracts, without
  a separately released SDK package or published JSON Schema. The vendor sync
  script is fixed to Mnemosyne. A new module requires its own integration review,
  fallback, recovery policy and regression evidence.
* Operational Compose activation is a known configuration gap, not fixed by a
  docs-only change. Broader deployment environment state was not inspected, so no
  claim is made about what another deployment may currently have enabled.
* Outside this navigation-only Mnemosyne edit scope, its README/EXPERIENCE
  typography text still says gateway data fonts are blocked, while Nexus already
  permits `font-src data:` and Mnemosyne embeds its font. A separate typography
  documentation pass should reconcile that historical text.

Status: documentation reflects the implemented local pilot. Production rollout
and the central-architecture handoff remain separate work; no deployment or
source behavior was changed.
