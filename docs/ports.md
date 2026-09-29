# Port convention and registry

Aureate Empyrean reserves TCP ports of the form `x333`, beginning with 12333 and stepping by 1000 through 65333. Every reserved value contains three consecutive 3s.

| Port | Allocation |
| --- | --- |
| 12333 | Nexus gateway/API; only normal host-published port |
| 13333 | Reference module in its supplied manifest |
| 14333–65333, step 1000 | Available module slots |

`protocol/module-v1.schema.json` is the machine-readable allowed module range; `backend/nexus/protocol.py` exposes the same range for tooling. The SQLite `modules.port UNIQUE` constraint is the installation registry. A second registration cannot reserve the same port, even while disabled. The reservation is freed only after successful uninstall. A module may not claim 12333 or any arbitrary port.

Ports identify expected module listeners, not host publications. Each module also has a private network, so the registry is a convention/coordination guarantee, not a claim that isolated containers technically cannot reuse port numbers. No manifest can publish a host port. The broker uses a Unix socket, so it has no TCP allocation.

`NEXUS_PORT` changes the host-facing bind without changing Nexus's internal 12333. A reverse proxy normally exposes 443. The disposable test harness uses host port 12334 solely to avoid colliding with a developer's normal installation; it is not an ecosystem service allocation.
