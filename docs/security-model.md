# Security model

## Assets and adversaries

Protect owner identity, metadata, private events, host integrity and separation between modules. Assume module images and their HTML may be malicious, manifests may contain hostile inputs, and remote clients may attack setup/session endpoints. The host administrator and Docker administrator are trusted. Physical host compromise, compromised Docker/kernel, a compromised Nexus/broker and malicious dependency supply chains are not solved by this project.

## Enforced boundaries

- Setup needs a random 256-bit-ish URL-safe claim secret stored mode 0600 on the local data volume; no default account/password. Setup is atomic and single-owner.
- Argon2id uses 64 MiB memory, three iterations and two lanes. Password length is 12–128 characters. Session tokens are random, stored as SHA-256 hashes, and expire after at most 12 hours. Sessions carry `created_at`, `kind`, `issued_by` and `revoked_at`; the authorization layer rejects expired, malformed, revoked, future-dated and over-age rows. Logout marks the current session revoked. Successful login/setup issuance is recorded by `auth.login`/`setup.completed`, and logout by `auth.logout`.
- Cookies are HttpOnly/SameSite=Strict and Secure when the configured origin uses HTTPS. Mutations require session-bound CSRF tokens; foreign/null origins are rejected. Explicit proxy headers are not trusted. No permissive CORS.
- Setup/login have per-peer request limits; modules have token-scoped request limits. One worker is required. These are abuse friction, not DDoS protection; use proxy-level limits for remote deployments. A reverse proxy's IP is intentionally shared unless a future trusted-proxy policy is designed.
- JSON schemas reject unknown privilege fields. Ports and IDs are validated and unique. SQL is parameterized. Compatibility is checked at install, again by the broker at enable, and at Nexus startup, where an enabled module that no longer supports the running version loses its credentials.
- Modules get private internal networks and token-scoped API access. No automatic host mounts, secret sharing, host-published ports, privileged mode or Docker socket. Their tokens cannot authenticate owner routes.
- Outbound Internet access exists only for modules granted `network.egress` (0.1.5): a separate per-module non-internal bridge that only that container joins. It does not restrict destinations. A module holding it can send anything it holds anywhere, and can reach addresses routable from the Docker host unless host firewall rules prevent it; it is responsible for SSRF protection of user-supplied URLs. Grant it only to modules whose declared integration needs it.
- Projection queries (0.1.5) are forwarded only for exact, reviewed module/projection scopes, authenticated to the provider with its resolver key and stamped with the requester; providers decide what to disclose. Nexus bounds and forwards responses without storing them.
- Runtime: non-root UID, read-only root, dropped capabilities, no-new-privileges, fixed CPU/memory/PID/log bounds, 16 MiB temporary storage. Images declaring volumes are rejected.
- Browser: a strict CSP opaque-origin sandbox prevents module HTML from inheriting Nexus's same-origin powers. Parent UI escapes untrusted text. Credentials, redirect/cookie headers and module-supplied security headers are not proxied.
- Gateway paths cannot select arbitrary hosts. Ordinary owner request bodies are
  capped at 64 KiB; module gateway/blob request bodies and gateway responses at
  2 MiB. Upstream timeout is 5 seconds. No redirects or streaming/WebSocket support.
- Requested/completed/failed lifecycle actions are audited. Errors revoke module access and retain cleanup state. Notifications show failure rather than fake success.

## Authentication and deployment boundaries

Three identities are distinct:

- **Interactive owner.** The single installation owner signs in at `/api/v1/auth/login` with the owner passphrase. Nexus issues an HttpOnly session cookie and a session-bound CSRF token. The session row records `kind='interactive'`, `issued_by='login'` and its creation time. All owner actions are audited under the owner's user ID.
- **Deployment service.** The local `nexus.manage` CLI uses a random deployment key stored at `/data/admin-key` (mode 0600), sent only as `X-Nexus-Admin-Key` over loopback (`127.0.0.1`/`::1`). It is accepted only for `/api/v1/modules` deployment and maintenance routes, cannot change navigation trust, and cannot reach the browser module gateway, settings, audit export or other owner APIs. It never creates a browser session or cookie. Each request is audited as `host-admin:nexus.manage`, and module lifecycle audit rows carry that service actor. The CLI refuses a key file readable by group/other.
- **Host administrator.** Docker/root access is a trusted, root-equivalent boundary. A host administrator can modify the database, containers and backups directly, including inserting sessions or resetting state. Application controls cannot prevent a malicious root-equivalent administrator from doing so. The security requirement is to keep normal deployment on the scoped deployment key, reserve interactive owner sessions for the owner, and make privileged paths attributable wherever possible. AI agents must not receive production Docker/database authority.

The deployment key is local-only; a module, remote client or reverse proxy cannot use it even if it learns the value because the source address is not loopback. Protect `/data`, backups and host access accordingly.

## Honest limitations

The lifecycle broker controls Docker and is therefore effectively root-equivalent. A Unix socket narrows who can reach it; it does not make a Docker daemon safe to expose. Its directory is mounted only into Nexus and the broker. A successful compromise of either trusted service could exploit this authority. Never mount broker-control or Docker sockets into a module. The trusted broker alone has the documented SELinux `label:disable` exception needed for the daemon socket on enforcing hosts. Nexus and modules retain normal SELinux labeling; the host policy is not disabled. A custom audited broker policy would be a stronger future deployment option.

Docker containers share the kernel. Internal Docker bridges constrain normal external routing and separate modules, but are not a universal host firewall: a module can reach Nexus, other listeners on its reachable bridge addresses, and potentially host services. Do not run sensitive unauthenticated host services on bridge interfaces. Docker's DNS may provide a limited outbound query channel. Strongly hostile workloads require extra host firewalling, reviewed runtime policy or VM isolation. No claim of total exfiltration prevention is made.

Published module HTTP endpoints are inherently reachable by Nexus on their private network. An image may run arbitrary code inside its container. Digest pinning identifies bytes; it does not authenticate a publisher or make an image safe. Manual publisher metadata is never a verification result. The local example tag is a development exception: a Docker administrator can replace it. Set `NEXUS_ALLOW_EXAMPLE=0` for stricter deployments.

A token is plaintext in its module's Docker environment; Docker admins can inspect it. SQLite and backups are not encrypted by Nexus. Use encrypted host storage and protected backups when required. Logout revokes only the current session; other sessions are not terminated. There is no browser account-recovery/password-rotation interface yet; a host administrator can recover a lost owner only with direct database/host access, which is inside the trusted root boundary. Operators should not deploy v1 for critical private data until these operational gaps and a broader security review are addressed.

Events are bounded best-effort signals. Subscribers with a granted event type can read every retained event of that type. Ordinary module events have no per-payload policy; internal reference-event delivery additionally checks current reference visibility. No tenant separation or schema registry exists. Notifications and event storage are bounded; audit history is not. Body-size bounds do not prevent all slow-client attacks; terminate remote traffic at a suitably configured reverse proxy.

Health is on demand and represents an HTTP status at that instant. Nexus health does not imply the Docker broker or every module is healthy. Runtime failures surface on lifecycle calls or restart reconciliation. No automatic vulnerability scanning, signature verification, remote monitoring or update assurance is claimed.

## Reporting and changes

See [SECURITY.md](../SECURITY.md). Changes to schemas, routing, broker policy, auth and capability enforcement require tests that demonstrate denied behavior, not just the happy path. Do not relax browser sandboxing or add broad mounts to fix module compatibility.

## Navigation history and draft checkpoints

The [navigation extension](navigation-history.md) (enabled by default since Nexus 0.1.11) does not change HTTP
authentication, CSRF, capabilities, the gateway key or opaque iframe sandboxing.
The host validates the connected enabled application's `contentWindow`, binds
module identity itself, and uses per-load challenges plus session/revision fences.
Opaque `null` origin alone is not identity. Parent-to-child wildcard delivery is
limited to the bound opaque frame; no auth credentials are included.

Routes are bounded data, never fetch targets or resource authority. Draft
checkpoints deliberately contain module-owned private text and are stored as JSON
in the trusted parent's tab-local sessionStorage, keyed by owner username and
bound module. This is not encryption, a vault, server backup or a new source of
domain truth. The child receives its own snapshot through the bridge rather than
direct storage access. Compromised parent code/host administrators remain trusted
with that text; never put Janus vault secrets into this channel.

Size/rate limits and explicit quota/timeout errors bound the mechanism. SPA leave
requires an acknowledged final checkpoint; full-document close/crash relies on
previously stored snapshots and the module's unload warning. Sign-out warns before
clearing dirty checkpoints; uninstall clears that module's copy. See [limitations
and rollout gates](navigation-history.md#validation-and-remaining-gates) rather than
assuming all failure combinations or all browsers have been validated.

## Reference boundaries

References and their existence can be sensitive. Type-level query scopes do not override per-edge creator/readers visibility; owning the target alone is insufficient. Filtering occurs before pagination. Resolution requires a different capability and owner-supplied authorization response. Nexus authenticates itself to the owner with a per-module resolver key and supplies the requester identity; browser headers cannot inject this credential. The plaintext resolver key is necessarily stored in the private metadata DB and owning container environment, omitted from all inspect/export responses, and rotated on enable. Protect offline backups accordingly.

Reference events contain only edge ID/creator and are filtered using current visibility; deletion leaves no audience index, so deleted-edge events are creator-only. Edges and normal metadata exports remain readable to the trusted installation administrator. Sensitive modules should avoid registering secrets or relationships whose existence must be hidden from that administrator. This is not a protected secret index or a multi-user authorization system. Reinstalling an identity with retained references requires explicit owner confirmation; stable IDs must never be recycled for unrelated objects.

## External navigation

A module's own content cannot reach the network (`connect-src 'none'`, no forms, `img-src data:` and `font-src data:` (inline resources only; since 0.1.4 so applications can embed the shared Roboto face, ADR 0008 in the architecture repository), no popups or top navigation, and Nexus's `frame-src 'self'` blocks the frame from navigating itself elsewhere). The bridge's `external` action was the remaining way out: a URL is a data channel, since anything the module puts in its path, query or fragment reaches the destination. Before 0.1.3 Nexus opened any HTTP(S)/mailto URL a module requested, relying on the user's click inside the module, so a malicious module could send private data to any server.

Showing the full URL and letting the owner click it (the first 0.1.3 attempt) is not enough: one click would both approve an attacker's server and send the payload the module placed in the address. Nexus therefore separates **trust** from **navigation**:

- **Parsing.** Only absolute `https:`, `http:` and `mailto:` URLs of at most 2048 characters without embedded credentials are accepted; everything else (for example `javascript:`, `data:`, `file:`, relative links) is rejected without a dialog.
- **Origin identity.** Trust applies to the browser's serialized origin: scheme, host and port, with the default port omitted and internationalized hosts in punycode. `http` and `https`, another port, a subdomain, a longer suffix or a Unicode lookalike are all different origins. Path, query and fragment are never part of trust.
- **First contact.** A request to an origin the module is not trusted for shows a Nexus dialog naming the requesting module, the origin, scheme, host and port, and nothing from the path or query. Approving it stores trust and **opens nothing**: the requested URL is discarded, so no module-supplied payload reaches the new origin. The module is told `{opened:false, trusted:true}`; the owner opens the link again afterwards.
- **Trusted origin.** Later requests to an exact trusted origin of **that module** open directly (new tab, `noopener,noreferrer`), including their path and query. Trusting an origin means accepting that the module may send data to it.
- **Scope and storage.** Trust is stored server-side per module ID and origin (`module_external_origins`), granted only through owner-authenticated, CSRF-protected API calls (`POST`/`DELETE /api/v1/modules/<id>/external-origins`), listed in the module's details where each entry can be removed, and deleted when the module is uninstalled. Modules cannot grant it to themselves, and trust never carries over to another module.
- **mailto.** Never becomes standing trust. Each request shows the single recipient address (strictly validated; multiple recipients are refused) and, on approval, opens `mailto:<address>` only. Module-supplied subject, body, cc, bcc and other fields are always discarded, and nothing is sent until the owner sends it from their mail app.
- **Click safety.** Approval buttons arm after 600 ms so a dialog raised under the pointer cannot capture a click, a pending decision cannot be replaced by another module request, and closing or replacing the dialog counts as refusal.

Limits: this constrains where a module can send data, not whether a module is trustworthy. A trusted origin receives whatever the module places in addresses under it, so trust only sites you expect that module to use. A malicious module remains able to misuse any capability it was granted.
