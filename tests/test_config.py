"""Tests for config load/save and set_nested."""

from __future__ import annotations

import json

import pytest

from cursor_mem.config import CONFIG_PATH, Config, DATA_DIR


def test_config_load_default():
    """Default config when no file exists."""
    # CONFIG_PATH may exist from other tests; use default by not having ai nested
    cfg = Config.load()
    if "host" in Config.__dataclass_fields__:
        assert cfg.host == "0.0.0.0"
    assert cfg.port == 37800
    assert cfg.ai.enabled is False


def test_config_save_and_load(tmp_path, monkeypatch):
    """Save and reload config."""
    monkeypatch.setattr("cursor_mem.config.CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr("cursor_mem.config.DATA_DIR", tmp_path)
    cfg = Config()
    cfg.port = 39000
    cfg.save()
    loaded = Config.load()
    assert loaded.port == 39000


def test_config_set_nested():
    """set_nested for top-level and ai.*."""
    cfg = Config.load()
    cfg.set_nested("port", "39001")
    assert cfg.port == 39001
    if "host" in Config.__dataclass_fields__:
        cfg.set_nested("host", "0.0.0.0")
        assert cfg.host == "0.0.0.0"
    cfg.set_nested("ai.enabled", "true")
    assert cfg.ai.enabled is True
    cfg.set_nested("ai.model", "gpt-4")
    assert cfg.ai.model == "gpt-4"
