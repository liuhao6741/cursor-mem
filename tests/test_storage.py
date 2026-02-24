"""Tests for database and storage layer."""

from __future__ import annotations

import pytest

from cursor_mem.storage.database import init_db
from cursor_mem.storage import session_store, observation_store, search


@pytest.fixture
def conn():
    """Fresh DB connection; DB is in test data dir from conftest."""
    init_db()
    conn = init_db()
    yield conn
    conn.close()


def test_init_db(conn):
    """Schema is created and meta has schema_version."""
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    assert row is not None
    assert int(row[0]) >= 1


def test_session_upsert_and_get(conn):
    """Upsert session and get_session."""
    s = session_store.upsert_session(conn, "s1", "proj_a", "hello world")
    assert s["id"] == "s1"
    assert s["project"] == "proj_a"
    assert s["status"] == "active"
    got = session_store.get_session(conn, "s1")
    assert got["user_prompt"] == "hello world"


def test_session_complete(conn):
    """Complete session stores summary."""
    session_store.upsert_session(conn, "s2", "proj_a")
    session_store.complete_session(conn, "s2", "Summary text")
    s = session_store.get_session(conn, "s2")
    assert s["status"] == "completed"
    assert s["summary"] == "Summary text"


def test_observation_add_and_list(conn):
    """Add observation and list by session."""
    session_store.upsert_session(conn, "s3", "proj_a")
    oid = observation_store.add_observation(
        conn, "s3", type="shell", title="ls", content="output"
    )
    assert oid > 0
    obs = observation_store.get_observations_for_session(conn, "s3")
    assert len(obs) == 1
    assert obs[0]["title"] == "ls"
    assert obs[0]["type"] == "shell"


def test_search_observations(conn):
    """FTS search returns matching observations."""
    session_store.upsert_session(conn, "s4", "proj_a")
    observation_store.add_observation(
        conn, "s4", type="shell", title="run test", content="pytest ran successfully"
    )
    results = search.search_observations(conn, "pytest", limit=10)
    assert len(results) >= 1
    assert "pytest" in (results[0].get("content") or "").lower() or "pytest" in (results[0].get("title") or "").lower()


def test_get_observations_by_ids(conn):
    """Batch get by IDs."""
    session_store.upsert_session(conn, "s5", "proj_a")
    id1 = observation_store.add_observation(conn, "s5", type="shell", title="a", content="")
    id2 = observation_store.add_observation(conn, "s5", type="shell", title="b", content="")
    obs = observation_store.get_observations_by_ids(conn, [id1, id2])
    assert len(obs) == 2


def test_session_stats(conn):
    """get_session_stats returns counts."""
    session_store.upsert_session(conn, "s6", "proj_a")
    session_store.upsert_session(conn, "s7", "proj_a")
    session_store.complete_session(conn, "s6", "done")
    stats = session_store.get_session_stats(conn)
    assert stats["sessions_total"] >= 2
    assert stats["sessions_active"] >= 1
    assert stats["sessions_completed"] >= 1
