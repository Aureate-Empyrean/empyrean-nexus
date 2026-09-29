# Control-panel navigation and motion

The operational UI has three primary destinations: Overview, Modules and Activity. Activity is backed by actual audit records, including lifecycle attempts/completions/failures and on-demand health changes. No event fixtures, product marketing or architecture tutorial fills empty screens. Settings lives in the bottom utility area, followed by the installed version.

The brand control opens an application switcher. It includes Nexus, enabled installed modules and Manage modules. Modules are never appended to Nexus's sidebar. A module view has its own route and sandboxed content; richer module-internal navigation remains the module's responsibility within the supported hosting contract.

`frontend/router.js` uses normal links, pushState and popstate. Known UI routes live under `/app/`; direct loading returns the same SPA entry document. API/gateway paths are not swallowed by a global fallback. Utility routes participate in the same history; modal/version panels are transient UI. Refresh preserves the route, and normal browser Back/Forward (including mouse buttons) re-renders it. Unrecognized application routes show a not-found view.

The top-bar notification button opens a dismissible recent-notification panel, refreshes real notification data and exposes unread state. A non-primary `/app/notifications` history route shows the retained recent records. Mark-read is explicit. Escape and outside click close the panel; normal browser controls remain available.

`system.update` currently reports `not_checked` with discovery unsupported. The UI only renders the sidebar update card for `status: available` plus an available version different from the installed one. An eventual provider may also supply `url`, `published_at` and plain-text `notes`. The card and version item open the same release panel. No download or update runs from these controls. A current status is shown only if supplied by a successful future check, never inferred from absence of release data. Actual discovery, manifest diff/review and an explicit installation workflow remain future work aligned with the ecosystem update policy.

Motion lives in `frontend/motion.js` and shared CSS tokens: fast 140 ms, normal 200 ms, slow 260 ms, with a common easing curve. Entrances use opacity and a small translation; state feedback uses a brief restrained background highlight. Stagger is capped at 100 ms. Actions start immediately; controls indicate real pending work, and success/error states follow actual responses. Loading animations only run during pending work, never as ambient decoration. Newer transitions cancel older ones. Native dialogs/controls retain focus semantics, and reduced-motion preference removes movement and looping indicators.

DOM/logic tests are distinct from a real browser visual check. The verification checkpoint records what was actually available in the implementation environment.
