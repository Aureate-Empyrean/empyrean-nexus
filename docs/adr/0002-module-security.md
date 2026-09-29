# ADR 0002: Constrained broker, isolated networks and sandboxed module content

Status: accepted for protocol v1.

Nexus never mounts Docker's socket. A private Unix-socket broker exposes only enable, disable, uninstall and status. No arbitrary Docker endpoint, command, environment, host mount or resource override is accepted. The manifest is validated independently in Nexus and the broker before enable. Runtime policy is fixed in code.

Images require immutable digest references. A narrow, configurable exception accepts the locally built reference image by its exact tag. Image-declared volumes are rejected. Runtime uses the resolved image ID to avoid a local tag changing between inspection and container creation.

Modules have per-module internal networks, no published ports, UID 10001, a read-only root filesystem, a small temporary filesystem, dropped capabilities, no-new-privileges and fixed CPU/memory/PID/log limits. V1 has no persistent module storage; deleting/disable destroys ephemeral data. Persistence requires a separately designed named-volume lifecycle rather than ad hoc bind mounts.

Serving arbitrary JavaScript under Nexus's normal origin would expose owner sessions to same-origin requests. Module responses instead receive a strict opaque-origin CSP sandbox, and the UI embeds the same sandbox. This intentionally prevents a general SPA, forms and direct browser network requests. The authenticated Nexus API explorer demonstrates API routing while richer module UI isolation (for example dedicated origins) is deferred. Do not remove sandbox restrictions to make an arbitrary app work.

Docker's socket is effectively host authority. Broker compromise, host administrator access, malicious images exploiting the kernel and host-network services remain threats. Internal bridge networks are not full host isolation. More hostile workloads need stronger VM/rootless/firewall isolation and review; no such protection is claimed here.

Source: https://docs.docker.com/engine/security/
