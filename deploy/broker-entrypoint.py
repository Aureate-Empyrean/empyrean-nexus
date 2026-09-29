import os
from pathlib import Path

import uvicorn

socket_dir = Path("/run/nexus")
socket_dir.mkdir(exist_ok=True)
os.chown(socket_dir, 10001, 10001)
os.chmod(socket_dir, 0o700)
# Only UID 10001 (the trusted Nexus gateway) and root can access this directory.
(socket_dir / "broker.sock").unlink(missing_ok=True)
uvicorn.run("broker.app:app", uds=str(socket_dir / "broker.sock"), access_log=False)
