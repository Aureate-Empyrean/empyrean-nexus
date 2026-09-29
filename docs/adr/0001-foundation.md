# ADR 0001: Small typed HTTP core, SQLite and static UI

Status: accepted for 0.1.0.

Use Python 3.13 in Docker, FastAPI/Pydantic request validation, Argon2id, SQLite and a plain JavaScript frontend. Python's standard library supports the independent reference image. FastAPI generates the OpenAPI contract. SQLite avoids requiring a separate database service for one owner's metadata; modules cannot access its volume.

A framework-free control panel is sufficient for this vertical slice and eliminates a second dependency/build pipeline. Type validation is concentrated at backend boundaries; the browser is deliberately small, not a reusable component framework. If UI scale justifies TypeScript/components, the HTTP API and CSS tokens remain migration points.

Run one server worker. No Redis, Kafka, Kubernetes, ORM, job scheduler or per-feature microservices. The one additional broker exists because Docker authority is qualitatively different from normal application logic.

Alternatives: a TypeScript full-stack application is reasonable but would not improve this initial vertical slice enough to justify the extra tooling. PostgreSQL is a future option if concurrent writers or shared installations require it. Database migration scripts and public API objects avoid coupling modules to SQLite.

Sources: https://fastapi.tiangolo.com/features/ and https://www.sqlite.org/wal.html
