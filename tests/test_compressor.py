"""Tests for context compressor (hook payload -> observation record)."""

from __future__ import annotations

import pytest

from cursor_mem.context.compressor import (
    compress_shell,
    compress_file_edit,
    compress_mcp,
    compress_prompt,
    deduplicate_observations,
    estimate_tokens,
)


def test_compress_shell():
    """Shell execution is compressed to type, title, content, files."""
    out = compress_shell({
        "command": "ls -la",
        "output": "file1\nfile2\nfile3",
        "duration": 100,
    })
    assert out["type"] == "shell"
    assert "ls" in out["title"]
    assert "file1" in out["content"]


def test_compress_file_edit():
    """File edit is summarized with path and edit counts."""
    out = compress_file_edit({
        "file_path": "/a/b/c/foo.py",
        "edits": [
            {"old_string": "x", "new_string": "y"},
            {"old_string": "", "new_string": "line1\nline2"},
        ],
    })
    assert out["type"] == "file_edit"
    assert "foo.py" in out["title"]
    assert "edit" in out["title"].lower()
    assert out["files"] == ["/a/b/c/foo.py"]


def test_compress_mcp():
    """MCP execution has tool_name and input/result summary."""
    out = compress_mcp({
        "tool_name": "memory_search",
        "tool_input": '{"query": "test"}',
        "result_json": '{"results": []}',
        "duration": 50,
    })
    assert out["type"] == "mcp"
    assert out["tool_name"] == "memory_search"


def test_compress_prompt():
    """User prompt is truncated for title and content."""
    out = compress_prompt({"prompt": "Please add tests for the storage layer."})
    assert out["type"] == "prompt"
    assert "tests" in out["title"].lower() or "storage" in out["title"].lower()
    assert out["tool_name"] is None


def test_deduplicate_observations_merges_edits():
    """Consecutive file_edit to same file are merged."""
    obs = [
        {"type": "file_edit", "files": ["a.py"], "content": "first", "title": "a"},
        {"type": "file_edit", "files": ["a.py"], "content": "second", "title": "a"},
    ]
    merged = deduplicate_observations(obs)
    assert len(merged) == 1
    assert "first" in merged[0]["content"] and "second" in merged[0]["content"]


def test_estimate_tokens():
    """Rough token estimate."""
    assert estimate_tokens("hello") >= 1
    assert estimate_tokens("x" * 40) >= 10
