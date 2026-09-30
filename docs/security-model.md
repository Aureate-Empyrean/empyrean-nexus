# Security model

## Assets and adversaries

Protect owner identity, metadata, private events, host integrity and separation between modules. Assume module images and their HTML may be malicious, manifests may contain hostile inputs, and remote clients may attack setup/session endpoints. The host administrator and Docker administrator are trusted. Physical host compromise, compromised Docker/kernel, a compromised Nexus/broker and malicious dependency supply chains are not solved by this project.

## Enforced boundaries

- Setup needs a random 256-bit-ish URL-safe claim secret stored mode 0600 on the local data volume; no default account/password. Setup is atomic and single-owner.
- Argon2id uses 64 MiB memory, three iterations and two lanes. Password length is 12–128 characters. Session tokens are random, stored as SHA-256 hashes, expire after 12 hours, and are revoked on logout.
- Cookies are HttpOnly/SameSite=Strict and Secure when the configured origin uses HTTPS. Mutations require session-bound CSRF tokens; foreign/null origins are rejected. Explicit proxy headers are not trusted. No permissive CORS.
- Setup/login have per-peer request limits; modules have token-scoped request limits. One worker is required. These are abuse friction, not DDoS protection; use proxy-level limits for remote deployments. A reverse proxy's IP is intentionally shared unless a future trusted-proxy policy is designed.
- JSON schemas reject unknown privilege fields. Ports and IDs are validated and unique. SQL is parameterized. Compatibility is checked at install, again by the broker at enable, and at Nexus startup, where an enabled module that no longer supports the running version loses its credentials.
- Modules get private internal networks and token-scoped API access. No automatic host mounts, secret sharing, external network grants, host-published ports, privileged mode or Docker socket. Their tokens cannot authenticate owner routes.
- Runtime: non-root UID, read-only root, dropped capabilities, no-new-privileges, fixed CPU/memory/PID/log bounds, 16 MiB temporary storage. Images declaring volumes are rejected.
- Browser: a strict CSP opaque-origin sandbox prevents module HTML from inheriting Nexus's same-origin powers. Parent UI escapes untrusted text. Credentials, redirect/cookie headers and module-supplied security headers are not proxied.
- Gateway paths cannot select arbitrary hosts. Requests are capped at 64 KiB; upstream responses at 2 MiB, with a 5-second timeout. No redirects or streaming/WebSocket support.
- Requested/completed/failed lifecycle actions are audited. Errors revoke module access and retain cleanup state. Notifications show failure rather than fake success.

## Honest limitations

The lifecycle broker controls Docker and is therefore effectively root-equivalent. A Unix socket narrows who can reach it; it does not make a Docker daemon safe to expose. Its directory is mounted only into Nexus and the broker. A successful compromise of either trusted service could exploit this authority. Never mount broker-control or Docker sockets into a module. The trusted broker alone has the documented SELinux `label:disable` exception needed for the daemon socket on enforcing hosts. Nexus and modules retain normal SELinux labeling; the host policy is not disabled. A custom audited broker policy would be a stronger future deployment option.

Docker containers share the kernel. Internal Docker bridges constrain normal external routing and separate modules, but are not a universal host firewall: a module can reach Nexus, other listeners on its reachable bridge addresses, and potentially host services. Do not run sensitive unauthenticated host services on bridge interfaces. Docker's DNS may provide a limited outbound query channel. Strongly hostile workloads require extra host firewalling, reviewed runtime policy or VM isolation. No claim of total exfiltration prevention is made.

Published module HTTP endpoints are inherently reachable by Nexus on their private network. An image may run arbitrary code inside its container. Digest pinning identifies bytes; it does not authenticate a publisher or make an image safe. Manual publisher metadata is never a verification result. The local example tag is a development exception: a Docker administrator can replace it. Set `NEXUS_ALLOW_EXAMPLE=0` for stricter deployments.

A token is plaintext in its module's Docker environment; Docker admins can inspect it. SQLite and backups are not encrypted by Nexus. Use encrypted host storage and protected backups when required. Logout does not terminate other sessions; there is no account recovery/password rotation interface yet. Operators should not deploy v1 for critical private data until these operational gaps and a broader security review are addressed.

Events are bounded best-effort signals. Subscribers with a granted event type can read every retained event of that type. Ordinary module events have no per-payload policy; internal reference-event delivery additionally checks current reference visibility. No tenant separation or schema registry exists. Notifications and event storage are bounded; audit history is not. Body-size bounds do not prevent all slow-client attacks; terminate remote traffic at a suitably configured reverse proxy.

Health is on demand and represents an HTTP status at that instant. Nexus health does not imply the Docker broker or every module is healthy. Runtime failures surface on lifecycle calls or restart reconciliation. No automatic vulnerability scanning, signature verification, remote monitoring or update assurance is claimed.

## Reporting and changes

See [SECURITY.md](../SECURITY.md). Changes to schemas, routing, broker policy, auth and capability enforcement require tests that demonstrate denied behavior, not just the happy path. Do not relax browser sandboxing or add broad mounts to fix module compatibility.

## Reference boundaries

References and their existence can be sensitive. Type-level query scopes do not override per-edge creator/readers visibility; owning the target alone is insufficient. Filtering occurs before pagination. Resolution requires a different capability and owner-supplied authorization response. Nexus authenticates itself to the owner with a per-module resolver key and supplies the requester identity; browser headers cannot inject this credential. The plaintext resolver key is necessarily stored in the private metadata DB and owning container environment, omitted from all inspect/export responses, and rotated on enable. Protect offline backups accordingly.

Reference events contain only edge ID/creator and are filtered using current visibility; deletion leaves no audience index, so deleted-edge events are creator-only. Edges and normal metadata exports remain readable to the trusted installation administrator. Sensitive modules should avoid registering secrets or relationships whose existence must be hidden from that administrator. This is not a protected secret index or a multi-user authorization system. Reinstalling an identity with retained references requires explicit owner confirmation; stable IDs must never be recycled for unrelated objects.

## External navigation

A module's own content cannot reach the network (`connect-src 'none'`, no forms, `img-src data:`, no popups or top navigation, and Nexus's `frame-src 'self'` blocks the frame from navigating itself elsewhere). The bridge's `external` action was the remaining way out: a URL is a data channel, since anything the module puts in its path, query or fragment reaches the destination. Before 0.1.3 Nexus opened any HTTP(S)/mailto URL a module requested, relying on the user's click inside the module, so a malicious module could send private data to any server.

Showing the full URL and letting the owner click it (the first 0.1.3 attempt) is not enough: one click would both approve an attacker's server and send the payload the module placed in the address. Nexus therefore separates **trust** from **navigation**:

- **Parsing.** Only absolute `https:`, `http:` and `mailto:` URLs of at most 2048 characters without embedded credentials are accepted; everything else (for example `javascript:`, `data:`, `file:`, relative links) is rejected without a dialog.
- **Origin identity.** Trust applies to the browser's serialized origin: scheme, host and port, with the default port omitted and internationalized hosts in punycode. `http` and `https`, another port, a subdomain, a longer suffix or a Unicode lookalike are all different origins. Path, query and fragment are never part of trust.
- **First contact.** A request to an origin the module is not trusted for shows a Nexus dialog naming the requesting module, the origin, scheme, host and port, and nothing from the path or query. Approving it stores trust and **opens nothing**: the requested URL is discarded, so no module-supplied payload reaches the new origin. The module is told `{opened:false, trusted:true}`; the owner opens the link again afterwards.
- **Trusted origin.** Later requests to an exact trusted origin of **that module** open directly (new tab, `noopener,noreferrer`), including their path and query. Trusting an origin means accepting that the module may send data to it.
- **Scope and storage.** Trust is stored server-side per module ID and origin (`module_external_origins`), granted only through owner-authenticated, CSRF-protected API calls (`POST`/`DELETE /api/v1/modules/<id>/external-origins`), listed in the module's details where each entry can be removed, and deleted when the module is uninstalled. Modules cannot grant it to themselves, and trust never carries over to another module.
- **mailto.** Never becomes standing trust. Each request shows the single recipient address (strictly validated; multiple recipients are refused) and, on approval, opens `mailto:<address>` only. Module-supplied subject, body, cc, bcc and other fields are always discarded, and nothing is sent until the owner sends it from their mail app.
- **Click safety.** Approval buttons arm after 600 ms so a dialog raised under the pointer cannot capture a click, a pending decision cannot be replaced by another module request, and closing or replacing the dialog counts as refusal.

Limits: this constrains where a module can send data, not whether a module is trustworthy. A trusted origin receives whatever the module places in addresses under it, so trust only sites you expect that module to use. A malicious module remains able to misuse any capability it was granted.
