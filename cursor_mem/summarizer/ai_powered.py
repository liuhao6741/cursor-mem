"""AI-powered session summarizer using any OpenAI-compatible API.

Activated only when ai.enabled=true and api_key is configured.
Falls back to rule_based automatically on failure.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from cursor_mem.config import Config
from cursor_mem.summarizer.rule_based import summarize_session as rule_based_summarize

logger = logging.getLogger("cursor_mem")

SYSTEM_PROMPT = """\
You are a concise technical summarizer. Given a list of tool observations from a coding session, \
produce a structured summary in Chinese. Include:

1. 任务目标 (one sentence)
2. 关键操作 (bullet list of important actions)
3. 修改文件 (list of files changed)
4. 关键决策 (any notable design decisions)
5. 最终状态 (completed / in-progress / encountered errors)

Keep the summary under 300 characters. Be concise and specific.\
"""


async def summarize_session_ai(
    observations: list[dict[str, Any]],
    user_prompt: str | None = None,
    config: Config | None = None,
) -> str:
    """Summarize via AI API. Returns rule-based summary on failure."""
    cfg = config or Config.load()
    if not cfg.ai.enabled or not cfg.ai.api_key or not cfg.ai.base_url:
        return rule_based_summarize(observations, user_prompt)

    obs_text = _format_observations(observations, user_prompt)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            url = cfg.ai.base_url.rstrip("/") + "/chat/completions"
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {cfg.ai.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": cfg.ai.model or "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": obs_text},
                    ],
                    "max_tokens": 500,
                    "temperature": 0.3,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return content.strip()
    except Exception as e:
        logger.warning("AI summarization failed, falling back to rule-based: %s", e)
        return rule_based_summarize(observations, user_prompt)


def _format_observations(observations: list[dict[str, Any]], user_prompt: str | None) -> str:
    """Format observations into a compact text block for the AI prompt."""
    parts = []
    if user_prompt:
        parts.append(f"用户提问: {user_prompt}")
    parts.append(f"共 {len(observations)} 条操作记录:")
    for obs in observations[:30]:
        obs_type = obs.get("type", "")
        title = obs.get("title", "")
        content = obs.get("content", "")
        line = f"- [{obs_type}] {title}"
        if content and len(content) < 200:
            line += f": {content}"
        parts.append(line)
    if len(observations) > 30:
        parts.append(f"... (省略 {len(observations) - 30} 条)")
    return "\n".join(parts)
