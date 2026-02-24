"""FastAPI routes for the worker HTTP service."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from cursor_mem.storage import session_store, observation_store, search
from cursor_mem.worker.session_manager import SessionManager

logger = logging.getLogger("cursor_mem")

router = APIRouter()

# SSE subscribers for the web viewer
_sse_subscribers: list[asyncio.Queue] = []


def _get_manager(request: Request) -> SessionManager:
    return request.app.state.session_manager


def _get_conn(request: Request):
    return request.app.state.db_conn


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/api/health")
async def health():
    return {"status": "ok", "service": "cursor-mem"}


@router.get("/api/readiness")
async def readiness(request: Request):
    try:
        conn = _get_conn(request)
        conn.execute("SELECT 1").fetchone()
        return {"status": "ready"}
    except Exception as e:
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=503)


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

@router.post("/api/session/init")
async def session_init(request: Request):
    body = await request.json()
    session_id = body.get("session_id", "")
    project = body.get("project", "default")
    user_prompt = body.get("user_prompt")
    project_root = body.get("project_root")

    manager = _get_manager(request)
    sess = manager.init_session(session_id, project, user_prompt)

    if project_root:
        manager.refresh_context(project, project_root)

    return {"ok": True, "session": sess}


@router.post("/api/session/summarize")
async def session_summarize(request: Request):
    body = await request.json()
    session_id = body.get("session_id", "")
    project_root = body.get("project_root")

    manager = _get_manager(request)
    summary = await manager.complete_session(session_id, project_root)

    _broadcast_sse({"event": "session_completed", "session_id": session_id})
    return {"ok": True, "summary": summary}


@router.get("/api/sessions")
async def list_sessions(request: Request, project: str | None = None, limit: int = 20):
    conn = _get_conn(request)
    sessions = session_store.get_recent_sessions(conn, project=project, limit=limit)
    return {"sessions": sessions}


@router.get("/api/sessions/{session_id}")
async def get_session(request: Request, session_id: str):
    conn = _get_conn(request)
    sess = session_store.get_session(conn, session_id)
    if not sess:
        return JSONResponse({"error": "not found"}, status_code=404)
    observations = observation_store.get_observations_for_session(conn, session_id)
    return {"session": sess, "observations": observations}


@router.get("/api/stats")
async def stats(request: Request, project: str | None = None):
    conn = _get_conn(request)
    return session_store.get_session_stats(conn, project=project)


# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------

@router.post("/api/observations")
async def add_observation(request: Request):
    body = await request.json()
    session_id = body.get("session_id", "")
    obs_type = body.get("type", "")

    manager = _get_manager(request)
    obs_id = manager.add_observation(
        session_id,
        obs_type,
        tool_name=body.get("tool_name"),
        title=body.get("title"),
        content=body.get("content"),
        files=body.get("files"),
    )
    _broadcast_sse({"event": "observation_added", "id": obs_id, "type": obs_type})
    return {"ok": True, "id": obs_id}


@router.get("/api/observations")
async def list_observations(request: Request, session_id: str | None = None, project: str | None = None, limit: int = 50):
    conn = _get_conn(request)
    if session_id:
        obs = observation_store.get_observations_for_session(conn, session_id, limit=limit)
    else:
        obs = observation_store.get_recent_observations(conn, project=project, limit=limit)
    return {"observations": obs}


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

@router.get("/api/context/build")
async def context_build(request: Request, project: str = "default"):
    from cursor_mem.context.builder import build_context
    conn = _get_conn(request)
    config = request.app.state.config
    md = build_context(conn, project, config)
    return {"context": md}


@router.post("/api/context/inject")
async def context_inject(request: Request):
    body = await request.json()
    project = body.get("project", "default")
    project_root = body.get("project_root", "")
    if not project_root:
        return JSONResponse({"error": "project_root required"}, status_code=400)

    manager = _get_manager(request)
    manager.refresh_context(project, project_root)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Search (Phase 2)
# ---------------------------------------------------------------------------

@router.get("/api/search/observations")
async def search_observations_route(
    request: Request,
    q: str = "",
    project: str | None = None,
    type: str | None = None,
    limit: int = 20,
    offset: int = 0,
):
    if not q:
        return {"results": []}
    conn = _get_conn(request)
    results = search.search_observations(conn, q, project=project, obs_type=type, limit=limit, offset=offset)
    return {"results": results, "query": q}


@router.get("/api/search/sessions")
async def search_sessions_route(
    request: Request,
    q: str = "",
    project: str | None = None,
    limit: int = 10,
):
    if not q:
        return {"results": []}
    conn = _get_conn(request)
    results = search.search_sessions(conn, q, project=project, limit=limit)
    return {"results": results, "query": q}


@router.get("/api/timeline")
async def timeline(
    request: Request,
    project: str | None = None,
    session_id: str | None = None,
    limit: int = 30,
):
    """Chronological timeline of observations."""
    conn = _get_conn(request)
    if session_id:
        obs = observation_store.get_observations_for_session(conn, session_id, limit=limit)
    else:
        obs = observation_store.get_recent_observations(conn, project=project, limit=limit)
    obs.reverse()
    return {"timeline": obs}


@router.get("/api/observations/batch")
async def get_observations_batch(request: Request, ids: str = ""):
    """Get observations by comma-separated IDs."""
    if not ids:
        return {"observations": []}
    conn = _get_conn(request)
    id_list = [int(i.strip()) for i in ids.split(",") if i.strip().isdigit()]
    obs = observation_store.get_observations_by_ids(conn, id_list)
    return {"observations": obs}


# ---------------------------------------------------------------------------
# SSE for web viewer (Phase 2)
# ---------------------------------------------------------------------------

@router.get("/api/events")
async def sse_events(request: Request):
    queue: asyncio.Queue = asyncio.Queue()
    _sse_subscribers.append(queue)

    async def event_generator():
        try:
            yield f"data: {json.dumps({'event': 'connected'})}\n\n"
            while True:
                msg = await queue.get()
                yield f"data: {json.dumps(msg)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _sse_subscribers.remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _broadcast_sse(data: dict[str, Any]) -> None:
    for q in _sse_subscribers:
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            pass


# ---------------------------------------------------------------------------
# Data management (Phase 3)
# ---------------------------------------------------------------------------

@router.delete("/api/sessions/cleanup")
async def cleanup_sessions(request: Request, keep_days: int = 30, project: str | None = None):
    conn = _get_conn(request)
    deleted = session_store.delete_old_sessions(conn, keep_days=keep_days, project=project)
    return {"deleted": deleted}
