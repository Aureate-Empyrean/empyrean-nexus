"""The reference module's contract endpoints, run as a real process against a fake Nexus."""

import json
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
from nexus.references import EnumerationPage, canonical_uuid, parse_resource


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class FakeNexus(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        raw = json.dumps({"created": True, "reference": body}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def test_reference_module_uses_uuid_identity_and_enumerates_what_it_created():
    nexus = ThreadingHTTPServer(("127.0.0.1", 0), FakeNexus)
    threading.Thread(target=nexus.serve_forever, daemon=True).start()
    port, key = free_port(), "k" * 40
    env = {
        **os.environ,
        "NEXUS_URL": f"http://127.0.0.1:{nexus.server_port}",
        "NEXUS_TOKEN": "t" * 40,
        "NEXUS_MODULE_ID": "empyrean-example",
        "NEXUS_RESOLVER_KEY": key,
        "MODULE_PORT": str(port),
    }
    process = subprocess.Popen(
        [sys.executable, "examples/example-module/app.py"], env=env, cwd=os.getcwd()
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if httpx.get(base + "/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.05)
        target = f"nexus:v1:peer:item:{uuid.uuid4()}"
        created = httpx.post(base + "/api/reference", json={"target": target}, timeout=5)
        assert created.status_code == 200
        info_resource = created.json()["reference"]["source"]
        identity = parse_resource(info_resource)
        assert identity["type"] == "item" and canonical_uuid(identity["id"])
        outgoing = base + "/empyrean/v1/references/outgoing?limit=200"
        assert httpx.get(outgoing, timeout=5).status_code == 403
        page = EnumerationPage.model_validate_json(
            httpx.get(outgoing, headers={"X-Nexus-Resolver-Key": key}, timeout=5).content
        )
        assert page.next_cursor is None
        assert [(e.source, e.target, e.relation) for e in page.references] == [
            (info_resource, target, "empyrean-example.related")
        ]
    finally:
        process.terminate()
        process.wait(timeout=5)
        nexus.shutdown()
