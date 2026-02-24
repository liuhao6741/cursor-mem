# cursor-mem Roadmap

This document describes version planning and feature evolution for cursor-mem.

---

## Status Legend

- **Done**: Shipped or merged to main
- **In progress**: Current release
- **Planned**: Future releases or TBD priority

---

## Done

### Core (v0.1.x)

- **Cursor Hooks**
  - beforeSubmitPrompt: session init and context injection
  - afterShellExecution / afterFileEdit / afterMCPExecution: record operations
  - stop: session summary and context refresh
- **Local storage**
  - SQLite + WAL, sessions / observations tables
  - FTS5 full-text index (observations_fts, sessions_fts)
  - Multi-project isolation (filter by project)
- **Context injection**
  - Recent session summaries + latest operations timeline + project key files
  - Token budget and adaptive budget (smaller for new projects)
  - Write to `.cursor/rules/cursor-mem.mdc`, alwaysApply
- **Rule-based compression and summarization**
  - Shell / file_edit / mcp / prompt compression without API
  - Rule-based session summary (task, files, commands, tools, errors, stats)
- **Worker HTTP service**
  - FastAPI: session and observation CRUD, search, timeline, stats
  - Context build and inject API
  - SSE for web viewer
- **CLI**
  - install / uninstall (including --global)
  - start / stop / restart / status
  - config set / get
  - data stats / projects / cleanup / export
- **MCP tools**
  - memory_search: full-text search over observations and sessions
  - memory_timeline: timeline by session or project
  - memory_get: observation details by ID
- **Optional AI summarization**
  - Any OpenAI-compatible API (e.g. Gemini)
  - Fallback to rule-based on failure
- **Web viewer**
  - Session list and details, observation timeline, full-text search, SSE live updates
- **Time display**
  - Store UTC, display in local timezone (time_display module)

### Delivery & quality

- PyPI release (pip install cursor-mem)
- Single package, minimal deps (click, fastapi, uvicorn, httpx)
- Tests: pytest for config, storage, compressor, hook_handler, worker routes, CLI
- Docs: README, README_CN, TESTING.md

---

## In progress / Short term (v0.2.x)

- **Stability and UX**
  - More edge-case tests (no network, worker down, large payloads)
  - Clearer logs and errors
- **Config and observability**
  - Configurable Worker bind address (default 127.0.0.1:37800)
  - Richer status output (e.g. per-project session counts)
- **Docs and examples**
  - Design doc, user manual, roadmap (this doc)
  - Optional: sample project or screencast

---

## Planned (medium term)

- **Search**
  - Optional vector search (e.g. local embedding + vector DB) alongside FTS5
  - Finer filters (time range, file path)
- **Context strategy**
  - Configurable strategies (summary-only, summary + recent ops, key-file weight)
  - Session labels or “important session” for priority injection
- **Data and privacy**
  - Richer export (e.g. Markdown, per-project)
  - Sensitive-field redaction or exclusion
- **Install and integration**
  - Optional Cursor extension or one-click install
  - Clear upgrade and migration notes

---

## Planned (long term / exploration)

- **Multi-IDE**
  - Explore Hook/API adaptation for other editors where the architecture allows
- **Collaboration and sync**
  - Exploration only: shared team memory, read-only snapshots; privacy and complexity must be addressed
- **Scale**
  - Index and query tuning for large session counts
  - Optional observation sampling or archival

---

## Versioning

- **Major**: Breaking API or config changes
- **Minor**: New features, backward-compatible improvements
- **Patch**: Bug fixes, docs, small tweaks

Current line is **0.1.x**. After 0.2, short-term items above will be prioritized; medium/long-term items may be adjusted by feedback.

---

*Last updated to match the repository.*

**[中文版 (Chinese)](ROADMAP_CN.md)**
