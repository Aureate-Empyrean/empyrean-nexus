# API v1

Download the generated, authenticated OpenAPI document at `/api/v1/openapi.json` or from Settings. It documents request bodies and validation; this page describes authentication and operational semantics. No CDN-hosted Swagger scripts are loaded. The arbitrary module gateway is excluded from OpenAPI because it proxies module-specific contracts.

Owner authentication is an HttpOnly SameSite=Strict cookie, valid for 12 hours. Setup/login returns a CSRF token; send it as `X-Nexus-CSRF` on all authenticated mutations. An explicitly supplied Origin must match `NEXUS_PUBLIC_ORIGIN`, its loopback aliases, or an explicit `NEXUS_ALLOWED_ORIGINS` entry; cross-site requests are rejected. HTTPS origins issue Secure cookies. Module authentication uses `Authorization: Bearer <module-token>`, independently of browser sessions.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/healthz` | Public, minimal gateway/database liveness |
| GET, POST | `/api/v1/setup` | Setup-required state; claim-token-protected initial owner creation |
| POST | `/api/v1/auth/login` | Local owner login |
| GET | `/api/v1/auth/session` | Current username and CSRF token |
| POST | `/api/v1/auth/logout` | Revoke current session |
| GET | `/api/v1/system` | Version, installation, DB liveness, storage and update-not-checked state |
| PATCH | `/api/v1/settings` | Change installation display name |
| GET | `/api/v1/protocol` | JSON Schema for protocol v1 |
| GET | `/api/v1/example-manifest` | Reference manifest for review |
| POST | `/api/v1/modules/validate` | Validate raw manifest without installation |
| GET, POST | `/api/v1/modules` | List / install disabled with exact capability grants |
| GET, DELETE | `/api/v1/modules/{id}` | Inspect / uninstall with runtime cleanup |
| POST | `/api/v1/modules/{id}/enable` | Start constrained module container |
| POST | `/api/v1/modules/{id}/disable` | Revoke token and remove container/network |
| POST | `/api/v1/modules/{id}/health` | Bounded on-demand health check |
| GET/POST/PUT/PATCH/DELETE | `/modules/{id}/{path}` | Authenticated, sandboxed module gateway |
| GET | `/api/v1/module/context` | Bearer-authenticated module identity and grants |
| GET, POST | `/api/v1/module/events` | Scoped event polling / publication |
| POST | `/api/v1/module/notifications` | Scoped plain-text notification |
| GET | `/api/v1/notifications` | Most recent 100 notifications |
| POST | `/api/v1/notifications/read` | Mark notifications read |
| GET | `/api/v1/audit` | Most recent 100 audit records |
| GET | `/api/v1/export` | Full retained metadata export without credentials |

Common responses: 401 authentication required, 403 origin/CSRF/capability rejected, 404 missing module, 409 setup/registration/state conflict, 413 body too large, 422 invalid contract, 429 rate limited, 502 runtime/upstream unavailable. Responses never contain a module bearer token. All JSON request models reject unknown fields. Request bodies are capped at 64 KiB even when sent without Content-Length.

`/api/v1/export` uses `format=empyrean-nexus-export`, `version=1`, a UTC creation timestamp, and settings/modules/events/notifications/audit arrays. It omits owners' password hashes, session tokens and module bearer tokens. Audit and events can still contain private metadata: protect exported files. An export is not a full backup or accepted restore input.

## Resource interoperability and activity (0.1.1)

- `POST /api/v1/module/references`: idempotent source-owned relationship create/update with explicit reader IDs.
- `DELETE /api/v1/module/references/{id}`: creator-owned removal.
- `GET /api/v1/module/references?resource=...&direction=incoming|outgoing&after=0&limit=50`: filtered backlinks/outgoing relationships.
- `POST /api/v1/module/resources/resolve`: resolve `{resource}` through its owner, separately authorized.
- `GET /api/v1/references`: owner inspection with the same query parameters.
- `GET /api/v1/activity/entries?before=<id>&limit=50`: newest-first operational records adapted from the audit log; returns `items`, `next_cursor`, `has_more`. Each item has `id`, `kind`, `subject`, `actor`, `occurred_at`.

See [reference contract](cross-module-references.md) for exact identity, sharing, resolution and lifecycle behavior. The export now includes a `references` array and excludes resolver credentials. `POST /modules/validate` also reports `retained_references`; reinstalling such an identity needs explicit `reuse_reference_identity: true` alongside the manifest/grants.

The Activity UI uses `/api/v1/activity/entries`. The original `/api/v1/activity` remains a deprecated alias: its exact path collides with an EasyPrivacy tracking filter and can be blocked by browser content blockers before reaching Nexus. Both endpoints read the same persisted audit records and require an owner session.

## Module lifecycle and recovery (0.1.3)

- `POST /api/v1/modules/{id}/update/review` (manifest body) → capability/version diff and backup policy. `POST /api/v1/modules/{id}/update` `{manifest, grants, backup_before?, allow_downgrade?}` applies it in place; `GET /api/v1/modules/{id}/updates` lists attempts.
- `POST /api/v1/modules/{id}/backups`, `GET /api/v1/modules/{id}/backups`, `GET /api/v1/modules/{id}/backups/{backup}/download`.
- `POST /api/v1/modules/{id}/backups/{backup}/restore` `{confirm_replace:true}`; `GET /api/v1/modules/{id}/restores`; `POST /api/v1/modules/{id}/restores/{job}/finalize`.
- `POST /api/v1/modules/{id}/references/reconcile` rebuilds the module's outgoing edges from its enumeration.
- `POST /api/v1/modules/{id}/external-origins` `{origin}` trusts one canonical origin for that module's bridge navigation; `DELETE /api/v1/modules/{id}/external-origins?origin=…` removes it. Module listings include `external_origins`. See [security model](security-model.md#external-navigation).
- `GET /api/v1/system` also reports `development.reference_module`; `/api/v1/example-manifest` returns 404 unless development mode is enabled.

Semantics and failure states: [lifecycle and recovery](lifecycle-and-recovery.md).
