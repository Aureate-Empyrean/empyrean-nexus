# Entity References v1

## Authority and scope

This implementation follows the Aureate Empyrean [architecture repository](https://github.com/Aureate-Empyrean/architecture), inspected at commit `2f4f018`, specifically `concepts/cross-module-references.md`, `architecture.md`, `concepts/interoperability.md` and `modules/nexus.md`. The ecosystem's established ownership and privacy rules take precedence over the earlier Nexus plan. Grammar, per-relation sharing and endpoints below are Nexus implementation choices within areas that repository currently marks Open; they are not claims that every ecosystem open question is settled.

**A module owns its data. Nexus owns interoperability.** No domain types or official-module exceptions are built into the core. Community and official modules use identical declarations, credentials, APIs and permission checks. No module database is shared or queried.

This is a small opt-in extension of Module Protocol v1, introduced in Nexus 0.1.1. Existing v1 manifests without the extension remain valid. A module using it declares `references.version: 1` and a Nexus range excluding 0.1.0 (normally `>=0.1.1,<0.2.0`). Older Nexus rejects unsupported fields rather than pretending to support them.

## Identity

Canonical form:

```text
nexus:v1:<module-id>:<resource-type>:<stable-resource-id>
nexus:v1:community-library:item:42
```

The version is part of the grammar. The `nexus` module ID/event namespace is reserved for the platform. Module IDs and resource types are lowercase kebab-case, at most 48 characters each. The opaque resource ID is case-sensitive ASCII, 1–128 characters: a letter/digit followed by letters, digits, `.`, `_`, `~` or `-`. There is no percent decoding, URI authority, query, fragment, slash or relative traversal. Authors whose native IDs contain other characters must assign a stable safe identifier; do not derive identity from mutable display names or routes.

Identity is unambiguous **within one installation**. There is no federation or implicit interpretation in another installation. The type and ID are meaningful only to the owning module. Updates must preserve IDs; owners must not recycle deleted IDs for unrelated objects. Migration/merge aliases and cross-installation import mapping are not implemented.

Machine-readable identity grammar: [`resource-v1.schema.json`](../protocol/resource-v1.schema.json). The Python parser additionally enforces per-component lengths and is used for every reference/query/resolve input.

## Declaration

In a module manifest:

```json
{
  "nexus": ">=0.1.1,<0.2.0",
  "resources": [{"type":"item","resolvable":true}],
  "references": {
    "version": 1,
    "read": [{"module":"community-archive","type":"entry"}],
    "resolve": [{"module":"community-archive","type":"entry"}]
  },
  "capabilities": ["references.create","references.read","references.resolve"]
}
```

These are fragments of the full manifest, not a complete installable example. Scopes are exact module/type pairs with no wildcard. A module's own resource namespace is implicitly in scope, but the matching capability is still required. Resource types must be unique. `resolvable` is a promise to implement the resolver endpoint; it is not permission to reveal everything.

The owner reviews the complete manifest, including these scopes, before granting capabilities. Declarations cannot change in place or expand automatically. Identity or trust category confers no extra access.

## Index writes and ownership

An enabled module with `references.create` can POST `/api/v1/module/references`:

```json
{
  "source":"nexus:v1:community-library:item:42",
  "target":"nexus:v1:community-archive:entry:91",
  "relation":"community-library.related",
  "metadata":{"note":"owner-supplied relationship annotation"},
  "readers":["community-archive"]
}
```

The authenticated module must own the source and the relation namespace (`<source-module>.<local-relation-name>`). Nexus has no understanding of the relation name. New edges require registered endpoint modules and declared endpoint types, but do not assert that either object currently exists. There is no full resource catalog or background object enumeration.

`metadata` is optional JSON, limited to 2 KiB; it describes the relationship, not copies of foreign objects. The index is plaintext metadata. Never put credentials, vault material or full domain objects here. Modules that cannot safely disclose even an indexed relationship to the trusted Nexus installation must **not register it**. A protected secret index is out of scope.

The directed `(source,target,relation)` tuple is unique. Repeating POST returns the same generated reference UUID; changing metadata/readers updates that edge and timestamp. An unchanged retry creates no event. Response: `{created, reference}` with source/target/relation, creator, metadata, reader IDs, creation/update timestamps and sequence. The creator is server-stamped. The creator alone may DELETE `/api/v1/module/references/<uuid>`; a target owner may not edit/delete another module's edge. Creating and removing are covered by the same narrowly source-owned capability. There is a 100,000-edge ceiling per creating module; existing module API rate limits also apply.

## Discovery is an explicit grant

**Owning a target does not authorize discovering its backlinks.** A relation defaults to `readers: []`: only its creator can discover it (with `references.read`). An explicit reader list grants visibility to those module IDs. No target-owner, Official or Verified exception exists. A module can voluntarily share an ordinary relationship with its target owner; it must do so explicitly.

A read needs both:

1. `references.read` plus a scope permitting the resource being queried (or the caller's own namespace).
2. Creator ownership or inclusion in that edge's explicit reader list.

Consequently, a sensitive module's relationship to a person cannot automatically be discovered by the module owning that person. Giving a module a broad type-level scope still does not reveal unshared relationships.

Queries:

```text
GET /api/v1/module/references?resource=<canonical-ref>&direction=outgoing
GET /api/v1/module/references?resource=<canonical-ref>&direction=incoming
```

Responses have `references`, `next_cursor`, and `has_more`. Pass `after` and `limit` (default 50, maximum 100) for pagination. Visibility filtering happens in SQL **before pagination**: empty results do not disclose hidden edge counts or advance the cursor over private backlinks. An exact page boundary can require one empty final request. Sequence cursors enumerate insertions, not revisions; re-query a resource after a change signal to refresh its relationships. Nexus does not compute domain summaries or traversal queries.

The installation owner can inspect ordinary indexed metadata using GET `/api/v1/references` with the same query parameters and can export it. Module-relative privacy is not encryption from the administrator. Full multi-user authorization and sensitive/protected-index semantics remain deferred.

## Resolution is separate from discovery

POST `/api/v1/module/resources/resolve` with `{ "resource": "nexus:v1:community-archive:entry:91" }` requires `references.resolve` and its exact module/type scope. A known reference, an edge reader grant, or the ability to create an edge does **not** grant resolution or access to full data.

Nexus calls the owning container at the fixed private endpoint:

```text
POST /empyrean/v1/resources/resolve
X-Nexus-Resolver-Key: <per-module shared credential>

{"resource":"nexus:v1:community-archive:entry:91","requester":"community-library"}
```

The broker supplies `NEXUS_MODULE_ID` and `NEXUS_RESOLVER_KEY` to the owning container. The owner verifies this credential before trusting the requester, then enforces its own resource-level policy. Do not call Nexus recursively from the resolver. The credential is separate from the module bearer token and rotates on enable. Nexus keeps it in the protected SQLite metadata store because it must authenticate outbound calls; it is never returned in inspect/export or forwarded from a browser request. Docker administrators can inspect their containers' credentials.

An allowed HTTP 200 response is strictly bounded and validated:

```json
{
  "resource":"nexus:v1:community-archive:entry:91",
  "label":"Owner-selected label",
  "open_path":"/entries/91",
  "representation":{"summary":"Optional minimal, deliberately disclosed metadata"}
}
```

`resource` must match the request. `label` is plain text, at most 200 characters. `open_path` is optional: a simple module-relative absolute path, no `//`, URL, dot traversal, query or fragment. It is not resource identity. Optional representation is an object limited to 2 KiB. Total response limit is 4 KiB, timeout 5 seconds, with no redirects, external addresses or inherited browser credentials. No representation is cached or copied into Nexus tables.

Nexus returns `resource`, parsed `identity`, `availability`, and only for an available response the label/representation and an open descriptor `{route:"/app/modules/<owner>",module_path:"/entries/91"}`. A client may combine the route with `?path=<encoded module_path>`; the route does not identify the resource. The owner remains authoritative, including whether the caller can open/use the resource in its own UI.

Owner response statuses: 403 → `forbidden`, 404 → `not_found`, 410 → `deleted`. Other failures, malformed/oversized replies, timeouts and redirects → `temporarily_unavailable`. Declaration/runtime checks can return `not_resolvable`, `module_disabled`, or `module_uninstalled`. These results do not delete edges. Disabled callers have no valid token and cannot perform any reference operations.

## Lifecycle and portability

The relationship table has indexes on source, target and creator, and deliberately has **no cascading foreign key to module registration**. Disable, uninstall, failure and target deletion retain edges. A module reports deleted/missing objects through its resolver; Nexus does not infer deletion from downtime. An existing edge may be annotated/unshared/deleted by its creator even while the target is absent. New edges to an absent module cannot be registered until its type declaration exists again.

An uninstall leaves identity-bearing metadata behind. A reinstall with the same ID therefore requires the owner's explicit `reuse_reference_identity` confirmation. The install review counts endpoint identities and retained reader grants and warns about restoring the same dataset/IDs. This avoids silently reassigning old relationships to an unrelated new module. Reader grants are also keyed by stable module ID; after intentional identity reuse, restore only code/data authorized for that identity. Automated ID merging, migration aliases, orphan repair UI and cross-installation mapping remain open.

The metadata JSON export includes references and sharing lists, but never resolver keys. An offline SQLite backup round-trips the index, sequences and credentials with the rest of Nexus state. Automatic export import/index rebuild is not implemented. Providers should keep their own authoritative linkage information if they need to reconstruct an index after a selective restore. The index is not their domain database.

## Events

Index writes atomically append `nexus.reference.created`, `.updated` or `.deleted` to the existing bounded event log. Payload contains only the reference UUID and creator, not resource endpoints, metadata or readers. Subscribers need `events.subscribe`, an exact event declaration **and** `references.read`.

For noncreators, delivery checks the edge's **current** reader list and a granted query scope for at least one endpoint. Revocation therefore hides queued older events too. After deletion, only the creator can receive the event; other readers discover removal when refreshing their view. This intentionally avoids retaining a second sensitive ACL/tombstone index just to deliver deletion notifications. Providers must treat events as hints, not authoritative state or guaranteed delivery.

Resource owners can already publish namespaced lifecycle events such as `<module>.resource.deleted` under the existing event contract; no automatic domain interpretation is added. Owners are responsible for not putting private resource contents in broadly subscribed module events. There is no event-sourcing framework, graph engine or background reconciliation scanner.
