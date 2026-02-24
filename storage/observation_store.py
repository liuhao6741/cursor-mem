"""CRUD operations for the observations table."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def add_observation(
    conn: sqlite3.Connection,
    session_id: str,
    obs_type: str | None = None,
    *,
    type: str | None = None,
    tool_name: str | None = None,
    title: str | None = None,
    content: str | None = None,
    files: list[str] | None = None,
) -> int:
    """Insert an observation and return its id."""
    resolved_type = obs_type or type or "unknown"
    files_json = json.dumps(files, ensure_ascii=False) if files else None
    cur = conn.execute(
        "INSERT INTO observations (session_id, type, tool_name, title, content, files, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (session_id, resolved_type, tool_name, title, content, files_json, _now()),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def get_observations_for_session(
    conn: sqlite3.Connection,
    session_id: str,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return observations for a session ordered by created_at."""
    sql = "SELECT * FROM observations WHERE session_id = ? ORDER BY created_at"
    params: list[Any] = [session_id]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_recent_observations(
    conn: sqlite3.Connection,
    project: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return recent observations across sessions."""
    if project:
        rows = conn.execute(
            "SELECT o.* FROM observations o JOIN sessions s ON o.session_id = s.id "
            "WHERE s.project = ? ORDER BY o.created_at DESC LIMIT ?",
            (project, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM observations ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_observations_by_ids(
    conn: sqlite3.Connection,
    ids: list[int],
) -> list[dict[str, Any]]:
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT * FROM observations WHERE id IN ({placeholders}) ORDER BY created_at",
        ids,
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def count_observations(conn: sqlite3.Connection, session_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM observations WHERE session_id = ?", (session_id,)
    ).fetchone()
    return row["cnt"]


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    if d.get("files"):
        try:
            d["files"] = json.loads(d["files"])
        except (json.JSONDecodeError, TypeError):
            pass
    return d
