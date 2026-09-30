# Module lifecycle and recovery (0.1.3)

Nexus 0.1.3 adds three module-contract seams from the ecosystem architecture (`concepts/module-contract.md`, `concepts/resource-identity-and-lifecycle.md`, `concepts/backups.md`): outgoing-reference enumeration, backup/restore participation and in-place updates. Nexus orchestrates; modules stay authoritative for their data and never expose their database or schema. All module-facing endpoints below are fixed paths on the module's private network, authenticated with the module's `X-Nexus-Resolver-Key` credential (never a browser credential).

## Outgoing-reference enumeration (Entity References v2)

Declared with `"references": {"version": 2, "enumerate": true, ...}` plus `references.create`. The module serves:

```text
GET /empyrean/v1/references/outgoing?limit=200[&cursor=<opaque>]
X-Nexus-Resolver-Key: <credential>

{"references":[{"source","target","relation","metadata","readers"}], "next_cursor": "<opaque>" | null}
```

It lists every outgoing edge it wants in the Nexus index: the complete, authoritative set for its own resources. Edges it does not want indexed (for example relationships whose existence is sensitive) are simply never registered or enumerated; enumeration never forces publication.

`POST /api/v1/modules/<id>/references/reconcile` (owner) fetches all pages, validates every edge like a normal write (source owned by the module and a declared UUID resource, namespaced relation, explicit reader IDs, bounded metadata, target type declared by a registered owner) and then, in one transaction, makes the module's edges in the index equal the enumeration: adds missing edges, updates changed metadata/readers, removes edges the owner no longer reports. Existing edges keep their reference UUIDs. Repeating it changes nothing. Normal `nexus.reference.*` hints are emitted for actual changes only. Edges created by other modules are never touched.

**Failure is never "zero references".** Any non-200 reply, timeout, oversized page (1 MiB), malformed page, repeated cursor, repeated edge, foreign or non-UUID source, undeclared type, or more than 100,000 edges aborts reconciliation with HTTP 502 and leaves the index unchanged. Retained edges to an uninstalled module stay representable; registered owners' declarations still apply.

## UUID resource identity

Entity References v2 (manifest `references.version: 2`, Nexus range excluding 0.1.2) requires every resource ID the module exposes to be a canonical lowercase UUID, as the ecosystem architecture requires for persistent first-class resources. Nexus enforces it wherever the module's identity appears: creating edges (as source or target), resolution requests and enumeration. Declare only persistent resources; transient concepts are not resource types. v1 manifests keep their opaque-ID contract so existing installations continue to work; new modules should use v2.

## Backup/restore contract (backup v1)

Declared with `"backup": {"version": 1}`; requires `storage.data` and a Nexus range excluding 0.1.2. The module's artifact is opaque to Nexus: Nexus never decrypts, parses or migrates it. A module whose data is encrypted end to end (for example a future Janus) exports ciphertext.

Module endpoints (all `POST`, all authenticated):

| Path | Contract |
| --- | --- |
| `/empyrean/v1/backup/export` | 200 with the artifact body (≤ 256 MiB) and metadata headers `X-Empyrean-Backup-Module`, `-Module-Version`, `-Format` (`^[a-z][a-z0-9.-]{0,63}$`), `-Format-Version` (integer), `-Created-At` (ISO 8601 with offset), optional `-Restorable-By` (PEP 440 range of module versions; default: exactly the exporting version). |
| `/empyrean/v1/backup/validate` | Receives the artifact and metadata headers. 200 `{"valid":true}` only if it can be restored. Must not change data. |
| `/empyrean/v1/backup/restore` | Replaces the module's data with the artifact, **preserving resource UUIDs**, and **suspends automatic destructive retention/purges** until finalize. 200 `{"restored":true}`. |
| `/empyrean/v1/backup/finalize` | Reconciles retention (restored timestamps must not trigger immediate purges) and resumes it. 200 `{"finalized":true}`. |

### Backup

`POST /api/v1/modules/<id>/backups` (module enabled). Nexus streams the artifact to `/data/backups/modules/<id>/<backup-id>/`, validates the metadata against the registration (identity and installed version must match), copies the shared blobs granted to the module, and writes `metadata.json`:

```json
{"format":"empyrean-module-backup","version":1,"id":"…","module":"…","module_version":"…",
 "module_format":"…","module_format_version":1,"created_at":"…","exported_at":"…",
 "restorable_by":"…","nexus_version":"0.1.3","artifact":{"sha256":"…","size":0},
 "blobs":[{"sha256":"…","size":0}]}
```

Nothing is recorded unless every part succeeds. `GET /api/v1/modules/<id>/backups` lists backups; `GET …/backups/<backup-id>/download` returns a portable uncompressed tar (`metadata.json`, `artifact`, `blobs/<sha256>`). Backups contain module data and are **not encrypted by Nexus**: protect the data volume and downloaded files. Backups survive uninstall; their presence makes a reinstall of the same identity require explicit reuse confirmation.

### Restore lifecycle

`POST /api/v1/modules/<id>/backups/<backup-id>/restore` with `{"confirm_replace": true}` (explicit; the module's current data is replaced). The lifecycle lock is held throughout.

1. **Preflight (Nexus)**: the backup belongs to this module identity; the installed module version satisfies `restorable_by`; artifact and blob digests match. Otherwise 409 and nothing is contacted or changed.
2. **validate**: the module is set to `restoring` (its API token and gateway are paused). If the module rejects the artifact: 422, state returns to `enabled`, job `failed/validate`, nothing changed.
3. **blobs**: missing shared files are written back and re-granted to the module. Blobs are only ever added.
4. **restore**: on any failure the data state is unknown: the module becomes `error` with health `restore_failed`, its credentials are revoked, the job is `failed/restore` and a notification explains the recovery (enable the module and retry). Success returns the module to `enabled`.
5. **reconcile**: for enumerating modules, the reference index is rebuilt from the restored data (above), never trusted from the old index. Modules that create references without enumeration complete with an explicit warning that the index was not reconciled.
6. **finalize**: only after reconciliation succeeded. If reconciliation or finalization fails the job is `needs_attention/<stage>`: restored data is in place and the module's purges **remain suspended**. `POST /api/v1/modules/<id>/restores/<job-id>/finalize` retries reconcile + finalize.

`GET /api/v1/modules/<id>/restores` lists jobs (`running`, `completed`, `failed`, `needs_attention`, with `stage` and `detail`). A Nexus restart during a restore marks the job `failed` and the module `error` with revoked credentials; nothing is reported as restored.

Not implemented yet: importing a downloaded backup into another installation, backup scheduling/retention, encryption, and module-independent full-installation backup. Nexus's own database and module data volumes still need the offline procedure in [deployment](deployment.md).

## In-place updates

A module update keeps its identity, registration, data volume, shared-file grants and references. It is never an uninstall/reinstall.

- `POST /api/v1/modules/<id>/update/review` with the new manifest returns the diff: versions (and whether it is a downgrade), image, port, Nexus range, capabilities added/removed, events, resource types, reference scopes, persistent-data effect and the backup policy (`recommended`, `unavailable` for persistent modules without backup support, `not_applicable`). The manifest is fully validated, including Nexus compatibility; identity changes are refused.
- `POST /api/v1/modules/<id>/update` with `{manifest, grants, backup_before?, allow_downgrade?}`. `grants` must equal the new capability list exactly: an added capability that is not granted is refused (422), removed capabilities are no longer granted. Downgrades need `allow_downgrade`.
- **Backup hook**: `backup_before: true` creates a backup first and aborts the update if it fails. `NEXUS_UPDATE_BACKUP=require` makes this mandatory for backup-capable persistent modules (default `recommend`). Whether an update migrates data is the module's business; Nexus never touches module schemas.
- **Apply**: an enabled (or errored) module is set to `updating`, its credentials are revoked, and the broker replaces the container with the new image while keeping the named data volume. New credentials are issued, then health is verified (`NEXUS_UPDATE_HEALTH_ATTEMPTS`, default 10 × 1 s). Only a healthy module is reported `completed`. A disabled module gets the new manifest and stays disabled; its health is `not_verified` until enabled.
- **Failure**: if the container cannot start or health does not pass, the module is `error` with revoked credentials and the update record is `failed` at `start` or `health`. **No rollback is performed or claimed.** The notification names the previous version: recover by reviewing and applying the previous manifest (`allow_downgrade`), or by restoring a backup if the new version already migrated data.
- `GET /api/v1/modules/<id>/updates` shows each attempt with from/to versions, state and stage. A Nexus restart during an update fails it closed.

The CLI in the gateway container supports the same flows for administrators: `python -m nexus.manage manifest.json --update [--approve] [--backup-first] [--allow-downgrade]`, `--backup <id>`, `--restore <id> <backup-id> --confirm-replace`, `--reconcile <id>`.
