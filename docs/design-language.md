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
