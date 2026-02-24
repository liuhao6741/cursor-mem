"""MCP server exposing memory search tools to Cursor.

Run via: python3 -m cursor_mem.mcp.server
Communicates over stdio using the MCP protocol.

Implements a 3-layer progressive disclosure workflow for ~10x token savings:
  Layer 1: memory_search  — compact index (~50-100 tokens/result)
  Layer 2: memory_timeline — anchor-based context (~100-200 tokens/result)
  Layer 3: memory_get      — full details (~500-1000 tokens/result)
"""

from __future__ import annotations

import json
import sys
from typing import Any

from cursor_mem.config import Config
from cursor_mem.storage.database import init_db
from cursor_mem.storage import search as search_mod, observation_store, session_store
from cursor_mem.storage.time_display import utc_to_local


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_WORKFLOW_TEXT = (
    "3-LAYER WORKFLOW (ALWAYS FOLLOW):\n"
    "1. memory_search(query) → compact index with IDs (~50-100 tokens/result)\n"
    "2. memory_timeline(anchor=ID) → context around interesting results (~100-200 tokens/result)\n"
    "3. memory_get(ids=[...]) → full details ONLY for filtered IDs (~500-1000 tokens/result)\n"
    "NEVER fetch full details without filtering first. This achieves ~10x token savings."
)

TOOLS = [
    {
        "name": "memory_important",
        "description": (
            "3-layer search workflow guide (always visible). "
            "Read this FIRST to understand how to query cursor-mem efficiently. "
            + _WORKFLOW_TEXT
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "memory_search",
        "description": (
            "Step 1: Search the cursor-mem index. Returns a compact table of IDs, "
            "titles, types, and dates (~50-100 tokens per result). "
            "Always start here to survey what exists before fetching details."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keywords"},
                "project": {"type": "string", "description": "Project name filter (optional)"},
                "type": {"type": "string", "description": "Observation type filter: shell|file_edit|mcp|prompt (optional)"},
                "limit": {"type": "integer", "description": "Max results (default 10)", "default": 10},
                "offset": {"type": "integer", "description": "Skip first N results for pagination", "default": 0},
                "dateStart": {"type": "string", "description": "Filter by start date YYYY-MM-DD (optional)"},
                "dateEnd": {"type": "string", "description": "Filter by end date YYYY-MM-DD (optional)"},
                "orderBy": {
                    "type": "string",
                    "description": "Sort order: relevance (default), date_desc, date_asc",
                    "default": "relevance",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "memory_timeline",
        "description": (
            "Step 2: Get chronological context around a specific observation. "
            "Use 'anchor' (observation ID) with depth_before/depth_after to see "
            "what happened before and after. ~100-200 tokens per entry."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "anchor": {"type": "integer", "description": "Observation ID to center the timeline around"},
                "depth_before": {"type": "integer", "description": "Number of observations before anchor (default 3)", "default": 3},
                "depth_after": {"type": "integer", "description": "Number of observations after anchor (default 3)", "default": 3},
                "query": {"type": "string", "description": "Search query to find anchor automatically (optional, used if anchor not provided)"},
                "session_id": {"type": "string", "description": "Specific session ID (optional, fallback mode)"},
                "project": {"type": "string", "description": "Project name filter (optional)"},
                "limit": {"type": "integer", "description": "Max entries for fallback mode (default 20)", "default": 20},
            },
        },
    },
    {
        "name": "memory_get",
        "description": (
            "Step 3: Fetch full observation details by IDs (~500-1000 tokens per observation). "
            "Only use AFTER filtering with memory_search/memory_timeline. "
            "Always batch multiple IDs in a single call."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "List of observation IDs to fetch (required)",
                },
                "orderBy": {
                    "type": "string",
                    "description": "Sort order: date_asc (default), date_desc",
                    "default": "date_asc",
                },
                "limit": {"type": "integer", "description": "Max observations to return", "default": 20},
            },
            "required": ["ids"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def handle_memory_important(_args: dict[str, Any], _conn) -> str:
    return _WORKFLOW_TEXT


def handle_memory_search(args: dict[str, Any], conn) -> str:
    query = args.get("query", "")
    project = args.get("project")
    obs_type = args.get("type")
    limit = args.get("limit", 10)
    offset = args.get("offset", 0)
    date_start = args.get("dateStart")
    date_end = args.get("dateEnd")
    order_by = args.get("orderBy", "relevance")

    obs_results = search_mod.search_observations(
        conn, query,
        project=project, obs_type=obs_type,
        limit=limit, offset=offset,
        date_start=date_start, date_end=date_end,
        order_by=order_by,
    )
    sess_results = search_mod.search_sessions(conn, query, project=project, limit=5)

    parts = []
    if obs_results:
        parts.append(f"## Observations ({len(obs_results)} matches)\n")
        parts.append("| ID | Time | Title | Type |")
        parts.append("|---|---|---|---|")
        for r in obs_results:
            ts = utc_to_local(r.get("created_at", ""))
            short_ts = ts[5:16] if len(ts) >= 16 else ts
            title = _truncate(r.get("title", ""), 60)
            parts.append(f"| #{r['id']} | {short_ts} | {title} | {r.get('type', '')} |")

    if sess_results:
        parts.append(f"\n## Sessions ({len(sess_results)} matches)\n")
        parts.append("| ID | Project | Summary |")
        parts.append("|---|---|---|")
        for r in sess_results:
            sid = r["id"][:8] if r.get("id") else ""
            summary = _truncate(r.get("summary") or "", 80)
            parts.append(f"| {sid} | {r.get('project', '')} | {summary} |")

    if not parts:
        parts.append("No results found.")

    return "\n".join(parts)


def handle_memory_timeline(args: dict[str, Any], conn) -> str:
    anchor = args.get("anchor")
    depth_before = args.get("depth_before", 3)
    depth_after = args.get("depth_after", 3)
    query = args.get("query")
    session_id = args.get("session_id")
    project = args.get("project")
    limit = args.get("limit", 20)

    anchor_id = anchor

    if anchor_id is None and query:
        results = search_mod.search_observations(conn, query, project=project, limit=1)
        if results:
            anchor_id = results[0]["id"]

    if anchor_id is not None:
        obs = observation_store.get_observations_around(
            conn, anchor_id,
            depth_before=depth_before,
            depth_after=depth_after,
            project=project,
        )
    elif session_id:
        obs = observation_store.get_observations_for_session(conn, session_id, limit=limit)
    else:
        obs = observation_store.get_recent_observations(conn, project=project, limit=limit)
        obs.reverse()

    if not obs:
        return "No observations found."

    lines = ["## Timeline\n"]
    for o in obs:
        ts = utc_to_local(o.get("created_at", ""))
        short_ts = ts[5:16] if len(ts) >= 16 else ts
        marker = " **>>>**" if anchor_id is not None and o.get("id") == anchor_id else ""
        title = _truncate(o.get("title", ""), 80)
        lines.append(f"- [{short_ts}] **{o.get('type', '')}** #{o['id']}: {title}{marker}")
    return "\n".join(lines)


def handle_memory_get(args: dict[str, Any], conn) -> str:
    ids = args.get("ids", [])
    order_by = args.get("orderBy", "date_asc")
    limit = args.get("limit", 20)

    obs = observation_store.get_observations_by_ids(conn, ids)
    if not obs:
        return "No observations found for the given IDs."

    if order_by == "date_desc":
        obs = list(reversed(obs))

    obs = obs[:limit]

    parts = []
    for o in obs:
        parts.append(f"### #{o['id']} — {o.get('title', '')} ({o.get('type', '')})")
        parts.append(f"Session: {o.get('session_id', '')}")
        parts.append(f"Time: {utc_to_local(o.get('created_at', ''))}")
        content = o.get("content") or ""
        if content:
            if len(content) > 2000:
                content = content[:2000] + "\n... (truncated)"
            parts.append(f"```\n{content}\n```")
        if o.get("files"):
            files = o["files"] if isinstance(o["files"], list) else [o["files"]]
            parts.append(f"Files: {', '.join(files)}")
        parts.append("")
    return "\n".join(parts)


def _truncate(text: str, max_len: int) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


TOOL_HANDLERS = {
    "memory_important": handle_memory_important,
    "memory_search": handle_memory_search,
    "memory_timeline": handle_memory_timeline,
    "memory_get": handle_memory_get,
}


# ---------------------------------------------------------------------------
# Minimal MCP stdio server (no dependency on `mcp` package)
# ---------------------------------------------------------------------------

def run_stdio_server() -> None:
    """Run a JSON-RPC 2.0 stdio server implementing the MCP tool protocol."""
    conn = init_db()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        req_id = request.get("id")
        method = request.get("method", "")

        if method == "initialize":
            _respond(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "cursor-mem", "version": "0.2.0"},
            })
        elif method == "tools/list":
            _respond(req_id, {"tools": TOOLS})
        elif method == "tools/call":
            params = request.get("params", {})
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            handler = TOOL_HANDLERS.get(tool_name)
            if handler:
                try:
                    result_text = handler(arguments, conn)
                    _respond(req_id, {
                        "content": [{"type": "text", "text": result_text}],
                    })
                except Exception as e:
                    _respond(req_id, {
                        "content": [{"type": "text", "text": f"Error: {e}"}],
                        "isError": True,
                    })
            else:
                _error(req_id, -32601, f"Unknown tool: {tool_name}")
        elif method == "notifications/initialized":
            pass
        else:
            if req_id is not None:
                _error(req_id, -32601, f"Method not found: {method}")

    conn.close()


def _respond(req_id: Any, result: Any) -> None:
    msg = {"jsonrpc": "2.0", "id": req_id, "result": result}
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _error(req_id: Any, code: int, message: str) -> None:
    msg = {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    run_stdio_server()
