# Empyrean Module Protocol v1

> For persistent full applications, the opt-in [0.1.2 infrastructure extension](application-infrastructure.md) supersedes the disposable-runtime limitations below.


Normative machine-readable schema: [`protocol/module-v1.schema.json`](../protocol/module-v1.schema.json). Working example: [`manifest.json`](../examples/example-module/manifest.json). Unknown fields are rejected at every object level. A manifest is UTF-8 JSON, limited by the 64 KiB API body limit. No executable installation hooks exist.

## Fields

| Field | Meaning and enforcement |
| --- | --- |
| `protocol` | Integer `1`; incompatible versions are rejected |
| `id` | Stable lowercase kebab-case identifier, maximum 48 characters; installation-unique |
| `name`, `description` | Plain-text display metadata, maximum 80/500 characters |
| `version` | Semantic Versioning 2.0.0 without build metadata (no leading zeros, no empty prerelease identifiers); updates compare versions by SemVer precedence |
| `publisher.name`, `publisher.originalAuthors` | Self-declared attribution; grants no trust badge |
| `repository`, optional `homepage` | HTTPS informational URI; never fetched/executed automatically |
| `license` | License expression identifying the module's terms |
| `nexus` | PEP 440 range, for example `>=0.1.0,<0.2.0`; **not** npm caret syntax |
| `container.image` | OCI image reference pinned as `registry/path@sha256:<64 lowercase hex digits>` |
| `container.port` | Reserved unique internal TCP port; see [allocation](ports.md) |
| `capabilities` | Requested grants from the closed list below |
| `routes.ui` | Absolute module path served when `/modules/<id>/` is requested |
| `routes.api` | Absolute API prefix, used by the API explorer |
| `routes.health` | Absolute endpoint returning HTTP 200 when healthy |
| `events.produces`, `events.consumes` | Exact event types; no wildcards |
| optional `release.url` | HTTPS release information for a future provider; informational in v1 |

Manifest route fields are simple absolute paths, not URLs, with no query, fragment,
escape sequence or parent traversal. The gateway forwards subsequent relative
paths to the same fixed container/port; it cannot target arbitrary hosts. Routes
declare entry points, not extra access control within a module. These fields are
distinct from the optional browser [navigation route reference](navigation-history.md#ownership-and-urls),
which may carry an internal query/fragment and is never used as a gateway target.

There are no module dependencies, arbitrary service names, custom commands, extra
environment variables, custom volumes, host devices, GPU grants, privileged flags
or custom resource limits in v1. Persistent data is available through `storage.data`
([application infrastructure](application-infrastructure.md)); outbound networking
requires the reviewed `network.egress` grant described below. Do not smuggle
privileges through unknown fields. Images declaring Docker volumes are rejected.

The local reference tag exceptions are `empyrean-example:0.1.0`, `0.1.1` and `0.1.2`, if the operator enables `NEXUS_ALLOW_EXAMPLE=1` on both services. It must already exist locally. All other images require digests. An image digest ensures identity of bytes, not trustworthiness or vulnerability freedom.

## Container contract

The broker supplies:

- `MODULE_PORT`: listen on this TCP port on `0.0.0.0`.
- `NEXUS_URL`: `http://nexus:12333`, reachable inside this module's network.
- `NEXUS_MODULE_ID`: stable registered module identity.
- `NEXUS_RESOLVER_KEY`: private credential for authenticating Nexus resolver requests; never log/export it.
- `NEXUS_TOKEN`: bearer credential scoped to this enabled module and declared capabilities.

Run as UID/GID 10001 with a read-only root filesystem. `/tmp` is a 16 MiB temporary
filesystem. Without `storage.data` the runtime is disposable; with that grant,
the broker owns a retained `/data` volume. Runtime limits are 256 MiB memory,
0.5 CPU, 64 processes and rotated logs (2 × 5 MiB). No public port is created.
Images should not contain private credentials, install packages at startup or
require root.

Tokens rotate on each enable and are revoked before disable/removal. Retry a Nexus API call made during startup: the container can start before the registration is committed as enabled. On a Nexus restart the existing token remains valid if its container is reconciled successfully. Never log the token.

## Lifecycle and review

`POST /api/v1/modules/validate` performs schema and compatibility review. `POST /api/v1/modules` takes `{ "manifest": {...}, "grants": [...] }`; grants must match the reviewed manifest exactly. Registration starts disabled and reserves its ID and port. Enabling is the point that downloads/runs the image. The broker validates again.

Enable, disable, inspect, health and uninstall routes are documented in [API](api.md). Uninstall is idempotent at the runtime cleanup layer, but inspecting/deleting an absent registration returns 404. Failed cleanup keeps the registration for a retry. `error` is a real state, not success. Since Nexus 0.1.3 a module is updated in place (same identity, data and references) after a capability diff review and verified health; see [lifecycle and recovery](lifecycle-and-recovery.md). Uninstall never deletes retained module data.

## Capability model

| Capability | Grants | Restriction |
| --- | --- | --- |
| `events.publish` | POST module events | Only `events.produces`; each must start with `<module-id>.` |
| `events.subscribe` | GET module events | Only exact `events.consumes` types |
| `notifications.publish` | POST module notifications | Plain text, 500 characters, source stamped by Nexus |

Every valid module token can call `/api/v1/module/context` for its own ID,
protocol, Nexus version and grants. Tokens cannot call owner endpoints. Review
exact event types. The table above lists the foundation event/notification grants;
later sections and [application infrastructure](application-infrastructure.md)
document the additional enforced storage, UI, reference, network and projection
capabilities. Arbitrary host access remains unsupported.

## Event contract

Publish to `/api/v1/module/events` with Authorization: Bearer and JSON:

```json
{"type":"empyrean-example.ping","payload":{"message":"hello"},"correlation_id":null}
```

Nexus returns HTTP 201:

```json
{
  "sequence": 1,
  "event": {
    "id": "30f70136-c774-444b-b7d9-b02534f6d958",
    "type": "empyrean-example.ping",
    "source": "empyrean-example",
    "timestamp": "2026-09-29T12:00:00+00:00",
    "schema_version": 1,
    "payload": {"message":"hello"},
    "correlation_id": null
  }
}
```

Only `type`, object `payload` (maximum 16 KiB serialized), and optional UUID `correlation_id` are client-supplied. The envelope's schema version describes the envelope, not domain payload semantics. Publishers own event type/payload compatibility; incompatible payloads should use a new event type/version contract.

Poll `GET /api/v1/module/events?after=0`. Response: `events`, `next_cursor`, `retention_gap`. Each entry has `sequence` and `event`. Nexus scans 100 entries per request and filters by grants, so an empty result may still advance the cursor. Continue polling until the cursor stops advancing. A maximum of 10,000 events is retained installation-wide. A nonzero cursor older than retained history sets `retention_gap=true`. Starting from zero means replay the retained window. Persist the cursor only after processing; deduplicate using event IDs. Retries of POST may create distinct events: no exactly-once/idempotency promise.

Module API traffic is limited to 120 requests per minute per module. Rate limits are in-memory and reset on restart. The example keeps no cursor so `/consume` replays retained events intentionally.

## Browser contract

Serve HTML with bundled inline styles/scripts. The gateway imposes CSP
`sandbox allow-scripts allow-downloads`, `default-src 'none'`, no network/forms,
data images/fonts and inline style/script. The non-application iframe further
restricts this with its `allow-scripts` attribute. Response cookies/redirects and
module security headers are not forwarded; owner browser credentials/headers
are not passed upstream. Nexus injects the module's gateway key, and forwards
method, query and body under the gateway's validation/size policy. A 5-second
timeout and 2 MiB response cap apply.

The module UI cannot directly read Nexus storage or invoke owner APIs. The
Nexus-side explorer supplies CSRF-protected requests to the declared prefix.
Full applications already use the opaque `ui.application` message bridge described
in [application infrastructure](application-infrastructure.md), rather than a
relaxed same-origin iframe.

## Navigation History pilot (local, default-off)

The [shared navigation SDK](navigation-history.md) is a browser bridge extension,
not a new Module Protocol manifest field, capability or required module dependency.
The host advertises version 1 through application context only when its process
has `NEXUS_NAVIGATION_HISTORY=1`. Existing manifests/URLs and the original bridge
remain valid; modules without an adapter keep legacy behavior. Mnemosyne is the
first local adapter; no all-module or production migration is claimed.

For adoption, preserve bootstrap paths, provide a domain route codec and legacy
fallback, bundle the shared client inline, fence async restores, and implement
acknowledged draft recovery before allowing an editor to unmount. The SDK's
default `beforeLeave` callback does not protect drafts. See the [adoption checklist](navigation-history.md#adopting-the-pilot-in-another-module)
and [recorded real-app tests](proposals/navigation-history/PILOT.md).

## Entity References extension v1

Optional `resources` declares unique opaque resource types with a `resolvable` flag. Optional `references` declares `version: 1` and exact `read`/`resolve` module/type scopes. The capabilities are `references.create` (source-owned creation/update/deletion), `references.read` (permission-aware index queries) and `references.resolve` (owner-authorized minimal metadata). Using these fields requires compatibility excluding Nexus 0.1.0. Legacy manifests without them remain supported.

Relationships are private to their creator unless explicit readers are granted. Target ownership never implies backlink visibility. The grammar, APIs, resolver authentication, event filtering, ID stability and lifecycle contract are specified in [cross-module references](cross-module-references.md). No official product receives special treatment.

## Nexus 0.1.3 additions

All are opt-in manifest fields validated by the same strict schema; older Nexus releases reject them rather than ignoring them. Using any of them requires a Nexus range excluding 0.1.2 (for example `>=0.1.3,<0.2.0`).

- `references.version: 2` (Entity References v2): the module's resource IDs are canonical lowercase UUIDs, enforced by Nexus. Optional `references.enumerate: true` (requires `references.create`) promises `GET /empyrean/v1/references/outgoing`.
- `backup: {"version": 1}` (requires `storage.data`): the module implements export, validate, restore and finalize.

Contracts, failure semantics and the owner APIs: [lifecycle and recovery](lifecycle-and-recovery.md). Module Protocol v1 itself is unchanged; existing manifests remain valid.

## Nexus 0.1.5 additions

Opt-in, validated by the same strict schema; a manifest using them must exclude Nexus 0.1.4 and earlier (for example `>=0.1.5,<0.2.0`), which reject them.

- **`network.egress`** (architecture ADR 0010). The broker creates a second, per-module bridge network `<installation>-egress-<id>` **without** `internal` and connects only this module's container to it. The internal network, its `nexus` alias and the gateway are unchanged; the gateway never joins an egress network. Disable and uninstall remove it. The capability is not a destination allowlist: the module must protect user-supplied destinations against SSRF (resolve and refuse non-public addresses, pin the vetted address, re-check redirects, bound time and size, never log URLs or credentials).
- **Projection queries** (architecture ADR 0011, `concepts/projections.md`). Declaration:

  ```json
  "projections": {"version": 1, "provides": ["dated-items"], "read": [{"module": "lyra", "projection": "dated-items"}]}
  ```

  `provides` needs no capability: it promises `POST /empyrean/v1/projections/<name>` on the module's private port, authenticated with `X-Nexus-Resolver-Key` and receiving `{requester, query, cursor}`. `read` requires `projections.read`; scopes are exact module/projection pairs. A consumer calls `POST /api/v1/module/projections/query` with `{module, projection, query (object ≤ 4 KiB), cursor}`. Nexus checks the capability and scope, the target's state and declaration, forwards with a 5 s timeout, accepts at most 1 MiB and 500 items, and returns `{module, projection, availability, items, next_cursor}`. `availability`: `available`, `module_uninstalled`, `module_disabled`, `not_provided`, `forbidden` (provider 403), `temporarily_unavailable` (anything else). Items are opaque to Nexus and are never stored.

Install review and update diffs show both (`capabilities`, `projections.provides`, `projections.read`).

## Nexus 0.1.8 addition: application icon

Optional manifest field `"icon": "/icon.svg"`: a path the module serves itself (`^/…\.(svg|png|webp)$`; no host, query or `..`). A manifest that declares it must exclude Nexus 0.1.7 and earlier (for example `>=0.1.8,<0.2.0`).

Nexus shows the icon in the application switcher, the module list, the module drawer and Overview. Serve a square, full-bleed tile in the application's own colours; Nexus applies its corner radius and edge light, so do not round or shadow the artwork. Icon changes are not permissions and do not appear in the update review.

Since Nexus 0.1.9 the icon is Nexus-owned once fetched (`backend/nexus/icons.py`): Nexus requests it from the module's private port, validates it, keeps the last valid copy in its data volume (`module-icons/<id>.icon` and `<id>.json`, keyed by module ID), and serves it to the owner at `GET /api/v1/modules/<id>/icon` (same origin, so the page keeps `img-src 'self'`). The copy survives module outages and Nexus restarts and is refreshed only when the manifest's icon path, version or image changes; a failed refresh keeps it, and failures are retried at most once a minute. Disabling a module keeps its copy, uninstalling deletes it. Until a valid copy exists, Nexus shows a neutral letter tile.

Validation: the response must be 200 with the content type of the declared format, at most 64 KiB; PNG and WebP must carry their signatures. SVG must be UTF-8, well-formed, rooted in the SVG namespace, without DTD, entities or style sheet instructions, and use only static drawing elements (`svg g defs title desc path circle ellipse rect line polyline polygon linearGradient radialGradient stop clipPath mask symbol use`): no script, `foreignObject`, `style`, `image`, links or animation, no event-handler attributes, and no references except to its own elements (`#id`, `url(#id)`); `javascript:` and `data:` values are rejected. The copy is served with `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; sandbox`, `X-Content-Type-Options: nosniff`, an ETag and `Cache-Control: private, no-cache`, so even an SVG opened directly is an inert document.
