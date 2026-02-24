"""Rule-based session summarizer — no AI API required.

Generates a structured summary from a session's observations by
extracting key actions, files touched, and outcomes.
"""

from __future__ import annotations

from typing import Any


def summarize_session(
    observations: list[dict[str, Any]],
    user_prompt: str | None = None,
) -> str:
    """Generate a textual summary from a list of observations."""
    if not observations:
        return user_prompt or "(空会话)"

    files_touched: list[str] = []
    shell_commands: list[str] = []
    mcp_tools: list[str] = []
    errors: list[str] = []

    for obs in observations:
        obs_type = obs.get("type", "")
        content = obs.get("content", "") or ""
        files = obs.get("files")

        if isinstance(files, list):
            for f in files:
                if f not in files_touched:
                    files_touched.append(f)

        if obs_type == "shell":
            cmd = obs.get("title", "")
            if cmd:
                shell_commands.append(cmd)
            if "error" in content.lower() or "fail" in content.lower():
                errors.append(cmd)

        elif obs_type == "mcp":
            tool = obs.get("tool_name", "")
            if tool and tool not in mcp_tools:
                mcp_tools.append(tool)

    parts: list[str] = []

    if user_prompt:
        parts.append(f"任务: {_truncate(user_prompt, 200)}")

    if files_touched:
        display_files = files_touched[:10]
        parts.append(f"修改文件: {', '.join(_shorten(f) for f in display_files)}")
        if len(files_touched) > 10:
            parts.append(f"  (共 {len(files_touched)} 个文件)")

    if shell_commands:
        unique_cmds = list(dict.fromkeys(shell_commands))[:5]
        parts.append(f"执行命令: {'; '.join(_truncate(c, 80) for c in unique_cmds)}")

    if mcp_tools:
        parts.append(f"使用工具: {', '.join(mcp_tools[:8])}")

    if errors:
        parts.append(f"遇到错误: {'; '.join(_truncate(e, 80) for e in errors[:3])}")

    stats = (
        f"统计: {len(observations)} 条操作, "
        f"{len(files_touched)} 个文件, "
        f"{len(shell_commands)} 条命令"
    )
    parts.append(stats)

    return "\n".join(parts)


def _truncate(text: str, max_len: int) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def _shorten(path: str) -> str:
    parts = path.replace("\\", "/").split("/")
    if len(parts) <= 2:
        return path
    return ".../" + "/".join(parts[-2:])
