# Empyrean Module Protocol v1

Normative machine-readable schema: [`protocol/module-v1.schema.json`](../protocol/module-v1.schema.json). Working example: [`manifest.json`](../examples/example-module/manifest.json). Unknown fields are rejected at every object level. A manifest is UTF-8 JSON, limited by the 64 KiB API body limit. No executable installation hooks exist.

## Fields

| Field | Meaning and enforcement |
| --- | --- |
| `protocol` | Integer `1`; incompatible versions are rejected |
| `id` | Stable lowercase kebab-case identifier, maximum 48 characters; installation-unique |
| `name`, `description` | Plain-text display metadata, maximum 80/500 characters |
| `version` | Three-part version, optional prerelease suffix |
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

A route is a simple absolute path, not a URL, with no query, fragment, escape sequence or parent traversal. The gateway forwards subsequent relative paths to the same fixed container/port; it cannot target arbitrary hosts. Routes declare entry points, not extra access control within a module.

There are no module dependencies, arbitrary service names, custom commands, extra environment variables, volumes, host devices, GPU grants, external networking, privileged flags or custom resource limits in v1. Do not smuggle these in through unknown manifest fields; validation rejects them. Images declaring Docker volumes are also rejected.

The local reference tag exceptions are `empyrean-example:0.1.0` and `empyrean-example:0.1.1`, if the operator enables `NEXUS_ALLOW_EXAMPLE=1` on both services. It must already exist locally. All other images require digests. An image digest ensures identity of bytes, not trustworthiness or vulnerability freedom.

## Container contract

The broker supplies:

- `MODULE_PORT`: listen on this TCP port on `0.0.0.0`.
- `NEXUS_URL`: `http://nexus:12333`, reachable inside this module's network.
- `NEXUS_MODULE_ID`: stable registered module identity.
- `NEXUS_RESOLVER_KEY`: private credential for authenticating Nexus resolver requests; never log/export it.
- `NEXUS_TOKEN`: bearer credential scoped to this enabled module and declared capabilities.

Run as UID/GID 10001 with a read-only root filesystem. `/tmp` is a 16 MiB temporary filesystem; no persistent data storage is supported. Runtime limits are 256 MiB memory, 0.5 CPU, 64 processes and rotated container logs (2 × 5 MiB). No public port is created. Module Docker images should not contain private credentials, run package installation at startup or require root.

Tokens rotate on each enable and are revoked before disable/removal. Retry a Nexus API call made during startup: the container can start before the registration is committed as enabled. On a Nexus restart the existing token remains valid if its container is reconciled successfully. Never log the token.

## Lifecycle and review

`POST /api/v1/modules/validate` performs schema and compatibility review. `POST /api/v1/modules` takes `{ "manifest": {...}, "grants": [...] }`; grants must match the reviewed manifest exactly. Registration starts disabled and reserves its ID and port. Enabling is the point that downloads/runs the image. The broker validates again.

Enable, disable, inspect, health and uninstall routes are documented in [API](api.md). Uninstall is idempotent at the runtime cleanup layer, but inspecting/deleting an absent registration returns 404. Failed cleanup keeps the registration for a retry. `error` is a real state, not success. V1 does not update manifests in place: disable/uninstall and explicitly review a new manifest. There is no persistent module data in this revision.

## Capability model

| Capability | Grants | Restriction |
| --- | --- | --- |
| `events.publish` | POST module events | Only `events.produces`; each must start with `<module-id>.` |
| `events.subscribe` | GET module events | Only exact `events.consumes` types |
| `notifications.publish` | POST module notifications | Plain text, 500 characters, source stamped by Nexus |

Every valid module token can call `/api/v1/module/context` for its own ID, protocol, Nexus version and grants. Tokens cannot call owner endpoints. Event subscriptions may reveal private data in future; review exact event types, even though this reference only uses a harmless ping. Host/network/storage capabilities are unsupported rather than represented as misleading, unenforced permissions.

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

Serve small HTML with inline styles/scripts if needed. The gateway imposes `sandbox allow-scripts`, `default-src 'none'`, no network connections/forms, and allows only data images plus inline style/script. It strips response cookies, redirects and all other upstream response headers except content type. Owner cookies, authorization and request headers are not forwarded; JSON request body and method are forwarded. A 5-second timeout and 2 MiB response cap apply.

The module UI cannot read Nexus storage or invoke owner APIs. The Nexus-side API explorer supplies CSRF-protected requests to the declared API prefix. This is a narrow foundation, **not general-purpose SPA hosting**. Supporting a full module frontend will require a dedicated-origin or similarly explicit isolation design, not a relaxed same-origin iframe.

## Entity References extension v1

Optional `resources` declares unique opaque resource types with a `resolvable` flag. Optional `references` declares `version: 1` and exact `read`/`resolve` module/type scopes. The capabilities are `references.create` (source-owned creation/update/deletion), `references.read` (permission-aware index queries) and `references.resolve` (owner-authorized minimal metadata). Using these fields requires compatibility excluding Nexus 0.1.0. Legacy manifests without them remain supported.

Relationships are private to their creator unless explicit readers are granted. Target ownership never implies backlink visibility. The grammar, APIs, resolver authentication, event filtering, ID stability and lifecycle contract are specified in [cross-module references](cross-module-references.md). No official product receives special treatment.
