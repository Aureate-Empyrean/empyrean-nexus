# ADR 0004: Domain-independent references with private-by-default discovery

Status: implemented in Nexus 0.1.1, Entity References extension v1.

Authority: Aureate Empyrean architecture, inspected at `2f4f018`, especially its first-class reference rule and example showing that a backlink's existence can itself be sensitive. These constraints supersede any earlier target-owner auto-discovery assumption.

Use a strict versioned identity string, a directed SQLite relationship index and a fixed authenticated resolver endpoint. Reuse the module registry, existing bearer capabilities, gateway namespace and bounded event log. No parallel identity provider, cross-module database access, domain objects or graph service is introduced.

A creating module controls source-owned edges; edges are private to it unless it names explicit readers. Query scopes and edge-level visibility are separate checks. Target ownership alone never authorizes backlink discovery. Filter before pagination to avoid leaking hidden backlink existence. Reader revocation also applies to queued Nexus reference events. Minimal resolver metadata is returned on demand and never persisted.

Keep index entries across runtime failures and uninstall. Reinstalling the same namespace requires explicit owner confirmation if references remain. This preserves useful unresolved references without silently transferring identity to a replacement dataset. Merging/import aliases and protected secret metadata remain unsolved scope, not inferred behaviors.

Tradeoffs: per-edge module-ID reader lists fit single-user v1 but are not a multi-user ACL framework. Normal index contents remain visible to the trusted installation owner/database administrator. Sensitive modules can decline indexing; this does not claim encrypted/private-vault interoperability. Deletion notifications are creator-only rather than retaining historical reader permissions. Resolution keys are necessarily stored in protected metadata and owning container environments, separate from hashed bearer tokens.

The extension is optional for legacy v1 manifests. New manifests require a Nexus range starting at 0.1.1 or otherwise excluding 0.1.0. Full contract: [cross-module references](../cross-module-references.md).
