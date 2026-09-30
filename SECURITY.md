# Security policy

Empyrean Nexus 0.1.2 is an early foundation, not independently audited software. Only the current development line receives fixes; no stable support window is promised yet. Read [the security model](docs/security-model.md) before entrusting it with sensitive data.

## Report privately where available

Use the canonical repository's **Security → Report a vulnerability** facility if its maintainers have enabled private vulnerability reporting. This repository does not invent a security email address or claim that a reporting channel has already been provisioned.

If that private facility is unavailable, open a minimal issue asking maintainers for a private reporting channel, without exploit details, private manifests, logs with tokens or personal data. Project maintainers should configure private reporting before publishing a release intended for real private data. No response-time guarantee exists yet.

A useful private report identifies the affected version, threat boundary, minimal reproduction, expected/actual behavior, and likely impact. Never include live credentials. Do not test against another person's installation without permission.

Security-sensitive changes need regression tests and honest release notes. Digest pinning and a Verified label must never be described as guarantees of safety. Containers are not perfect sandboxes; Docker authority is root-equivalent on typical hosts.
