"""Tests for hook handler (event parsing and handler dispatch)."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

import pytest

# Import after conftest set env
from cursor_mem.hook_handler import (
    main,
    _extract_project,
    _extract_project_root,
    handle_before_submit_prompt,
    handle_after_shell_execution,
    handle_stop,
    HANDLERS,
)


def test_extract_project():
    """Project name from workspace_roots."""
    assert _extract_project({"workspace_roots": ["/home/user/my-project"]}) == "my-project"
    assert _extract_project({"workspace_roots": []}) == "default"


def test_extract_project_root():
    """Project root path from workspace_roots."""
    assert _extract_project_root({"workspace_roots": ["/home/user/my-project"]}) == "/home/user/my-project"
    assert _extract_project_root({}) == ""


def test_handlers_registry():
    """All expected events have handlers."""
    for name in ["beforeSubmitPrompt", "afterShellExecution", "afterFileEdit", "afterMCPExecution", "stop"]:
        assert name in HANDLERS


def test_handle_before_submit_prompt_returns_continue():
    """beforeSubmitPrompt returns continue: True for Cursor."""
    with patch("cursor_mem.hook_handler._post", return_value={"ok": True}):
        out = handle_before_submit_prompt({
            "conversation_id": "conv-1",
            "workspace_roots": ["/tmp/proj"],
            "prompt": "hello",
        })
    assert out == {"continue": True}


def test_handle_after_shell_execution():
    """afterShellExecution posts and returns empty (no Cursor block)."""
    with patch("cursor_mem.hook_handler._post", return_value={"ok": True}) as m:
        out = handle_after_shell_execution({
            "conversation_id": "c1",
            "command": "ls",
            "output": "a\nb",
        })
    assert out == {}
    assert m.called


def test_handle_stop():
    """stop handler posts summarize and returns empty."""
    with patch("cursor_mem.hook_handler._post", return_value={"ok": True}) as m:
        out = handle_stop({
            "conversation_id": "c1",
            "workspace_roots": ["/tmp/proj"],
        })
    assert out == {}
    assert m.called


def test_main_before_submit_prompt():
    """CLI main with --event beforeSubmitPrompt and JSON stdin runs without error."""
    stdin = json.dumps({
        "conversation_id": "cid",
        "workspace_roots": ["/path/to/proj"],
        "prompt": "hi",
    })
    with patch("sys.argv", ["hook_handler", "--event", "beforeSubmitPrompt"]), \
         patch("sys.stdin", StringIO(stdin)), patch("sys.stdout", StringIO()), \
         patch("cursor_mem.hook_handler._post", return_value={"ok": True}):
        main()
    # No exception; handler ran and returned continue: True (written to stdout)
