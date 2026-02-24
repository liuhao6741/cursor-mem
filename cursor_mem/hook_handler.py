"""Unified hook handler — single entry point for all Cursor hook events.

Called by Cursor via:
    python3 -m cursor_mem.hook_handler --event <event_name>

Reads JSON from stdin, sends data to the worker HTTP service,
and writes JSON response to stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.request import urlopen, Request
from urllib.error import URLError

from cursor_mem.context.compressor import (
    compress_file_edit,
    compress_mcp,
    compress_prompt,
    compress_shell,
)


DEFAULT_WORKER_URL = "http://127.0.0.1:37800"
TIMEOUT = 3  # seconds — hooks should never block the IDE for long


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    args = parser.parse_args()

    raw = sys.stdin.read()
    try:
        hook_input = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        hook_input = {}

    handler = HANDLERS.get(args.event)
    if handler:
        output = handler(hook_input)
    else:
        output = {}

    if output:
        sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _worker_url() -> str:
    """Read worker URL from config or use default."""
    try:
        from cursor_mem.config import Config
        cfg = Config.load()
        return f"http://127.0.0.1:{cfg.port}"
    except Exception:
        return DEFAULT_WORKER_URL


def _post(path: str, data: dict[str, Any]) -> dict[str, Any] | None:
    """Fire-and-forget POST to worker. Returns response or None on failure."""
    try:
        url = _worker_url() + path
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, OSError, json.JSONDecodeError, Exception):
        return None


def _extract_project(hook_input: dict[str, Any]) -> str:
    """Extract project name from workspace roots."""
    roots = hook_input.get("workspace_roots", [])
    if roots:
        return os.path.basename(roots[0])
    return "default"


def _extract_project_root(hook_input: dict[str, Any]) -> str:
    """Extract project root path."""
    roots = hook_input.get("workspace_roots", [])
    return roots[0] if roots else ""


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------

def handle_before_submit_prompt(hook_input: dict[str, Any]) -> dict[str, Any]:
    """Initialize session and refresh context before prompt submission."""
    session_id = hook_input.get("conversation_id", "")
    project = _extract_project(hook_input)
    project_root = _extract_project_root(hook_input)
    prompt = hook_input.get("prompt", "")

    _post("/api/session/init", {
        "session_id": session_id,
        "project": project,
        "project_root": project_root,
        "user_prompt": prompt,
    })

    if prompt:
        compressed = compress_prompt(hook_input)
        _post("/api/observations", {
            "session_id": session_id,
            **compressed,
        })

    return {"continue": True}


def handle_after_shell_execution(hook_input: dict[str, Any]) -> dict[str, Any]:
    """Capture shell command execution."""
    session_id = hook_input.get("conversation_id", "")
    compressed = compress_shell(hook_input)
    _post("/api/observations", {
        "session_id": session_id,
        **compressed,
    })
    return {}


def handle_after_file_edit(hook_input: dict[str, Any]) -> dict[str, Any]:
    """Capture file edit."""
    session_id = hook_input.get("conversation_id", "")
    compressed = compress_file_edit(hook_input)
    _post("/api/observations", {
        "session_id": session_id,
        **compressed,
    })
    return {}


def handle_after_mcp_execution(hook_input: dict[str, Any]) -> dict[str, Any]:
    """Capture MCP tool execution."""
    session_id = hook_input.get("conversation_id", "")
    compressed = compress_mcp(hook_input)
    _post("/api/observations", {
        "session_id": session_id,
        **compressed,
    })
    return {}


def handle_stop(hook_input: dict[str, Any]) -> dict[str, Any]:
    """Generate summary and update context when agent stops."""
    session_id = hook_input.get("conversation_id", "")
    project_root = _extract_project_root(hook_input)

    _post("/api/session/summarize", {
        "session_id": session_id,
        "project_root": project_root,
    })
    return {}


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

HANDLERS = {
    "beforeSubmitPrompt": handle_before_submit_prompt,
    "afterShellExecution": handle_after_shell_execution,
    "afterFileEdit": handle_after_file_edit,
    "afterMCPExecution": handle_after_mcp_execution,
    "stop": handle_stop,
}


if __name__ == "__main__":
    main()
