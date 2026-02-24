"""Rule-based compression for observations and sessions.

Extracts key information from raw hook data, deduplicates, and
truncates to fit within the context budget — all without AI.
"""

from __future__ import annotations

import json
import re
from typing import Any


# ---------------------------------------------------------------------------
# Per-observation compression (raw hook input → compact record)
# ---------------------------------------------------------------------------

def compress_shell(hook_input: dict[str, Any]) -> dict[str, Any]:
    """Compress an afterShellExecution hook payload."""
    command = hook_input.get("command", "")
    output = hook_input.get("output", "")
    duration = hook_input.get("duration")

    output_lines = output.strip().splitlines()
    truncated = output_lines[:5]
    if len(output_lines) > 5:
        truncated.append(f"... ({len(output_lines) - 5} more lines)")

    title = _truncate(command, 120)
    content_parts = [f"$ {command}"]
    if truncated:
        content_parts.append("\n".join(truncated))
    if duration is not None:
        content_parts.append(f"({duration}ms)")

    return {
        "type": "shell",
        "tool_name": "shell",
        "title": title,
        "content": "\n".join(content_parts),
        "files": _extract_file_paths(command),
    }


def compress_file_edit(hook_input: dict[str, Any]) -> dict[str, Any]:
    """Compress an afterFileEdit hook payload."""
    file_path = hook_input.get("file_path", "")
    edits = hook_input.get("edits", [])

    edit_summaries = []
    for edit in edits[:5]:
        old = edit.get("old_string", "")
        new = edit.get("new_string", "")
        old_lines = len(old.splitlines()) if old else 0
        new_lines = len(new.splitlines()) if new else 0
        if not old:
            edit_summaries.append(f"+{new_lines} lines (new content)")
        elif not new:
            edit_summaries.append(f"-{old_lines} lines (deleted)")
        else:
            edit_summaries.append(f"-{old_lines}/+{new_lines} lines")

    if len(edits) > 5:
        edit_summaries.append(f"... ({len(edits) - 5} more edits)")

    short_path = _shorten_path(file_path)
    title = f"edit: {short_path}"
    content = f"{short_path}: {', '.join(edit_summaries)}" if edit_summaries else short_path

    return {
        "type": "file_edit",
        "tool_name": "file_edit",
        "title": title,
        "content": content,
        "files": [file_path] if file_path else [],
    }


def compress_mcp(hook_input: dict[str, Any]) -> dict[str, Any]:
    """Compress an afterMCPExecution hook payload."""
    tool_name = hook_input.get("tool_name", "unknown")
    tool_input = hook_input.get("tool_input", "")
    result_json = hook_input.get("result_json", "")
    duration = hook_input.get("duration")

    input_summary = _summarize_json(tool_input, max_len=200)
    result_summary = _summarize_json(result_json, max_len=200)

    title = f"mcp: {tool_name}"
    parts = [f"Tool: {tool_name}"]
    if input_summary:
        parts.append(f"Input: {input_summary}")
    if result_summary:
        parts.append(f"Result: {result_summary}")
    if duration is not None:
        parts.append(f"({duration}ms)")

    return {
        "type": "mcp",
        "tool_name": tool_name,
        "title": title,
        "content": "\n".join(parts),
        "files": [],
    }


def compress_prompt(hook_input: dict[str, Any]) -> dict[str, Any]:
    """Compress a beforeSubmitPrompt payload (user prompt)."""
    prompt = hook_input.get("prompt", "")
    title = _truncate(prompt, 120)
    return {
        "type": "prompt",
        "tool_name": None,
        "title": title,
        "content": _truncate(prompt, 500),
        "files": [],
    }


# ---------------------------------------------------------------------------
# Session-level compression
# ---------------------------------------------------------------------------

def deduplicate_observations(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge consecutive edits to the same file."""
    if not observations:
        return []

    result: list[dict[str, Any]] = []
    for obs in observations:
        if (
            result
            and obs.get("type") == "file_edit"
            and result[-1].get("type") == "file_edit"
            and obs.get("files") == result[-1].get("files")
        ):
            prev = result[-1]
            prev["content"] = prev.get("content", "") + " | " + obs.get("content", "")
            prev["title"] = prev.get("title", "")
        else:
            result.append(obs)
    return result


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for mixed content."""
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate(text: str, max_len: int) -> str:
    text = text.strip().replace("\n", " ")
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _shorten_path(path: str) -> str:
    """Keep last 3 path components."""
    parts = path.replace("\\", "/").split("/")
    if len(parts) <= 3:
        return path
    return ".../" + "/".join(parts[-3:])


def _extract_file_paths(text: str) -> list[str]:
    """Best-effort extraction of file paths from shell commands."""
    patterns = re.findall(r'(?:^|\s)((?:\.{0,2}/)?[\w./-]+\.\w+)', text)
    return list(dict.fromkeys(patterns))[:5]


def _summarize_json(data: str | dict | Any, max_len: int = 200) -> str:
    """Return a compact string summary of JSON data."""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return _truncate(data, max_len)
    if isinstance(data, dict):
        parts = [f"{k}={_truncate(str(v), 50)}" for k, v in list(data.items())[:6]]
        return _truncate(", ".join(parts), max_len)
    return _truncate(str(data), max_len)
