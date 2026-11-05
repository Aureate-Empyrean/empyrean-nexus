# Aureate Empyrean product design language

This records the product design language first established by the Mnemosyne redesign and now applied to Nexus. It describes principles, not a component library. Each product keeps its own workflows, layout and accent; what they share is how they feel and behave. The canonical ecosystem design system (tokens, module accents) is in the architecture repository (`concepts/design-system.md`); this document is the implementation-level interpretation for current products.

## Principles

- **Workflows, not schemas.** Screens follow what a person is trying to do — write, complete, install, review, recover — rather than the shape of the stored records. Raw identifiers, manifests and codes exist, behind explicit technical details.
- **Premium, dark, desktop productivity.** The shared black/graphite foundation, dense but calm. Hierarchy comes from typography and spacing, not boxes. Few cards, restrained hairline borders, no dashboard-card syndrome, no generic SaaS or admin-panel look.
- **One dominant action per surface.** Contextual controls sit next to what they affect. Rare and destructive actions live in overflow menus and confirmations, never as permanent red buttons.
- **Progressive disclosure.** Summaries first; details in drawers, disclosures and inspectors. Drawers are used where spatial continuity helps: the list stays visible and the selected item stays marked.
- **Clear state.** Selected, focused and active states are unmistakable (accent tint plus a thin accent rule, visible focus rings). Status is described in words people use ("Running", "Not responding"), with the reason and the next action nearby.
- **Immediate and truthful.** Controls react at once; state shown is state confirmed. Pending work is labelled as pending. Nothing fakes progress or success. Errors keep their real message.
- **Excellent empty and error states.** Empty states say what the thing is and offer the one useful action; calm is a valid state. Errors explain and offer recovery.
- **Keyboard first-class.** Lists move with arrow keys, Enter opens, Escape closes the top-most layer and returns focus to where it came from, menus take arrow keys, and there is a global shortcut for the main switcher.
- **Restrained brand moments.** Poster typography and the product mark appear on first run, sign-in, splash and the wordmark — not on working screens.

## Accent identity

Each product has one accent family on the shared neutrals, used for identity and interaction emphasis only: active navigation, selection, focus, primary actions, key status. Not for backgrounds everywhere.

| Product | Accent | Light | Deep |
|---|---|---|---|
| Nexus (Aureate Empyrean) | `#D6AD60` gold | `#F0D58A` | `#8C6734` |
| Mnemosyne | `#8B7CF6` violet | `#B7AEFF` | `#5B4FC4` |

Resource colors chosen by users are separate from product accents. Status colours (healthy green, attention red, warning amber) are separate from the accent too.

## Composition (design system 2.1)

Since Nexus 0.1.6 and Mnemosyne 1.2.1 both products carry the token set 2.1 materials (architecture ADR 0012, ADR 0014) as a composition layer at the end of their stylesheet. The local components, markup and workflows stay; their appearance is superseded. Nexus 0.1.7 and Mnemosyne 1.2.2 refine it against "bubble UI":

- **Two materials only.** *Structure* for ordinary content: a quiet, nearly opaque panel with hairline rows, no blur and no float shadow. *Lens* for what navigates or floats (command bar, rail, toolbar, menus, the application switcher, drawer, dialogs, toasts): a specular sheen from the top left, edge light (inset highlights, bottom shade, a hairline outer separation), a deep blur with reduced brightness, and a tint dark enough that text behind it dissolves into colour. Small floating layers add a masked specular rim; layers that scroll use edge light instead, because a masked ring would scroll with the content.
- **No cards inside surfaces.** A panel holds rows separated by hairlines, not a card per row. Status is a lit dot and a word, versions are plain metadata, and pills are kept for counts and tags.
- **One radius scale.** Controls 9 px, groups 12 px, panels 16 px, floating glass 18 px.
- **Application tiles (0.1.8).** Each module owns its icon (manifest `icon`, served by the module); Nexus draws every tile at one size per context (32 px in the switcher, 38 px in lists, 48 px in the drawer) with the same radius and edge light, and a neutral letter tile when there is no icon. The Nexus gold mark is Nexus's own.
- **Backdrop roots.** An element with `backdrop-filter` (or `filter`, `opacity` below 1, `mask`) becomes the backdrop root of everything inside it, and a descendant's blur then sees only that element. Floating glass must never sit inside another glass element: the command bar keeps its glass on `::before`, so the switcher and menus inside it blur the page or module behind them. A masked rim on the bar itself produced compositing seams around its controls, so the bar's rim is edge light.

- **Nexus — command center.** Restrained golden illumination from above with a cool counter-light and faint orbit rings; a floating lens command bar whose navigation is words with one gold light under the current place; the overview status (state orb, headline, one line of facts) reads straight off the atmosphere; modules and recent activity share one structural panel divided by a hairline; platform facts are columns divided by hairlines; the Modules page is one panel with a row per module. Drawer, dialogs, menus, the application switcher, notifications and toasts float as lens glass. Full-window applications hide the atmosphere so the module owns the window.
- **Mnemosyne — lamplight.** A dim violet dusk with one warm amber lamp. The sidebar and toolbar float as glass; the work sits on an elevated, nearly opaque sheet, so long-form reading and writing get no blur, glow or gradient behind the text. Inside the sheet nothing is glass: task lists, recent items and board columns are quiet hairline groups, project headers are open, and the formatting bar is icons above a hairline. Glass is reserved for navigation and floating layers.
- Glass becomes solid without `backdrop-filter` support and under `prefers-reduced-transparency: reduce`. Text never sits on glass lighter than `--surface-glass`.

Before/after screenshots: Nexus `docs/screenshots/`, Mnemosyne `docs/screenshots/` (Playwright Chromium, 1440 px and 390 px).

## Typography

- **Roboto** for all functional text: navigation, body, controls, inputs, status, metadata, dialogs, notifications, user and localized content. No Inter, Geist or other generic dashboard faces.
- **Greater Theory** only as an optional poster face for fixed uppercase brand strings whose glyphs are known in advance (`AUREATE EMPYREAN`, `EMPYREAN NEXUS`, `MNEMOSYNE`). Never for headings, sentences, localized or dynamic text. Never bundled unless its licence allows it; products detect a local copy and are complete without it.
- Nexus serves Roboto itself (same-origin, allowed by its policy). Sandboxed modules cannot load fonts under the module content security policy, so they use Roboto when it is installed on the viewer's system; that limitation is documented rather than worked around by weakening the policy.

## Motion

Motion is part of the interaction language: it shows where something came from, where it went, what changed and what has focus.

- About **120 ms** for micro feedback (hover, press, small state), **180 ms** for ordinary transitions (tabs, lists, menus, disclosures), **200–240 ms** for larger spatial moves (drawers, inspectors, page changes).
- Ease-out for entering, ease-in for leaving; opacity with small translations; a gentle spring only for tactile confirmations (a checkbox).
- Lists insert by expanding and remove by collapsing; moved items glide (FLIP).
- Drawers, menus, dialogs and toasts each have one consistent motion.
- Motion follows the action and never delays it; operations are not shown as finished early.
- `prefers-reduced-motion: reduce` removes movement and looping indicators; everything still works.
