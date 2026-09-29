# ADR 0003: Explicit capabilities, bounded polling and honest provenance

Status: accepted for protocol v1.

The initial release implemented three capabilities: events.publish, events.subscribe and notifications.publish. Grants must exactly match reviewed declarations; optional/selective grants would require module behavior negotiation. Event types constrain publish/subscribe authority. Publishers may only emit their own module-ID namespace. Server-generated source, ID and timestamp prevent impersonation.

A bounded SQLite log is appropriate for lightweight integration signals on one installation. Consumers own cursor persistence and deduplication. It is not a reliable queue for irreplaceable business records. Add stronger delivery only when a real module requires it.

A manifest's author and publisher fields are attribution, not proof. Every manual installation is Community/unreviewed. Official and Verified are reserved for a future independently authenticated provenance/review system. Original authors remain separately visible. Community does not mean malicious, and Verified will not mean guaranteed safe.

Keep ingestion separate from runtime identity: manual files work offline; future sources return the same contract. Release metadata is informational, never executed or followed automatically. Compatibility is explicit; updates cannot mutate a registration behind the owner's back.

ADR 0004 extends this set with source-owned references, scoped resolution, explicit edge sharing and visibility-filtered internal reference events. Ordinary module event semantics remain unchanged.
