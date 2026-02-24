"""Session lifecycle management — wraps storage operations with business logic."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from typing import Any

from cursor_mem.config import Config
from cursor_mem.context.builder import build_context
from cursor_mem.context.injector import inject_context
from cursor_mem.storage import observation_store, session_store
from cursor_mem.summarizer.rule_based import summarize_session as rule_based_summarize

logger = logging.getLogger("cursor_mem")


class SessionManager:
    def __init__(self, conn: sqlite3.Connection, config: Config | None = None):
        self.conn = conn
        self.config = config or Config.load()

    def init_session(self, session_id: str, project: str, user_prompt: str | None = None) -> dict[str, Any]:
        sess = session_store.upsert_session(self.conn, session_id, project, user_prompt)
        logger.info("Session initialized: %s (project=%s)", session_id, project)
        return sess

    def add_observation(
        self,
        session_id: str,
        obs_type: str,
        *,
        tool_name: str | None = None,
        title: str | None = None,
        content: str | None = None,
        files: list[str] | None = None,
    ) -> int:
        session_store.upsert_session(self.conn, session_id, self._guess_project(session_id))
        obs_id = observation_store.add_observation(
            self.conn, session_id,
            obs_type=obs_type,
            tool_name=tool_name,
            title=title,
            content=content,
            files=files,
        )
        logger.debug("Observation added: id=%d session=%s type=%s", obs_id, session_id, obs_type)
        return obs_id

    async def complete_session(self, session_id: str, project_root: str | None = None) -> str:
        """Generate summary, mark session complete, and update context file."""
        sess = session_store.get_session(self.conn, session_id)
        if not sess:
            logger.warning("Session not found for completion: %s", session_id)
            return ""

        observations = observation_store.get_observations_for_session(self.conn, session_id)
        user_prompt = sess.get("user_prompt")

        if self.config.ai.enabled:
            try:
                from cursor_mem.summarizer.ai_powered import summarize_session_ai
                summary = await summarize_session_ai(observations, user_prompt, self.config)
            except Exception:
                summary = rule_based_summarize(observations, user_prompt)
        else:
            summary = rule_based_summarize(observations, user_prompt)

        session_store.complete_session(self.conn, session_id, summary)
        logger.info("Session completed: %s (obs=%d)", session_id, len(observations))

        if project_root:
            self.refresh_context(sess["project"], project_root)

        return summary

    def refresh_context(self, project: str, project_root: str) -> None:
        """Rebuild and inject context file for the project."""
        try:
            context_md = build_context(self.conn, project, self.config)
            path = inject_context(project_root, context_md)
            logger.info("Context refreshed: %s", path)
        except Exception as e:
            logger.error("Failed to refresh context: %s", e)

    def _guess_project(self, session_id: str) -> str:
        """Get project name from an existing session, or use 'default'."""
        sess = session_store.get_session(self.conn, session_id)
        return sess["project"] if sess else "default"
