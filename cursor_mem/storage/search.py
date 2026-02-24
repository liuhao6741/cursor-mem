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
) -> list[dict[str, Any]]:
    """Full-text search on observations. Returns matches ranked by relevance."""
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

    where = " AND ".join(clauses)
    params.extend([limit, offset])

    rows = conn.execute(
        f"SELECT o.*, s.project, rank "
        f"FROM observations_fts f {joins} "
        f"WHERE {where} "
        f"ORDER BY rank "
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
