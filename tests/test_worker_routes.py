"""Tests for worker HTTP API (FastAPI TestClient)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cursor_mem.config import Config
from cursor_mem.worker.server import create_app


@pytest.fixture
def client():
    """Test client with lifespan so app.state (db_conn, session_manager) is set."""
    cfg = Config.load()
    app = create_app(cfg)
    with TestClient(app) as c:
        yield c


def test_health(client):
    """GET /api/health returns ok."""
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["service"] == "cursor-mem"


def test_readiness(client):
    """GET /api/readiness returns ready when DB is up."""
    r = client.get("/api/readiness")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_session_init(client):
    """POST /api/session/init creates session."""
    r = client.post("/api/session/init", json={
        "session_id": "test-session-1",
        "project": "test_proj",
        "user_prompt": "run tests",
        "project_root": "/tmp/proj",
    })
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert "session" in data


def test_observations_add_and_list(client):
    """POST /api/observations and GET /api/observations."""
    client.post("/api/session/init", json={
        "session_id": "obs-session",
        "project": "p",
        "project_root": "/tmp",
    })
    r = client.post("/api/observations", json={
        "session_id": "obs-session",
        "type": "shell",
        "title": "ls",
        "content": "file1 file2",
    })
    assert r.status_code == 200
    assert r.json().get("ok") is True
    assert "id" in r.json()

    r2 = client.get("/api/observations?session_id=obs-session")
    assert r2.status_code == 200
    obs = r2.json().get("observations", [])
    assert len(obs) >= 1
    assert any(o.get("title") == "ls" for o in obs)


def test_stats(client):
    """GET /api/stats returns session stats."""
    r = client.get("/api/stats")
    assert r.status_code == 200
    data = r.json()
    assert "sessions_total" in data


def test_search_observations_route(client):
    """GET /api/search/observations with q= returns results or []."""
    r = client.get("/api/search/observations?q=test")
    assert r.status_code == 200
    assert "results" in r.json()


def test_timeline(client):
    """GET /api/timeline returns timeline list."""
    r = client.get("/api/timeline")
    assert r.status_code == 200
    assert "timeline" in r.json()


def test_search_with_date_and_order(client):
    """GET /api/search/observations with date and order params."""
    r = client.get("/api/search/observations?q=test&dateStart=2020-01-01&orderBy=date_desc")
    assert r.status_code == 200
    assert "results" in r.json()


def test_timeline_with_anchor(client):
    """GET /api/timeline with anchor param."""
    client.post("/api/session/init", json={
        "session_id": "anchor-sess",
        "project": "p",
        "project_root": "/tmp",
    })
    r1 = client.post("/api/observations", json={
        "session_id": "anchor-sess",
        "type": "shell",
        "title": "anchor cmd",
        "content": "output",
    })
    obs_id = r1.json().get("id")

    r = client.get(f"/api/timeline?anchor={obs_id}&depth_before=2&depth_after=2")
    assert r.status_code == 200
    data = r.json()
    assert "timeline" in data
    assert data.get("anchor") == obs_id


def test_observations_batch_with_order(client):
    """GET /api/observations/batch with orderBy and limit."""
    client.post("/api/session/init", json={
        "session_id": "batch-sess",
        "project": "p",
        "project_root": "/tmp",
    })
    ids = []
    for i in range(3):
        r = client.post("/api/observations", json={
            "session_id": "batch-sess",
            "type": "shell",
            "title": f"batch_{i}",
            "content": f"out_{i}",
        })
        ids.append(str(r.json()["id"]))

    r = client.get(f"/api/observations/batch?ids={','.join(ids)}&orderBy=date_desc&limit=2")
    assert r.status_code == 200
    obs = r.json().get("observations", [])
    assert len(obs) == 2
