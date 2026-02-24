"""Pytest configuration and fixtures. Set CURSOR_MEM_DATA_DIR before any cursor_mem import."""

from __future__ import annotations

import os
import tempfile

# Must run before cursor_mem is imported so config uses test data dir
_test_data_root = tempfile.mkdtemp(prefix="cursor_mem_test_")
os.environ["CURSOR_MEM_DATA_DIR"] = _test_data_root


def pytest_configure(config):
    """Ensure test data dir exists."""
    os.makedirs(_test_data_root, exist_ok=True)
