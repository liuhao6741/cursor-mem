"""Tests for CLI commands (status, config, data)."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from cursor_mem.cli import main


runner = CliRunner()


def test_status_exits_zero():
    """cursor-mem status runs and exits 0."""
    r = runner.invoke(main, ["status"])
    assert r.exit_code == 0
    assert "Worker:" in r.output
    assert "Port:" in r.output
    assert "Data dir:" in r.output


def test_config_get_empty():
    """cursor-mem config get prints config (default)."""
    r = runner.invoke(main, ["config", "get"])
    assert r.exit_code == 0
    assert "port" in r.output.lower()


def test_config_set_and_get():
    """cursor-mem config set port 37801 then get port."""
    runner.invoke(main, ["config", "set", "port", "37801"])
    r = runner.invoke(main, ["config", "get", "port"])
    assert r.exit_code == 0
    assert "37801" in r.output
    # Restore for other tests
    runner.invoke(main, ["config", "set", "port", "37800"])


def test_data_stats():
    """cursor-mem data stats runs."""
    r = runner.invoke(main, ["data", "stats"])
    assert r.exit_code == 0
    assert "Sessions:" in r.output or "sessions" in r.output.lower()


def test_data_projects():
    """cursor-mem data projects runs."""
    r = runner.invoke(main, ["data", "projects"])
    assert r.exit_code == 0
