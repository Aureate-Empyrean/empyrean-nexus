"""Disposable process runtime for real HTTP Nexus/Mnemosyne/Chronos browser tests.

Replaces only the container broker with loopback Python processes. All auth,
gateway, frontend, domain APIs, databases and module-to-Nexus calls are real.
Never reads production config/data and never contacts Docker or Exodus.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
SIBLINGS = ROOT.parent


class LocalRuntime:
    def __init__(self):
        self.children = {}
        self.ports = json.loads(os.environ["PILOT_MODULE_PORTS"])

    def target(self, module_id, port):
        return f"http://127.0.0.1:{self.ports[module_id]}"

    def call(self, action, module_id, manifest=None, token=None, resolver_key=None):
        if module_id not in self.ports:
            raise RuntimeError("Local pilot permits only Mnemosyne and Chronos")
        if action == "enable":
            self.stop(module_id)
            env = {
                **os.environ,
                "PILOT_MODULE": module_id,
                "NEXUS_TOKEN": token,
                "NEXUS_RESOLVER_KEY": resolver_key,
            }
            log = open(Path(env["PILOT_DATA"]) / (module_id + ".log"), "w", encoding="utf-8")
            python = (
                SIBLINGS
                / module_id
                / ".venv"
                / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            )
            if not python.exists():
                python = Path(sys.executable)
            process = subprocess.Popen(
                [str(python), "-X", "utf8", __file__, "module"],
                env=env,
                stdout=log,
                stderr=log,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.children[module_id] = (process, log)
            for _ in range(150):
                if process.poll() is not None:
                    raise RuntimeError(f"{module_id} process failed; inspect disposable logs")
                try:
                    response = httpx.get(
                        self.target(module_id, 0) + "/health", timeout=0.2, trust_env=False
                    )
                    if response.status_code == 200:
                        return {"state": "running"}
                except httpx.HTTPError:
                    pass
                time.sleep(0.05)
            raise RuntimeError("Local module start timed out")
        if action in {"disable", "remove"}:
            self.stop(module_id)
            return {"state": "absent"}
        process = self.children.get(module_id)
        return {"state": "running" if process and process[0].poll() is None else "absent"}

    def stop(self, module_id):
        child = self.children.pop(module_id, None)
        if child:
            process, log = child
            process.terminate()
            process.wait(timeout=10)
            log.close()


if __name__ == "__main__":
    data = Path(os.environ["PILOT_DATA"])
    if sys.argv[-1] == "module":
        module = os.environ["PILOT_MODULE"]
        sys.path.insert(0, str(SIBLINGS / module / "backend"))
        if module == "mnemosyne":
            from mnemosyne.app import create_app
        else:
            from chronos.app import create_app
        app = create_app(data / module)
        port = json.loads(os.environ["PILOT_MODULE_PORTS"])[module]
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    else:
        sys.path.insert(0, str(ROOT / "backend"))
        from nexus.app import create_app

        runtime = LocalRuntime()
        try:
            uvicorn.run(
                create_app(data / "nexus", runtime),
                host="127.0.0.1",
                port=int(os.environ["PILOT_NEXUS_PORT"]),
                log_level="warning",
                access_log=False,
            )
        finally:
            for module_id in list(runtime.children):
                runtime.stop(module_id)
