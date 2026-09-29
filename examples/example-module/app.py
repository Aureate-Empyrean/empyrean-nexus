"""Disposable independent protocol reference; imports no Nexus implementation code."""

import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.environ["NEXUS_URL"]
TOKEN = os.environ["NEXUS_TOKEN"]
MODULE_ID = os.getenv("NEXUS_MODULE_ID", "empyrean-example")
RESOLVER_KEY = os.getenv("NEXUS_RESOLVER_KEY", "")
RESOURCE = f"nexus:v1:{MODULE_ID}:item:sample"


def nexus(path, body=None):
    request = urllib.request.Request(
        BASE + "/api/v1/module" + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=4) as response:
        return json.load(response)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, body, status=200, content_type="application/json"):
        raw = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        try:
            if self.path == "/health":
                self.reply({"status": "ok", "version": "0.1.1"})
            elif self.path == "/":
                self.reply(
                    """<!doctype html><html lang="en"><meta charset="utf-8">
                <meta name="viewport" content="width=device-width,initial-scale=1">
                <title>Empyrean Example Module</title>
                <style>body{background:#101216;color:#f2f0ea;font:14px/1.7 system-ui;padding:24px}
                h1{font-size:22px}p{color:#a7a9af}code{color:#d6ad60}</style>
                <h1>Protocol reference module</h1>
                <p>Disposable test resource: <code>item:sample</code></p>
                <p>API explorer: GET <code>/info</code>, POST <code>/publish</code>,
                GET <code>/consume</code>.</p><p>References: POST <code>/reference</code>,
                GET <code>/references</code> or <code>/backlinks</code>, POST <code>/resolve</code>.</p>
                </html>""",
                    content_type="text/html; charset=utf-8",
                )
            elif self.path == "/api/info":
                self.reply(
                    {
                        "module": MODULE_ID,
                        "version": "0.1.1",
                        "nexus": nexus("/context"),
                        "resource": RESOURCE,
                    }
                )
            elif self.path == "/api/consume":
                self.reply(nexus("/events"))
            elif self.path in {"/api/references", "/api/backlinks"}:
                self.reply(
                    nexus(
                        "/references?"
                        + urllib.parse.urlencode(
                            {
                                "resource": RESOURCE,
                                "direction": "incoming"
                                if self.path.endswith("backlinks")
                                else "outgoing",
                            }
                        )
                    )
                )
            else:
                self.reply({"detail": "Not found"}, 404)
        except (urllib.error.URLError, TimeoutError):
            self.reply({"detail": "Nexus API unavailable or access denied"}, 502)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 65536:
                return self.reply({"detail": "Body too large"}, 413)
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                return self.reply({"detail": "Expected JSON object"}, 400)
            if self.path == "/empyrean/v1/resources/resolve":
                if not RESOLVER_KEY or not secrets.compare_digest(
                    self.headers.get("X-Nexus-Resolver-Key", ""), RESOLVER_KEY
                ):
                    return self.reply({"detail": "Resolver authentication required"}, 403)
                if body.get("resource") != RESOURCE:
                    return self.reply({"detail": "Resource not found"}, 404)
                return self.reply({"resource": RESOURCE, "label": "Example item", "open_path": "/"})
            if self.path == "/api/publish":
                event = nexus(
                    "/events",
                    {"type": MODULE_ID + ".ping", "payload": {"message": "Reference module event"}},
                )
                nexus(
                    "/notifications",
                    {"message": "The reference module published its example event."},
                )
                return self.reply(event, 201)
            if self.path == "/api/reference":
                return self.reply(
                    nexus(
                        "/references",
                        {
                            "source": RESOURCE,
                            "target": body.get("target", RESOURCE),
                            "relation": MODULE_ID + ".related",
                            "readers": body.get("readers", []),
                        },
                    )
                )
            if self.path == "/api/resolve":
                return self.reply(
                    nexus("/resources/resolve", {"resource": body.get("resource", RESOURCE)})
                )
            return self.reply({"detail": "Not found"}, 404)
        except (ValueError, TypeError):
            self.reply({"detail": "Invalid JSON request"}, 400)
        except (urllib.error.URLError, TimeoutError):
            self.reply({"detail": "Nexus API unavailable or access denied"}, 502)


if __name__ == "__main__":
    ThreadingHTTPServer(
        ("0.0.0.0", int(os.getenv("MODULE_PORT", "13333"))), Handler
    ).serve_forever()
