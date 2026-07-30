# db.py
# SQLite connection + schema for the auth module (users, devices,
# auth_audit_log). See specs/authentication/design.md for the schema
# rationale. Kept in its own auth.db file (git-ignored) so auth data has an
# independent lifecycle/retention policy from any future scan-event audit db.

import sqlite3
from pathlib import Path

import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'viewer')),
    is_active     INTEGER NOT NULL DEFAULT 1,
    auth_provider TEXT NOT NULL DEFAULT 'local',
    external_id   TEXT,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until  TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS devices (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    label         TEXT NOT NULL,
    key_hash      TEXT NOT NULL UNIQUE,
    owner_user_id INTEGER REFERENCES users(id),
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    last_used_at  TEXT,
    revoked_at    TEXT
);

CREATE TABLE IF NOT EXISTS auth_audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT NOT NULL DEFAULT (datetime('now')),
    actor_user_id INTEGER,
    actor_label   TEXT,
    action        TEXT NOT NULL,
    target        TEXT,
    success       INTEGER NOT NULL,
    detail        TEXT
);
"""


def get_connection() -> sqlite3.Connection:
    """
    Opens a connection to the auth database, creating the schema on first
    use. Callers are responsible for closing the connection (or use it as
    a context manager).

    Reads config.AUTH_DB_PATH at call time (not import time) so tests can
    monkeypatch it to a temp file per test.
    """
    db_path = Path(config.AUTH_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    return conn
