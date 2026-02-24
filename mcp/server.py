"""MCP server exposing memory search tools to Cursor.

Run via: python3 -m cursor_mem.mcp.server
Communicates over stdio using the MCP protocol.

If the `mcp` package is not installed, this module falls back to a minimal
JSON-RPC stdio implementation that covers the essential tool-calling flow.
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

TOOLS = [
    {
        "name": "memory_search",
        "description": (
            "Search the cursor-mem index for past observations and session summaries. "
            "Use this to recall what was done in previous sessions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keywords"},
                "project": {"type": "string", "description": "Project name filter (optional)"},
                "type": {"type": "string", "description": "Observation type filter: shell|file_edit|mcp|prompt (optional)"},
                "limit": {"type": "integer", "description": "Max results (default 10)", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "memory_timeline",
        "description": (
            "Get a chronological timeline of recent observations. "
            "Useful for reviewing what happened in recent sessions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Specific session ID (optional)"},
                "project": {"type": "string", "description": "Project name filter (optional)"},
                "limit": {"type": "integer", "description": "Max entries (default 20)", "default": 20},
            },
        },
    },
    {
        "name": "memory_get",
        "description": "Get full details of specific observations by their IDs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "List of observation IDs to fetch",
                },
            },
            "required": ["ids"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def handle_memory_search(args: dict[str, Any], conn) -> str:
    query = args.get("query", "")
    project = args.get("project")
    obs_type = args.get("type")
    limit = args.get("limit", 10)

    obs_results = search_mod.search_observations(conn, query, project=project, obs_type=obs_type, limit=limit)
    sess_results = search_mod.search_sessions(conn, query, project=project, limit=5)

    parts = []
    if obs_results:
        parts.append(f"## Observations ({len(obs_results)} matches)\n")
        for r in obs_results:
            parts.append(f"- [#{r['id']}] {r.get('title', '')} ({r.get('type', '')})")
    if sess_results:
        parts.append(f"\n## Sessions ({len(sess_results)} matches)\n")
        for r in sess_results:
            parts.append(f"- [{r['id'][:8]}] {r.get('project', '')} — {(r.get('summary') or '')[:100]}")
    if not parts:
        parts.append("No results found.")

    return "\n".join(parts)


def handle_memory_timeline(args: dict[str, Any], conn) -> str:
    session_id = args.get("session_id")
    project = args.get("project")
    limit = args.get("limit", 20)

    if session_id:
        obs = observation_store.get_observations_for_session(conn, session_id, limit=limit)
    else:
        obs = observation_store.get_recent_observations(conn, project=project, limit=limit)
        obs.reverse()

    if not obs:
        return "No observations found."

    lines = ["## Timeline\n"]
    for o in obs:
        ts = utc_to_local(o.get("created_at", ""))
        lines.append(f"- [{ts}] **{o.get('type', '')}** #{o['id']}: {o.get('title', '')}")
    return "\n".join(lines)


def handle_memory_get(args: dict[str, Any], conn) -> str:
    ids = args.get("ids", [])
    obs = observation_store.get_observations_by_ids(conn, ids)
    if not obs:
        return "No observations found for the given IDs."

    parts = []
    for o in obs:
        parts.append(f"### #{o['id']} — {o.get('title', '')} ({o.get('type', '')})")
        parts.append(f"Session: {o.get('session_id', '')}")
        parts.append(f"Time: {utc_to_local(o.get('created_at', ''))}")
        if o.get("content"):
            parts.append(f"```\n{o['content']}\n```")
        if o.get("files"):
            files = o["files"] if isinstance(o["files"], list) else [o["files"]]
            parts.append(f"Files: {', '.join(files)}")
        parts.append("")
    return "\n".join(parts)


TOOL_HANDLERS = {
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
                "serverInfo": {"name": "cursor-mem", "version": "0.1.0"},
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
