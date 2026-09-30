# Control center experience

Nexus is the Aureate Empyrean control center: the place where you see whether the platform and its applications are healthy, install and change modules, and move between applications. It is designed around those workflows, not around the database or container runtime underneath. The shared principles behind it are in [design language](design-language.md).

## Structure

- **Masthead.** The Nexus mark and `EMPYREAN NEXUS` wordmark open the application launcher. Beside them: Overview, Modules and Activity, with a gold indicator that slides to the current page. On the right: an update notice (only when a real update is reported), notifications, Settings and the account menu (sign out).
- **Launcher** (`Ctrl/⌘ K`). Nexus plus every enabled module, each with its live status and version, then "Manage modules" and the release information entry. Modules are never appended to navigation.
- **Application mode.** An application (`ui.application`) takes the full window. Nexus steps back to a thin gold edge at the top; hovering it or moving keyboard focus into it slides the platform bar down, so the launcher and control center stay one gesture away without wrapping the application in chrome.
- **Module details** open in a drawer beside the Modules list. It pushes the list aside on wide screens and overlays it on narrower ones. Escape closes it and returns focus to the row.

`frontend/router.js` uses normal links, pushState and popstate under `/app/`. Refresh preserves the route; Back/Forward re-render it; unknown routes show a not-found view.

## Surfaces

- **Overview** answers "is everything all right?". A single status headline: healthy, a module changing state, or how many modules need attention. Modules that need attention are listed with a plain explanation and the relevant action. Below: the modules with their status and an Open action, the most recent activity, and a quiet platform summary (version, update discovery, free data space, database, protocol). When everything is healthy the page is calm; nothing is invented to fill it.
- **Modules** is a list, not a grid of cards. Each row shows the module, its description, a human status ("Running", "Stopped", "Not responding", "Needs attention", "Incompatible", "Starting…"), and one primary action (Open or Start). Everything else — health check, stop, update review, backup, uninstall — is in the row's menu or the details drawer.
- **Module details** explain what the module may do in plain language, with the capability code beneath each item; its events, cross-module scopes, data handling, trusted sites, update history and backups; and the raw manifest behind "Technical details".
- **Install** reviews a manifest before anything is registered: identity, self-declared publisher, the unverified-publisher warning, permissions in plain language, cross-module scopes, technical details on request, and the retained-identity confirmation when it applies. Granting is an explicit checkbox; the module is installed stopped.
- **Update review** (Nexus 0.1.3+) compares a pasted manifest with the installed one: version direction, new and removed permissions (new ones highlighted and requiring explicit approval), scopes, events, item types, image, port, Nexus range, data, migrations and restart consequences, and the backup policy. "Back up before updating" is on when a backup is possible. Downgrades require explicit confirmation.
- **Backups and restores** (Nexus 0.1.3+, modules declaring `backup`) list backups with download and restore. A restore explains what is replaced and requires an explicit confirmation. Backups that the installed version cannot restore are marked as such before anyone tries. A restore waiting for finalization is shown with its stage and a finish action.
- **Activity** is readable history grouped by day ("Mnemosyne started", "Hermes reported a problem"). A request whose outcome is already recorded is folded into that outcome; "Show event codes" reveals every record with its raw kind and subject.
- **Notifications** open from the bell with the unread count; "Mark all read" is explicit. The full history has its own page.
- **Settings** groups installation name and language, version and release information, metadata export, developer contracts and the account.
- **Sign-in and first run** use a restrained poster moment with the wordmark; the forms are unchanged in behaviour.

Features that need Nexus 0.1.3 (update review, backups, trusted-site management) appear only when the running backend reports version 0.1.3 or later.

## Honest state

Nothing shows success before the backend confirms it. While a lifecycle request is in flight the module shows "Starting…", "Stopping…", "Checking…" or "Updating…" and its controls are disabled; the final state comes from the refreshed module record. Errors keep the backend's message. Loading placeholders appear only while data is pending. `system.update` still reports `not_checked`; no update is discovered, downloaded or installed from these controls, and "Up to date" is shown only if a future check says so.

## Motion

Tokens in `style.css`: `--motion-fast` 120 ms (hover, press, small state), `--motion-normal` 180 ms (tabs, lists, disclosures, menus), `--motion-slow` 230 ms (drawer, application edge), with an ease-out curve for entering and an ease-in curve for leaving. `frontend/motion.js` holds the primitives: enter, directional slide between top-level pages, leave, stagger (capped at 96 ms), feedback highlight, collapse and expand for list removal and insertion, and a FLIP helper. A newer transition cancels an older one on the same element, and exit animations hold their end state only until the element is shown again. Motion never gates or delays a request. `prefers-reduced-motion: reduce` removes movement and looping indicators.

## Typography

Roboto is the interface typeface. It ships with Nexus (`frontend/fonts/Roboto.woff2`, a Latin and Latin Extended-A subset of the variable font, SIL Open Font License 1.1, see `frontend/fonts/OFL.txt`) and loads from `/assets`, which the existing content security policy already allows. Greater Theory is an optional poster face used only for the fixed `EMPYREAN NEXUS` and `AUREATE EMPYREAN` marks. It is never bundled; it is used only when installed locally and detected, and the interface is complete without it.

DOM/logic tests are distinct from a real browser visual check.
