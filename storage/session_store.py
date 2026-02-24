"""CRUD operations for the sessions table."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def upsert_session(
    conn: sqlite3.Connection,
    session_id: str,
    project: str,
    user_prompt: str | None = None,
) -> dict[str, Any]:
    """Create a new session or update its timestamp if it already exists."""
    now = _now()
    existing = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE sessions SET updated_at = ?, user_prompt = COALESCE(?, user_prompt) WHERE id = ?",
            (now, user_prompt, session_id),
        )
    else:
        conn.execute(
            "INSERT INTO sessions (id, project, status, created_at, updated_at, user_prompt) "
            "VALUES (?, ?, 'active', ?, ?, ?)",
            (session_id, project, now, now, user_prompt),
        )
    conn.commit()
    return dict(conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone())


def complete_session(conn: sqlite3.Connection, session_id: str, summary: str | None = None) -> None:
    """Mark session as completed, optionally storing a summary."""
    conn.execute(
        "UPDATE sessions SET status = 'completed', summary = COALESCE(?, summary), updated_at = ? WHERE id = ?",
        (summary, _now(), session_id),
    )
    conn.commit()


def get_session(conn: sqlite3.Connection, session_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return dict(row) if row else None


def get_recent_sessions(
    conn: sqlite3.Connection,
    project: str | None = None,
    limit: int = 10,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent sessions ordered by updated_at DESC."""
    clauses: list[str] = []
    params: list[Any] = []
    if project:
        clauses.append("project = ?")
        params.append(project)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    rows = conn.execute(
        f"SELECT * FROM sessions{where} ORDER BY updated_at DESC LIMIT ?", params
    ).fetchall()
    return [dict(r) for r in rows]


def get_session_stats(conn: sqlite3.Connection, project: str | None = None) -> dict[str, Any]:
    """Return aggregate stats."""
    where = " WHERE project = ?" if project else ""
    params: tuple = (project,) if project else ()
    row = conn.execute(
        f"SELECT COUNT(*) as total, "
        f"SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) as active, "
        f"SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed "
        f"FROM sessions{where}",
        params,
    ).fetchone()
    obs_row = conn.execute(
        f"SELECT COUNT(*) as total_observations FROM observations o "
        f"JOIN sessions s ON o.session_id = s.id{' WHERE s.project = ?' if project else ''}",
        params,
    ).fetchone()
    return {
        "sessions_total": row["total"],
        "sessions_active": row["active"],
        "sessions_completed": row["completed"],
        "total_observations": obs_row["total_observations"],
    }


def delete_old_sessions(conn: sqlite3.Connection, keep_days: int = 30, project: str | None = None) -> int:
    """Delete sessions older than keep_days. Returns number deleted."""
    clauses = ["updated_at < datetime('now', ?)", "status = 'completed'"]
    params: list[Any] = [f"-{keep_days} days"]
    if project:
        clauses.append("project = ?")
        params.append(project)
    where = " WHERE " + " AND ".join(clauses)
    cur = conn.execute(f"DELETE FROM sessions{where}", params)
    conn.commit()
    return cur.rowcount
