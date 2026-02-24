"""Build the context markdown to inject into Cursor rules file.

Assembles recent session summaries and observations into a structured
markdown document that fits within the configured token budget.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from cursor_mem.config import Config
from cursor_mem.context.compressor import deduplicate_observations, estimate_tokens
from cursor_mem.storage import session_store, observation_store
from cursor_mem.storage.time_display import DISPLAY_FMT, utc_to_local


def build_context(conn: sqlite3.Connection, project: str, config: Config | None = None) -> str:
    """Build the full context markdown for a project."""
    cfg = config or Config.load()
    budget = _adaptive_budget(conn, project, cfg)
    max_sessions = cfg.max_sessions_in_context

    sections: list[str] = []
    used_tokens = 0

    header = "# 历史会话记忆 (cursor-mem)\n"
    used_tokens += estimate_tokens(header)
    sections.append(header)

    # -- recent session summaries --
    sessions = session_store.get_recent_sessions(
        conn, project=project, limit=max_sessions, status="completed"
    )

    if sessions:
        summary_section = _build_summaries_section(sessions, budget - used_tokens)
        used_tokens += estimate_tokens(summary_section)
        sections.append(summary_section)

    # -- latest session's observations (most detailed) --
    latest_sessions = session_store.get_recent_sessions(conn, project=project, limit=1)
    if latest_sessions:
        latest = latest_sessions[0]
        obs_list = observation_store.get_observations_for_session(conn, latest["id"])
        obs_list = deduplicate_observations(obs_list)
        if obs_list:
            obs_section = _build_observations_section(latest, obs_list, budget - used_tokens)
            used_tokens += estimate_tokens(obs_section)
            sections.append(obs_section)

    # -- project-level key files (from all recent observations) --
    recent_obs = observation_store.get_recent_observations(conn, project=project, limit=100)
    file_section = _build_files_section(recent_obs, budget - used_tokens)
    if file_section:
        used_tokens += estimate_tokens(file_section)
        sections.append(file_section)

    mcp_hint = (
        "\n## 查询更多历史\n\n"
        "如需更多历史细节，使用 MCP 三层检索（~10x token 节省）：\n"
        "1. `memory_search(query)` → 紧凑索引\n"
        "2. `memory_timeline(anchor=ID)` → 上下文\n"
        "3. `memory_get(ids=[...])` → 完整详情\n"
    )
    sections.append(mcp_hint)

    footer = f"\n---\n*cursor-mem auto-updated | {datetime.now().strftime(DISPLAY_FMT)}*\n"
    sections.append(footer)

    return "\n".join(sections)


def _build_summaries_section(sessions: list[dict[str, Any]], budget: int) -> str:
    """Format session summaries."""
    lines = ["## 近期会话摘要\n"]
    tokens_used = estimate_tokens(lines[0])

    for sess in sessions:
        summary = sess.get("summary") or "(无摘要)"
        prompt = sess.get("user_prompt") or ""
        ts = utc_to_local(sess.get("created_at", ""))

        entry_lines = [f"### {ts}"]
        if prompt:
            entry_lines.append(f"- **问题**: {_truncate(prompt, 200)}")
        entry_lines.append(f"- **摘要**: {_truncate(summary, 500)}")
        entry_lines.append("")

        entry = "\n".join(entry_lines)
        entry_tokens = estimate_tokens(entry)
        if tokens_used + entry_tokens > budget:
            break
        lines.append(entry)
        tokens_used += entry_tokens

    return "\n".join(lines)


def _build_observations_section(
    session: dict[str, Any], observations: list[dict[str, Any]], budget: int
) -> str:
    """Format the latest session's observations."""
    session_ts = utc_to_local(session.get("created_at", ""))[:16]
    header = f"## 最近操作 (会话 {session_ts})\n"
    lines = [header]
    tokens_used = estimate_tokens(header)

    for obs in observations:
        obs_type = obs.get("type", "")
        title = obs.get("title", "")
        content = obs.get("content", "")
        ts = utc_to_local(obs.get("created_at", ""))[11:19]  # HH:MM:SS

        if obs_type == "prompt":
            entry = f"- [{ts}] **prompt**: {_truncate(title, 150)}"
        elif obs_type == "shell":
            entry = f"- [{ts}] `{_truncate(title, 100)}`"
        elif obs_type == "file_edit":
            entry = f"- [{ts}] {title}: {_truncate(content, 100)}"
        elif obs_type == "mcp":
            entry = f"- [{ts}] {title}"
        else:
            entry = f"- [{ts}] {obs_type}: {_truncate(title, 100)}"

        entry_tokens = estimate_tokens(entry)
        if tokens_used + entry_tokens > budget:
            lines.append(f"- ... ({len(observations) - len(lines) + 1} more)")
            break
        lines.append(entry)
        tokens_used += entry_tokens

    return "\n".join(lines)


def _build_files_section(observations: list[dict[str, Any]], budget: int) -> str:
    """Extract frequently touched files across recent observations."""
    file_counts: dict[str, int] = {}
    for obs in observations:
        files = obs.get("files")
        if isinstance(files, list):
            for f in files:
                file_counts[f] = file_counts.get(f, 0) + 1

    if not file_counts:
        return ""

    sorted_files = sorted(file_counts.items(), key=lambda x: -x[1])[:15]

    lines = ["## 项目关键文件\n"]
    for filepath, count in sorted_files:
        lines.append(f"- `{filepath}` ({count}x)")

    section = "\n".join(lines)
    if estimate_tokens(section) > budget:
        return ""
    return section


def _adaptive_budget(conn: sqlite3.Connection, project: str, config: Config) -> int:
    """Scale the context budget based on project history depth.

    New projects with few sessions get a smaller budget (less noise),
    mature projects get the full configured budget.
    """
    base = config.context_budget
    stats = session_store.get_session_stats(conn, project=project)
    total = stats.get("sessions_total", 0) or 0
    if total <= 1:
        return min(base, 1200)
    elif total <= 5:
        return min(base, 2000)
    return base


def _truncate(text: str, max_len: int) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= max_len else text[: max_len - 3] + "..."
