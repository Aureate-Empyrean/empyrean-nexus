import sqlite3
from contextlib import contextmanager
from pathlib import Path

MIGRATIONS = [
    """
    CREATE TABLE users(id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, password TEXT NOT NULL);
    CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE sessions(token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                          csrf TEXT NOT NULL, expires INTEGER NOT NULL);
    CREATE TABLE modules(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
                         manifest TEXT NOT NULL, port INTEGER NOT NULL UNIQUE,
                         state TEXT NOT NULL, token TEXT, health TEXT NOT NULL DEFAULT 'unknown',
                         source TEXT NOT NULL, installed_at TEXT NOT NULL);
    CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
                        type TEXT NOT NULL, source TEXT NOT NULL, timestamp TEXT NOT NULL,
                        envelope TEXT NOT NULL);
    CREATE TABLE notifications(id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL,
                               message TEXT NOT NULL, created_at TEXT NOT NULL, read INTEGER DEFAULT 0);
    CREATE TABLE audit(id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT NOT NULL,
                       action TEXT NOT NULL, target TEXT NOT NULL, timestamp TEXT NOT NULL);
    """,
    """
    ALTER TABLE modules ADD COLUMN resolver_key TEXT;
    CREATE TABLE resource_references(
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT NOT NULL UNIQUE,
        source TEXT NOT NULL,
        target TEXT NOT NULL,
        relation TEXT NOT NULL,
        creator TEXT NOT NULL,
        metadata TEXT NOT NULL,
        readers TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(source,target,relation)
    );
    CREATE INDEX references_source ON resource_references(source,seq);
    CREATE INDEX references_target ON resource_references(target,seq);
    CREATE INDEX references_creator ON resource_references(creator);
    """,
    """
    CREATE TABLE retained_module_data(id TEXT PRIMARY KEY);
    CREATE TABLE blobs(id TEXT PRIMARY KEY, size INTEGER NOT NULL);
    CREATE TABLE blob_grants(blob TEXT NOT NULL REFERENCES blobs(id), module TEXT NOT NULL,
                             PRIMARY KEY(blob,module));
    """,
]


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > len(MIGRATIONS):
                raise RuntimeError("Database is newer than Nexus; downgrade is unsafe")
            for index in range(version, len(MIGRATIONS)):
                db.executescript(
                    "BEGIN IMMEDIATE;\n"
                    + MIGRATIONS[index]
                    + f"\nPRAGMA user_version={index + 1};\nCOMMIT;"
                )
        path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()
