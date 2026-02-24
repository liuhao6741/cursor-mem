"""Installation logic — generates hooks.json, registers MCP, manages worker."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

from cursor_mem.config import Config, DATA_DIR, PID_FILE


HOOKS_CONFIG = {
    "version": 1,
    "hooks": {
        "beforeSubmitPrompt": [
            {"command": f"{sys.executable} -m cursor_mem.hook_handler --event beforeSubmitPrompt"}
        ],
        "afterShellExecution": [
            {"command": f"{sys.executable} -m cursor_mem.hook_handler --event afterShellExecution"}
        ],
        "afterFileEdit": [
            {"command": f"{sys.executable} -m cursor_mem.hook_handler --event afterFileEdit"}
        ],
        "afterMCPExecution": [
            {"command": f"{sys.executable} -m cursor_mem.hook_handler --event afterMCPExecution"}
        ],
        "stop": [
            {"command": f"{sys.executable} -m cursor_mem.hook_handler --event stop"}
        ],
    },
}


def install_hooks(global_install: bool = False, project_root: str | None = None) -> Path:
    """Write hooks.json to the appropriate location.

    Returns the path where hooks.json was written.
    """
    if global_install:
        target_dir = Path.home() / ".cursor"
    else:
        root = Path(project_root) if project_root else Path.cwd()
        target_dir = root / ".cursor"

    target_dir.mkdir(parents=True, exist_ok=True)
    hooks_path = target_dir / "hooks.json"

    existing = _load_existing_hooks(hooks_path)
    merged = _merge_hooks(existing, HOOKS_CONFIG)

    hooks_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    return hooks_path


def uninstall_hooks(global_install: bool = False, project_root: str | None = None) -> bool:
    """Remove cursor-mem hooks from hooks.json."""
    if global_install:
        hooks_path = Path.home() / ".cursor" / "hooks.json"
    else:
        root = Path(project_root) if project_root else Path.cwd()
        hooks_path = root / ".cursor" / "hooks.json"

    if not hooks_path.exists():
        return False

    try:
        data = json.loads(hooks_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False

    hooks = data.get("hooks", {})
    changed = False
    for event_name, entries in hooks.items():
        if isinstance(entries, list):
            filtered = [e for e in entries if "cursor_mem" not in e.get("command", "")]
            if len(filtered) != len(entries):
                hooks[event_name] = filtered
                changed = True

    if changed:
        hooks_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return changed


def register_mcp(python_path: str | None = None) -> Path:
    """Register the MCP server in ~/.cursor/mcp.json."""
    mcp_config_path = Path.home() / ".cursor" / "mcp.json"
    py = python_path or sys.executable

    existing: dict[str, Any] = {}
    if mcp_config_path.exists():
        try:
            existing = json.loads(mcp_config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    servers = existing.setdefault("mcpServers", {})
    servers["cursor-mem"] = {
        "command": py,
        "args": ["-m", "cursor_mem.mcp.server"],
    }

    mcp_config_path.parent.mkdir(parents=True, exist_ok=True)
    mcp_config_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    return mcp_config_path


def unregister_mcp() -> bool:
    """Remove cursor-mem from ~/.cursor/mcp.json."""
    mcp_path = Path.home() / ".cursor" / "mcp.json"
    if not mcp_path.exists():
        return False
    try:
        data = json.loads(mcp_path.read_text(encoding="utf-8"))
        servers = data.get("mcpServers", {})
        if "cursor-mem" in servers:
            del servers["cursor-mem"]
            mcp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
    except (json.JSONDecodeError, OSError):
        pass
    return False


# ---------------------------------------------------------------------------
# Worker process management
# ---------------------------------------------------------------------------

def start_worker(config: Config | None = None) -> int:
    """Start the worker as a background process. Returns PID."""
    if is_worker_running():
        return _read_pid()

    cfg = config or Config.load()
    cfg.save()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        [sys.executable, "-m", "cursor_mem.worker.server"],
        stdout=subprocess.DEVNULL,
        stderr=open(DATA_DIR / "worker-stderr.log", "a"),
        start_new_session=True,
    )
    PID_FILE.write_text(str(proc.pid))
    return proc.pid


def stop_worker() -> bool:
    """Stop the worker process. Returns True if stopped."""
    pid = _read_pid()
    if not pid:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        PID_FILE.unlink(missing_ok=True)
        return True
    except (OSError, ProcessLookupError):
        PID_FILE.unlink(missing_ok=True)
        return False


def is_worker_running() -> bool:
    pid = _read_pid()
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        PID_FILE.unlink(missing_ok=True)
        return False


def _read_pid() -> int:
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text().strip())
        except (ValueError, OSError):
            pass
    return 0


def _load_existing_hooks(path: Path) -> dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _merge_hooks(existing: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Merge new hooks into existing config, avoiding duplicates."""
    result = {**existing, "version": 1}
    existing_hooks = result.get("hooks", {})
    new_hooks = new.get("hooks", {})

    for event_name, new_entries in new_hooks.items():
        current = existing_hooks.get(event_name, [])
        current_cmds = {e.get("command", "") for e in current}
        for entry in new_entries:
            if entry.get("command", "") not in current_cmds:
                current.append(entry)
        existing_hooks[event_name] = current

    result["hooks"] = existing_hooks
    return result
