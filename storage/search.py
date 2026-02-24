"""FTS5 full-text search across observations and sessions."""

from __future__ import annotations

import sqlite3
from typing import Any


def search_observations(
    conn: sqlite3.Connection,
    query: str,
    project: str | None = None,
    obs_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
    date_start: str | None = None,
    date_end: str | None = None,
    order_by: str = "relevance",
) -> list[dict[str, Any]]:
    """Full-text search on observations with optional date range and ordering."""
    fts_query = _sanitize_fts_query(query)
    if not fts_query:
        return []

    joins = "JOIN observations o ON f.rowid = o.id JOIN sessions s ON o.session_id = s.id"
    clauses = ["observations_fts MATCH ?"]
    params: list[Any] = [fts_query]

    if project:
        clauses.append("s.project = ?")
        params.append(project)
    if obs_type:
        clauses.append("o.type = ?")
        params.append(obs_type)
    if date_start:
        clauses.append("o.created_at >= ?")
        params.append(date_start)
    if date_end:
        clauses.append("o.created_at <= ?")
        params.append(date_end + " 23:59:59" if len(date_end) == 10 else date_end)

    where = " AND ".join(clauses)

    if order_by == "date_desc":
        order = "o.created_at DESC"
    elif order_by == "date_asc":
        order = "o.created_at ASC"
    else:
        order = "rank"

    params.extend([limit, offset])

    rows = conn.execute(
        f"SELECT o.*, s.project, rank "
        f"FROM observations_fts f {joins} "
        f"WHERE {where} "
        f"ORDER BY {order} "
        f"LIMIT ? OFFSET ?",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def search_sessions(
    conn: sqlite3.Connection,
    query: str,
    project: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Full-text search on session summaries."""
    fts_query = _sanitize_fts_query(query)
    if not fts_query:
        return []

    clauses = ["sessions_fts MATCH ?"]
    params: list[Any] = [fts_query]

    if project:
        clauses.append("s.project = ?")
        params.append(project)

    where = " AND ".join(clauses)
    params.append(limit)

    rows = conn.execute(
        f"SELECT s.*, rank "
        f"FROM sessions_fts f JOIN sessions s ON f.rowid = s.rowid "
        f"WHERE {where} "
        f"ORDER BY rank LIMIT ?",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def _sanitize_fts_query(query: str) -> str:
    """Escape special FTS5 characters and build a query string."""
    query = query.strip()
    if not query:
        return ""
    tokens = query.split()
    escaped = ['"' + t.replace('"', '""') + '"' for t in tokens if t]
    return " ".join(escaped)
