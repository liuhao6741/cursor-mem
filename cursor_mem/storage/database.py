"""SQLite database connection, schema creation, and migrations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from cursor_mem.config import DB_PATH, DATA_DIR

SCHEMA_VERSION = 1

SCHEMA_SQL = """\
-- sessions
CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,
    project         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    summary         TEXT,
    user_prompt     TEXT
);

-- observations
CREATE TABLE IF NOT EXISTS observations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    type            TEXT NOT NULL,
    tool_name       TEXT,
    title           TEXT,
    content         TEXT,
    files           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_obs_session ON observations(session_id);
CREATE INDEX IF NOT EXISTS idx_obs_type ON observations(type);
CREATE INDEX IF NOT EXISTS idx_obs_created ON observations(created_at);

-- FTS5 for observations
CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts USING fts5(
    title, content, tool_name, files,
    content=observations, content_rowid=id
);

-- FTS triggers to keep index in sync
CREATE TRIGGER IF NOT EXISTS obs_ai AFTER INSERT ON observations BEGIN
    INSERT INTO observations_fts(rowid, title, content, tool_name, files)
    VALUES (new.id, new.title, new.content, new.tool_name, new.files);
END;

CREATE TRIGGER IF NOT EXISTS obs_ad AFTER DELETE ON observations BEGIN
    INSERT INTO observations_fts(observations_fts, rowid, title, content, tool_name, files)
    VALUES ('delete', old.id, old.title, old.content, old.tool_name, old.files);
END;

CREATE TRIGGER IF NOT EXISTS obs_au AFTER UPDATE ON observations BEGIN
    INSERT INTO observations_fts(observations_fts, rowid, title, content, tool_name, files)
    VALUES ('delete', old.id, old.title, old.content, old.tool_name, old.files);
    INSERT INTO observations_fts(rowid, title, content, tool_name, files)
    VALUES (new.id, new.title, new.content, new.tool_name, new.files);
END;

-- FTS5 for sessions
CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
    summary, project, user_prompt,
    content=sessions, content_rowid=rowid
);

CREATE TRIGGER IF NOT EXISTS sess_ai AFTER INSERT ON sessions BEGIN
    INSERT INTO sessions_fts(rowid, summary, project, user_prompt)
    VALUES (new.rowid, new.summary, new.project, new.user_prompt);
END;

CREATE TRIGGER IF NOT EXISTS sess_ad AFTER DELETE ON sessions BEGIN
    INSERT INTO sessions_fts(sessions_fts, rowid, summary, project, user_prompt)
    VALUES ('delete', old.rowid, old.summary, old.project, old.user_prompt);
END;

CREATE TRIGGER IF NOT EXISTS sess_au AFTER UPDATE ON sessions BEGIN
    INSERT INTO sessions_fts(sessions_fts, rowid, summary, project, user_prompt)
    VALUES ('delete', old.rowid, old.summary, old.project, old.user_prompt);
    INSERT INTO sessions_fts(rowid, summary, project, user_prompt)
    VALUES (new.rowid, new.summary, new.project, new.user_prompt);
END;

-- meta
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Return a configured SQLite connection (WAL mode, foreign keys)."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(db_path: Path | None = None) -> sqlite3.Connection:
    """Create tables if they don't exist and run migrations."""
    conn = get_connection(db_path)

    row = None
    try:
        row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    except sqlite3.OperationalError:
        pass

    current_version = int(row["value"]) if row else 0

    if current_version < SCHEMA_VERSION:
        conn.executescript(SCHEMA_SQL)
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()

    return conn
