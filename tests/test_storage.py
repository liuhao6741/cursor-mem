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


def test_get_observations_around(conn):
    """get_observations_around returns obs before, anchor, and after."""
    session_store.upsert_session(conn, "s_around", "proj_a")
    ids = []
    for i in range(7):
        oid = observation_store.add_observation(
            conn, "s_around", type="shell", title=f"cmd_{i}", content=f"out_{i}"
        )
        ids.append(oid)

    anchor_id = ids[3]
    result = observation_store.get_observations_around(conn, anchor_id, depth_before=2, depth_after=2)
    result_ids = [o["id"] for o in result]
    assert anchor_id in result_ids
    assert len(result) == 5
    assert result_ids == ids[1:6]


def test_get_observations_around_at_start(conn):
    """Anchor near the start doesn't error."""
    session_store.upsert_session(conn, "s_start", "proj_a")
    ids = []
    for i in range(3):
        oid = observation_store.add_observation(
            conn, "s_start", type="shell", title=f"c_{i}", content=""
        )
        ids.append(oid)

    result = observation_store.get_observations_around(conn, ids[0], depth_before=5, depth_after=1)
    result_ids = [o["id"] for o in result]
    assert ids[0] in result_ids
    assert len(result) >= 1


def test_get_observations_around_not_found(conn):
    """Non-existent anchor returns empty."""
    result = observation_store.get_observations_around(conn, 999999, depth_before=2, depth_after=2)
    assert result == []


def test_search_observations_with_date_filter(conn):
    """search_observations with date_start/date_end."""
    session_store.upsert_session(conn, "s_date", "proj_a")
    observation_store.add_observation(
        conn, "s_date", type="shell", title="date test command", content="date filter test"
    )
    results = search.search_observations(conn, "date filter", date_start="2020-01-01", limit=10)
    assert len(results) >= 1

    results_future = search.search_observations(conn, "date filter", date_start="2099-01-01", limit=10)
    assert len(results_future) == 0


def test_search_observations_order_by(conn):
    """search_observations with different orderBy."""
    session_store.upsert_session(conn, "s_order", "proj_a")
    observation_store.add_observation(conn, "s_order", type="shell", title="order test alpha", content="order test")
    observation_store.add_observation(conn, "s_order", type="shell", title="order test beta", content="order test")

    by_date = search.search_observations(conn, "order test", order_by="date_desc", limit=10)
    assert len(by_date) >= 2

    by_relevance = search.search_observations(conn, "order test", order_by="relevance", limit=10)
    assert len(by_relevance) >= 2
