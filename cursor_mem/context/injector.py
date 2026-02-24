"""Write context to .cursor/rules/cursor-mem.mdc for Cursor to pick up."""

from __future__ import annotations

from pathlib import Path


MDC_HEADER = """\
---
alwaysApply: true
description: "cursor-mem: persistent cross-session memory (auto-updated)"
---
"""


def inject_context(project_root: str, context_markdown: str) -> Path:
    """Write the context markdown to the project's .cursor/rules/ directory.

    Returns the path to the written file.
    """
    rules_dir = Path(project_root) / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    target = rules_dir / "cursor-mem.mdc"
    target.write_text(MDC_HEADER + context_markdown, encoding="utf-8")
    return target
