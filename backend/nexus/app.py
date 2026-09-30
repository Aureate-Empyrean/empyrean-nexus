import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import Version
from pydantic import BaseModel, ConfigDict, Field

from nexus import VERSION
from nexus.db import Database
from nexus.navigation import add_navigation_routes, trusted_origins
from nexus.protocol import ROOT, validate_manifest
from nexus.recovery import add_recovery_routes
from nexus.references import add_reference_routes, edge_json, event_visible
from nexus.runtime import BrokerRuntime
from nexus.updates import add_update_routes

PASSWORDS = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
COOKIE = "nexus_session"
MAX_BODY = 65536


def now():
    return datetime.now(timezone.utc).isoformat()


def compatible_with_running_nexus(manifest):
    try:
        return Version(VERSION) in SpecifierSet(manifest["nexus"])
    except (InvalidSpecifier, KeyError, TypeError):
        return False


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(StrictModel):
    username: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=128)


class Setup(Credentials):
    claim_token: str = Field(min_length=20, max_length=200)
    installation_name: str = Field(min_length=1, max_length=80)


class Installation(StrictModel):
    installation_name: str = Field(min_length=1, max_length=80)
    locale: str | None = Field(
        default=None, pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$", max_length=35
    )


class Install(StrictModel):
    manifest: dict
    grants: list[str] = Field(max_length=10)
    reuse_reference_identity: bool = False


class Event(StrictModel):
    type: str = Field(max_length=120, pattern=r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9_-]*)+$")
    payload: dict
    correlation_id: uuid.UUID | None = None


class Notification(StrictModel):
    message: str = Field(min_length=1, max_length=500)


class BodyLimit:
    """Enforce size before parsing, including chunked requests without Content-Length."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        messages, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            path = scope.get("path", "")
            body_limit = (
                2 * 1024 * 1024
                if path.startswith("/modules/") or path == "/api/v1/module/blobs"
                else MAX_BODY
            )
            if size > body_limit:
                response = JSONResponse(
                    {"detail": "Request exceeds endpoint body limit"}, status_code=413
                )
                return await response(scope, receive, send)
            messages.append(message)
            if not message.get("more_body", False):
                break

        async def replay():
            if messages:
                return messages.pop(0)
            return await receive()

        await self.app(scope, replay, send)


def create_app(data_dir=None, runtime=None, transport=None):
    data = Path(data_dir or os.getenv("NEXUS_DATA", ".data"))
    db = Database(data / "nexus.sqlite3")
    runtime = runtime or BrokerRuntime(os.getenv("NEXUS_BROKER_SOCKET", "/run/nexus/broker.sock"))
    origin = os.getenv("NEXUS_PUBLIC_ORIGIN", "http://localhost:12333").rstrip("/")
    allowed_origins = {origin}
    allowed_origins.update(
        value.strip().rstrip("/")
        for value in os.getenv("NEXUS_ALLOWED_ORIGINS", "").split(",")
        if value.strip()
    )
    for value in tuple(allowed_origins):
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
            or "*" in value
            or parsed.scheme != urlsplit(origin).scheme
        ):
            raise ValueError("Nexus origins must be explicit HTTP(S) origins with the same scheme")
        if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
            suffix = f":{parsed.port}" if parsed.port else ""
            allowed_origins.update(
                f"{parsed.scheme}://{host}{suffix}" for host in ("localhost", "127.0.0.1", "[::1]")
            )
    allow_example = os.getenv("NEXUS_ALLOW_EXAMPLE") == "1"
    lifecycle_lock = threading.Lock()
    attempts = defaultdict(deque)
    rate_lock = threading.Lock()
    claim_path = data / "setup-token"
    with db.connect() as conn:
        if not conn.execute("SELECT 1 FROM users").fetchone() and not claim_path.exists():
            fd = os.open(claim_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w") as file:
                file.write(secrets.token_urlsafe(32))

    @asynccontextmanager
    async def lifespan(app):
        # Interrupted operations remain explicit and retryable after process termination.
        with db.connect() as conn:
            conn.execute(
                "UPDATE modules SET state='error', token=NULL,resolver_key=NULL WHERE state IN ('enabling','disabling','removing','restoring','updating')"
            )
            conn.execute(
                "UPDATE module_restores SET state='failed',detail='Interrupted by a Nexus restart; the module data state is unknown.' WHERE state='running'"
            )
            conn.execute(
                "UPDATE module_updates SET state='failed',detail='Interrupted by a Nexus restart; the module was left in error.' WHERE state='applying'"
            )
            enabled = conn.execute(
                "SELECT id,manifest FROM modules WHERE state='enabled'"
            ).fetchall()
        # An upgraded Nexus must not keep serving modules whose declared range excludes it.
        compatible = []
        for row in enabled:
            if compatible_with_running_nexus(json.loads(row["manifest"])):
                compatible.append(row)
                continue
            with db.connect() as conn:
                conn.execute(
                    "UPDATE modules SET state='error',token=NULL,resolver_key=NULL,health='incompatible' WHERE id=?",
                    (row["id"],),
                )
                audit(conn, "nexus", "module.compatibility.failed", row["id"])
                notice(
                    conn,
                    "nexus",
                    f"Module {row['id']} does not support Nexus {VERSION}. Its access was revoked; disable it and install a compatible release.",
                )
        # A recreated gateway must rejoin the networks of existing module containers.
        for row in compatible:
            try:
                running = runtime.call("status", row["id"])["state"] == "running"
            except RuntimeError:
                running = False
            if not running:
                with db.connect() as conn:
                    conn.execute(
                        "UPDATE modules SET state='error',token=NULL,resolver_key=NULL,health='unreachable' WHERE id=?",
                        (row["id"],),
                    )
                    notice(
                        conn,
                        "nexus",
                        f"Module {row['id']} could not be reconciled after startup. Retry enable or disable.",
                    )
        yield

    app = FastAPI(
        title="Empyrean Nexus",
        version=VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.db = db
    app.state.runtime = runtime
    app.add_middleware(BodyLimit)

    def audit(conn, actor, action, target):
        conn.execute(
            "INSERT INTO audit(actor,action,target,timestamp) VALUES(?,?,?,?)",
            (actor, action, target, now()),
        )

    def notice(conn, source, message):
        conn.execute(
            "INSERT INTO notifications(source,message,created_at) VALUES(?,?,?)",
            (source, message, now()),
        )
        conn.execute(
            "DELETE FROM notifications WHERE id <= (SELECT COALESCE(MAX(id),0)-500 FROM notifications)"
        )

    def limit(key, count=10, window=300):
        with rate_lock:
            clock = time.monotonic()
            # Bounded maps; tokens and IP addresses never become permanent database records.
            if len(attempts) > 2048:
                for old in list(attempts):
                    if not attempts[old] or attempts[old][-1] < clock - window:
                        del attempts[old]
                if len(attempts) > 2048:
                    raise HTTPException(429, "Too many clients; retry later")
            queue = attempts[key]
            while queue and queue[0] < clock - window:
                queue.popleft()
            if len(queue) >= count:
                raise HTTPException(429, "Rate limit reached; retry later")
            queue.append(clock)

    def require_owner(request: Request):
        token = request.cookies.get(COOKIE, "")
        with db.connect() as conn:
            session = conn.execute(
                "SELECT sessions.*,users.username FROM sessions JOIN users ON users.id=sessions.user_id WHERE token=? AND expires>?",
                (digest(token), int(time.time())),
            ).fetchone()
        if not session:
            raise HTTPException(401, "Sign in required")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if not secrets.compare_digest(request.headers.get("x-nexus-csrf", ""), session["csrf"]):
                raise HTTPException(403, "CSRF token required")
        return dict(session)

    def require_module(request: Request):
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Module token required")
        hashed = digest(authorization[7:])
        with db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM modules WHERE token=? AND state='enabled'", (hashed,)
            ).fetchone()
        if not row:
            raise HTTPException(401, "Module token is invalid or revoked")
        limit("module:" + row["id"], 120, 60)
        return {**dict(row), "manifest": json.loads(row["manifest"])}

    def capability(module, cap):
        if cap not in module["manifest"]["capabilities"]:
            raise HTTPException(403, "Capability was not granted: " + cap)

    @app.middleware("http")
    async def security(request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            supplied_origin = request.headers.get("origin")
            if supplied_origin and supplied_origin not in allowed_origins:
                return JSONResponse(
                    {
                        "detail": "Origin rejected. Use a configured Nexus address or add this address to NEXUS_ALLOWED_ORIGINS."
                    },
                    status_code=403,
                )
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Cross-site request rejected"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if not request.url.path.startswith("/modules/"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
            )
        return response

    def session_response(conn, user_id, username):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        conn.execute("DELETE FROM sessions WHERE expires<=?", (int(time.time()),))
        conn.execute(
            "INSERT INTO sessions VALUES(?,?,?,?)",
            (digest(token), user_id, csrf, int(time.time()) + 43200),
        )
        response = JSONResponse({"username": username, "csrf": csrf})
        response.set_cookie(
            COOKIE,
            token,
            max_age=43200,
            httponly=True,
            secure=origin.startswith("https://"),
            samesite="strict",
            path="/",
        )
        return response

    @app.get("/api/v1/setup")
    def setup_status():
        with db.connect() as conn:
            return {"required": conn.execute("SELECT 1 FROM users").fetchone() is None}

    @app.post("/api/v1/setup", status_code=201)
    def setup(body: Setup, request: Request):
        limit("setup:" + request.client.host)
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM users").fetchone():
                raise HTTPException(409, "Installation is already initialized")
            if not claim_path.exists() or not secrets.compare_digest(
                body.claim_token, claim_path.read_text().strip()
            ):
                raise HTTPException(403, "Invalid installation claim token")
            user_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO users VALUES(?,?,?)",
                (user_id, body.username, PASSWORDS.hash(body.password)),
            )
            conn.execute(
                "INSERT INTO settings VALUES('installation_name',?)", (body.installation_name,)
            )
            audit(conn, user_id, "setup.completed", "nexus")
            notice(
                conn, "nexus", "Welcome to Nexus. Your installation is ready for its first module."
            )
            response = session_response(conn, user_id, body.username)
        claim_path.unlink(missing_ok=True)
        response.status_code = 201
        return response

    @app.post("/api/v1/auth/login")
    def login(body: Credentials, request: Request):
        limit("login:" + request.client.host)
        with db.connect() as conn:
            user = conn.execute("SELECT * FROM users WHERE username=?", (body.username,)).fetchone()
            valid = False
            try:
                if user:
                    valid = PASSWORDS.verify(user["password"], body.password)
                else:
                    PASSWORDS.hash(body.password)  # Avoid an inexpensive unknown-user timing path.
            except VerificationError:
                pass
            if not valid:
                raise HTTPException(401, "Invalid username or password")
            if PASSWORDS.check_needs_rehash(user["password"]):
                conn.execute(
                    "UPDATE users SET password=? WHERE id=?",
                    (PASSWORDS.hash(body.password), user["id"]),
                )
            audit(conn, user["id"], "auth.login", "nexus")
            return session_response(conn, user["id"], user["username"])

    @app.get("/api/v1/auth/session")
    def session(owner=Depends(require_owner)):
        return {"username": owner["username"], "csrf": owner["csrf"]}

    @app.post("/api/v1/auth/logout")
    def logout(owner=Depends(require_owner)):
        with db.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token=?", (owner["token"],))
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE, path="/")
        return response

    @app.get("/healthz")
    def healthz():
        with db.connect() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok"}

    @app.get("/api/v1/system")
    def system(owner=Depends(require_owner)):
        with db.connect() as conn:
            name = conn.execute(
                "SELECT value FROM settings WHERE key='installation_name'"
            ).fetchone()[0]
            count = conn.execute("SELECT COUNT(*) FROM modules").fetchone()[0]
            locale = conn.execute("SELECT value FROM settings WHERE key='locale'").fetchone()
        disk = os.statvfs(data)
        return {
            "name": name,
            "version": VERSION,
            "status": "healthy",
            "modules": count,
            "database": "SQLite",
            "locale": locale[0] if locale else "en",
            "data_free_bytes": disk.f_bavail * disk.f_frsize,
            "update": {"status": "not_checked", "discovery_supported": False},
            "protocol": 1,
            "development": {"reference_module": allow_example},
        }

    @app.patch("/api/v1/settings")
    def settings(body: Installation, owner=Depends(require_owner)):
        with db.connect() as conn:
            conn.execute(
                "UPDATE settings SET value=? WHERE key='installation_name'",
                (body.installation_name,),
            )
            if body.locale is not None:
                conn.execute(
                    "INSERT INTO settings(key,value) VALUES('locale',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (body.locale,),
                )
            audit(conn, owner["user_id"], "settings.changed", "nexus")
        return {"ok": True}

    @app.get("/api/v1/openapi.json")
    def openapi(owner=Depends(require_owner)):
        return app.openapi()

    @app.get("/api/v1/protocol")
    def protocol(owner=Depends(require_owner)):
        return FileResponse(ROOT / "protocol/module-v1.schema.json")

    @app.get("/api/v1/example-manifest")
    def example_manifest(owner=Depends(require_owner)):
        # Development-only reference; production installations do not offer it.
        if not allow_example:
            raise HTTPException(404, "The reference module is a development feature")
        return FileResponse(ROOT / "examples/example-module/manifest.json")

    def validate(manifest):
        try:
            return validate_manifest(manifest, allow_example)
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, str(exc)) from exc

    def inspect_row(row):
        result = dict(row)
        result.pop("token", None)
        result.pop("resolver_key", None)
        result["manifest"] = json.loads(result["manifest"])
        result["provenance"] = {
            "status": "community",
            "review": "Unreviewed local installation; publisher metadata is self-declared",
        }
        result["update"] = {"status": "not_checked"}
        return result

    def retained_reference_count(conn, module_id):
        prefix = "nexus:v1:" + module_id + ":%"
        return conn.execute(
            "SELECT COUNT(*) FROM resource_references WHERE source LIKE ? OR target LIKE ? OR EXISTS (SELECT 1 FROM json_each(resource_references.readers) WHERE value=?)",
            (prefix, prefix, module_id),
        ).fetchone()[0]

    def retained_data(conn, module_id):
        return bool(
            conn.execute("SELECT 1 FROM retained_module_data WHERE id=?", (module_id,)).fetchone()
            or conn.execute("SELECT 1 FROM blob_grants WHERE module=?", (module_id,)).fetchone()
            or conn.execute("SELECT 1 FROM module_backups WHERE module=?", (module_id,)).fetchone()
        )

    @app.post("/api/v1/modules/validate")
    def review(manifest: dict, owner=Depends(require_owner)):
        validate(manifest)
        with db.connect() as conn:
            retained = retained_reference_count(conn, manifest["id"])
            data_retained = retained_data(conn, manifest["id"])
        return {
            "valid": True,
            "retained_references": retained,
            "retained_data": data_retained,
            "capabilities": manifest["capabilities"],
            "provenance": "community",
            "warning": "Publisher identity is not verified. Enabling runs third-party container code.",
        }

    @app.post("/api/v1/modules", status_code=201)
    def install(body: Install, owner=Depends(require_owner)):
        manifest = validate(body.manifest)
        if set(body.grants) != set(manifest["capabilities"]):
            raise HTTPException(422, "Explicit grants must match the reviewed capability request")
        with lifecycle_lock, db.connect() as conn:
            if (
                retained_reference_count(conn, manifest["id"])
                or retained_data(conn, manifest["id"])
            ) and not body.reuse_reference_identity:
                raise HTTPException(
                    409,
                    "This module identity has retained references or persistent data. Explicitly confirm reuse_reference_identity when restoring the same module data.",
                )
            try:
                conn.execute(
                    "INSERT INTO modules(id,owner_id,manifest,port,state,source,installed_at) VALUES(?,?,?,?,?,?,?)",
                    (
                        manifest["id"],
                        owner["user_id"],
                        json.dumps(manifest),
                        manifest["container"]["port"],
                        "disabled",
                        "manual-manifest",
                        now(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise HTTPException(
                    409, "Module ID or reserved port is already registered"
                ) from exc
            if "storage.data" in manifest["capabilities"]:
                conn.execute(
                    "INSERT OR IGNORE INTO retained_module_data VALUES(?)", (manifest["id"],)
                )
            audit(conn, owner["user_id"], "module.installed", manifest["id"])
        return {"id": manifest["id"], "state": "disabled"}

    @app.get("/api/v1/modules")
    def modules(owner=Depends(require_owner)):
        with db.connect() as conn:
            return [
                {**inspect_row(row), "external_origins": trusted_origins(conn, row["id"])}
                for row in conn.execute("SELECT * FROM modules ORDER BY installed_at")
            ]

    def get_module(module_id):
        with db.connect() as conn:
            row = conn.execute("SELECT * FROM modules WHERE id=?", (module_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Module not found")
        return dict(row)

    @app.get("/api/v1/modules/{module_id}")
    def inspect(module_id: str, owner=Depends(require_owner)):
        row = get_module(module_id)
        with db.connect() as conn:
            return {**inspect_row(row), "external_origins": trusted_origins(conn, module_id)}

    def transition(module_id, action, owner):
        with lifecycle_lock:
            row = get_module(module_id)
            if action == "enable" and row["state"] == "enabled":
                return {"state": "enabled"}
            token = secrets.token_urlsafe(32) if action == "enable" else None
            resolver_key = secrets.token_urlsafe(32) if token else None
            pending = {"enable": "enabling", "disable": "disabling", "uninstall": "removing"}[
                action
            ]
            with db.connect() as conn:
                conn.execute(
                    "UPDATE modules SET state=?,token=NULL,resolver_key=NULL,health='unknown' WHERE id=?",
                    (pending, module_id),
                )
                audit(conn, owner["user_id"], f"module.{action}.requested", module_id)
            try:
                runtime.call(action, module_id, json.loads(row["manifest"]), token, resolver_key)
            except RuntimeError as exc:
                with db.connect() as conn:
                    conn.execute(
                        "UPDATE modules SET state='error',token=NULL,resolver_key=NULL WHERE id=?",
                        (module_id,),
                    )
                    notice(
                        conn,
                        "nexus",
                        f"Module {module_id}: {action} failed. Inspect the broker and retry disable or uninstall.",
                    )
                    audit(conn, owner["user_id"], f"module.{action}.failed", module_id)
                raise HTTPException(502, str(exc)) from exc
            with db.connect() as conn:
                if action == "uninstall":
                    conn.execute("DELETE FROM modules WHERE id=?", (module_id,))
                    # Navigation trust is a grant to this installation of the module, not data.
                    conn.execute("DELETE FROM module_external_origins WHERE module=?", (module_id,))
                else:
                    conn.execute(
                        "UPDATE modules SET state=?,token=?,resolver_key=? WHERE id=?",
                        (
                            "enabled" if action == "enable" else "disabled",
                            digest(token) if token else None,
                            resolver_key,
                            module_id,
                        ),
                    )
                audit(conn, owner["user_id"], f"module.{action}.completed", module_id)
            return {
                "state": {"enable": "enabled", "disable": "disabled", "uninstall": "uninstalled"}[
                    action
                ]
            }

    @app.post("/api/v1/modules/{module_id}/enable")
    def enable(module_id: str, owner=Depends(require_owner)):
        return transition(module_id, "enable", owner)

    @app.post("/api/v1/modules/{module_id}/disable")
    def disable(module_id: str, owner=Depends(require_owner)):
        return transition(module_id, "disable", owner)

    @app.delete("/api/v1/modules/{module_id}")
    def uninstall(module_id: str, owner=Depends(require_owner)):
        return transition(module_id, "uninstall", owner)

    def upstream(row, method, path, content=None):
        url = runtime.target(row["id"], row["port"]) + path
        try:
            with httpx.Client(
                transport=transport, timeout=5, follow_redirects=False, trust_env=False
            ) as client:
                with client.stream(
                    method,
                    url,
                    content=content,
                    headers={
                        **({"content-type": "application/json"} if content else {}),
                        **(
                            {"X-Nexus-Gateway-Key": row["resolver_key"]}
                            if row["resolver_key"]
                            else {}
                        ),
                    },
                ) as response:
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > 2 * 1024 * 1024:
                            raise HTTPException(502, "Module response exceeds 2 MiB")
                        chunks.append(chunk)
                    return (
                        response.status_code,
                        response.headers.get("content-type", "application/octet-stream"),
                        b"".join(chunks),
                    )
        except httpx.HTTPError as exc:
            raise HTTPException(502, "Module did not respond") from exc

    @app.post("/api/v1/modules/{module_id}/health")
    def module_health(module_id: str, owner=Depends(require_owner)):
        row = get_module(module_id)
        status = "disabled"
        if row["state"] == "enabled":
            try:
                code, _, _ = upstream(row, "GET", json.loads(row["manifest"])["routes"]["health"])
                status = "healthy" if code == 200 else "unhealthy"
            except HTTPException:
                status = "unreachable"
        with db.connect() as conn:
            conn.execute("UPDATE modules SET health=? WHERE id=?", (status, module_id))
            if status != row["health"]:
                audit(conn, owner["user_id"], "module.health." + status, module_id)
                if status == "healthy" and row["health"] in {"unhealthy", "unreachable"}:
                    notice(conn, "nexus", f"Module {module_id} recovered.")
            if status in {"unhealthy", "unreachable"} and status != row["health"]:
                notice(conn, "nexus", f"Module {module_id} is {status}.")
        return {"status": status, "checked_at": now()}

    @app.api_route(
        "/modules/{module_id}/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        include_in_schema=False,
    )
    async def gateway(module_id: str, path: str, request: Request, owner=Depends(require_owner)):
        row = get_module(module_id)
        if row["state"] != "enabled":
            raise HTTPException(409, "Module is not enabled")
        if (
            any(part in {".", ".."} for part in path.split("/"))
            or any(c in path for c in "\\%?#")
            or path.startswith("/")
        ):
            raise HTTPException(400, "Invalid module path")
        routes = json.loads(row["manifest"])["routes"]
        target_path = "/" + path if path else routes["ui"]
        # Run blocking I/O off the event loop: modules can call Nexus during a gateway request.
        from starlette.concurrency import run_in_threadpool

        code, content_type, content = await run_in_threadpool(
            upstream,
            row,
            request.method,
            target_path + ("?" + request.url.query if request.url.query else ""),
            await request.body(),
        )
        # Never forward cookies, redirects, authentication headers, CORS or module CSP.
        if 300 <= code < 400:
            raise HTTPException(502, "Module redirects are not supported in protocol v1")
        return Response(
            content,
            status_code=code,
            headers={
                "Content-Type": content_type,
                "Content-Security-Policy": "sandbox allow-scripts allow-downloads; default-src 'none'; style-src 'unsafe-inline'; img-src data:; script-src 'unsafe-inline'; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'",
            },
        )

    from nexus.blobs import add_blob_routes

    add_blob_routes(app, db, data, require_module, capability)

    @app.get("/api/v1/module/context")
    def module_context(module=Depends(require_module)):
        return {
            "id": module["id"],
            "nexus_version": VERSION,
            "protocol": 1,
            "capabilities": module["manifest"]["capabilities"],
            "resources": module["manifest"].get("resources", []),
            "references": module["manifest"].get("references"),
        }

    @app.post("/api/v1/module/events", status_code=201)
    def publish(body: Event, module=Depends(require_module)):
        capability(module, "events.publish")
        if (
            body.type.startswith("nexus.")
            or body.type not in module["manifest"]["events"]["produces"]
        ):
            raise HTTPException(403, "Event type was not declared")
        if len(json.dumps(body.payload).encode()) > 16384:
            raise HTTPException(422, "Event payload exceeds 16 KiB")
        envelope = {
            "id": str(uuid.uuid4()),
            "type": body.type,
            "source": module["id"],
            "timestamp": now(),
            "schema_version": 1,
            "payload": body.payload,
            "correlation_id": str(body.correlation_id) if body.correlation_id else None,
        }
        with db.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO events(id,type,source,timestamp,envelope) VALUES(?,?,?,?,?)",
                (
                    envelope["id"],
                    body.type,
                    module["id"],
                    envelope["timestamp"],
                    json.dumps(envelope),
                ),
            )
            sequence = cursor.lastrowid
            conn.execute(
                "DELETE FROM events WHERE seq <= (SELECT COALESCE(MAX(seq),0)-10000 FROM events)"
            )
        return {"sequence": sequence, "event": envelope}

    @app.get("/api/v1/module/events")
    def consume(after: int = Query(0, ge=0), module=Depends(require_module)):
        capability(module, "events.subscribe")
        types = module["manifest"]["events"]["consumes"]
        with db.connect() as conn:
            oldest = conn.execute("SELECT COALESCE(MIN(seq),0) FROM events").fetchone()[0]
            latest = conn.execute("SELECT COALESCE(MAX(seq),0) FROM events").fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT 100", (after,)
            ).fetchall()
        return {
            "events": [
                {"sequence": row["seq"], "event": json.loads(row["envelope"])}
                for row in rows
                if row["type"] in types and event_visible(module, json.loads(row["envelope"]), db)
            ],
            "next_cursor": rows[-1]["seq"] if rows else max(after, latest),
            "retention_gap": bool(after and oldest > after + 1),
        }

    @app.post("/api/v1/module/notifications", status_code=201)
    def module_notice(body: Notification, module=Depends(require_module)):
        capability(module, "notifications.publish")
        with db.connect() as conn:
            notice(conn, module["id"], body.message)
        return {"ok": True}

    @app.get("/api/v1/notifications")
    def notifications(owner=Depends(require_owner)):
        with db.connect() as conn:
            return [
                dict(row)
                for row in conn.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT 100")
            ]

    @app.post("/api/v1/notifications/read")
    def read_notifications(owner=Depends(require_owner)):
        with db.connect() as conn:
            conn.execute("UPDATE notifications SET read=1")
        return {"ok": True}

    @app.get("/api/v1/activity", deprecated=True)
    @app.get("/api/v1/activity/entries")
    def activity(
        before: int | None = Query(None, ge=1),
        limit: int = Query(50, ge=1, le=100),
        owner=Depends(require_owner),
    ):
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT audit.*, COALESCE(users.username,audit.actor) AS actor_name FROM audit LEFT JOIN users ON users.id=audit.actor WHERE (? IS NULL OR audit.id<?) ORDER BY audit.id DESC LIMIT ?",
                (before, before, limit + 1),
            ).fetchall()
        items = rows[:limit]
        return {
            "items": [
                {
                    "id": row["id"],
                    "kind": row["action"],
                    "subject": row["target"],
                    "actor": row["actor_name"],
                    "occurred_at": row["timestamp"],
                }
                for row in items
            ],
            "next_cursor": items[-1]["id"] if items else before,
            "has_more": len(rows) > limit,
        }

    @app.get("/api/v1/audit")
    def audit_log(owner=Depends(require_owner)):
        with db.connect() as conn:
            return [
                dict(row) for row in conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 100")
            ]

    @app.get("/api/v1/export")
    def export(owner=Depends(require_owner)):
        with db.connect() as conn:
            result = {
                "format": "empyrean-nexus-export",
                "version": 1,
                "created_at": now(),
                "settings": [dict(row) for row in conn.execute("SELECT * FROM settings")],
                "modules": [inspect_row(row) for row in conn.execute("SELECT * FROM modules")],
                "events": [
                    json.loads(row[0]) for row in conn.execute("SELECT envelope FROM events")
                ],
                "notifications": [dict(row) for row in conn.execute("SELECT * FROM notifications")],
                "audit": [dict(row) for row in conn.execute("SELECT * FROM audit")],
                "references": [
                    edge_json(row) for row in conn.execute("SELECT * FROM resource_references")
                ],
            }
            audit(conn, owner["user_id"], "metadata.exported", "nexus")
        return JSONResponse(
            result, headers={"Content-Disposition": 'attachment; filename="nexus-export.json"'}
        )

    add_reference_routes(app, db, require_module, require_owner, runtime, transport)
    add_navigation_routes(app, db, require_owner, audit)
    ctx = SimpleNamespace(
        db=db,
        runtime=runtime,
        transport=transport,
        data=data,
        lock=lifecycle_lock,
        audit=audit,
        notice=notice,
        upstream=upstream,
        require_owner=require_owner,
        validate=validate,
        now=now,
    )
    create_backup = add_recovery_routes(app, ctx)
    add_update_routes(app, ctx, create_backup)

    app.mount("/assets", StaticFiles(directory=ROOT / "frontend"), name="assets")

    @app.get("/app/{path:path}", include_in_schema=False)
    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(ROOT / "frontend/index.html")

    return app
