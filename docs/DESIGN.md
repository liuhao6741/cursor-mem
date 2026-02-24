# cursor-mem Design Document

## 1. Overview

cursor-mem is a **persistent memory system for Cursor IDE**. It works without any API key by using Cursor’s native Hooks to record session context and keep memory across sessions.

### 1.1 Design Goals

- **Cross-session memory**: Remember recent session actions, edited files, and shell commands
- **Zero-config**: Works out of the box with rule-based compression; no API key required
- **Optional AI summarization**: Plug in any OpenAI-compatible API (e.g. free Gemini) for smarter session summaries
- **Full-text search**: SQLite FTS5 over observations and sessions
- **Agent-queryable**: MCP tools with a **3-layer progressive disclosure workflow** (~10x token savings): compact index → anchor context → full details
- **Multi-project isolation**: Separate storage and context injection per project

### 1.2 Tech Stack

| Layer        | Choice                    |
|-------------|---------------------------|
| Language    | Python 3.10+              |
| CLI         | Click                     |
| HTTP server | FastAPI + Uvicorn        |
| Storage     | SQLite (WAL + FTS5)       |
| Protocols   | Cursor Hooks JSON, MCP stdio, SSE |

---

## 2. System Architecture

### 2.1 Data Flow

```
User submits prompt
    → beforeSubmitPrompt hook
    → Worker: init session + refresh .cursor/rules/cursor-mem.mdc (inject history)

Agent runs
    → afterShellExecution / afterFileEdit / afterMCPExecution hooks
    → Hook script compresses payload → POST to Worker
    → Worker writes to SQLite

Agent stops
    → stop hook
    → Worker: generate session summary (rule-based / AI) → complete session → refresh context file again
```

### 2.2 Component Diagram

```
                    ┌─────────────────┐
                    │   Cursor IDE    │
                    │  (hooks fire)   │
                    └────────┬────────┘
                             │ JSON stdin/stdout
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  cursor_mem.hook_handler                                          │
│  - Parse --event, read stdin JSON                                 │
│  - Call compressor                                                │
│  - POST to Worker (fire-and-forget, 3s timeout)                   │
└────────┬─────────────────────────────────────────────────────────┘
         │ HTTP POST
         ▼
┌──────────────────────────────────────────────────────────────────┐
│  Worker (FastAPI, default 37800)                                  │
│  - SessionManager: session lifecycle, summarization, context    │
│  - routes: /api/session/*, /api/observations, /api/context/*,    │
│            /api/search/*, /api/timeline, /api/events (SSE)        │
└────────┬─────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────┐
│  Storage (SQLite)                                                 │
│  - sessions / observations + FTS5 (observations_fts, sessions_fts) │
│  - session_store, observation_store, search                      │
└──────────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────┐
│  Context injection                                                │
│  - context/builder: recent summaries + latest ops + key files     │
│    within token budget                                            │
│  - context/injector: write <project>/.cursor/rules/cursor-mem.mdc │
└──────────────────────────────────────────────────────────────────┘
```

In addition:

- **MCP Server** (`cursor_mem.mcp.server`) talks to Cursor over stdio and uses the same SQLite, search, observation_store, and session_store to implement the 4 tools: `memory_important`, `memory_search`, `memory_timeline`, `memory_get` (3-layer workflow).
- **Web Viewer** uses the Worker’s `/api/*` and `/api/events` (SSE) to browse sessions and timeline with live updates.

---

## 3. Core Modules

### 3.1 Config (config.py)

- **Paths**: Data dir from `CURSOR_MEM_DATA_DIR` or `~/.cursor-mem`; under it: `config.json`, `cursor-mem.db`, `logs/`, `worker.pid`.
- **Options**: `port` (default 37800), `context_budget` (default 3000, reduced for 3-layer MCP usage), `max_sessions_in_context`, `log_level`, `ai.*` (enabled, base_url, api_key, model).
- Dotted keys for `config set/get` (e.g. `ai.enabled`).

### 3.2 Installer & process (installer.py)

- **Hooks**: Merge into `~/.cursor/hooks.json` (global) or `<project>/.cursor/hooks.json`; each event runs `python -m cursor_mem.hook_handler --event <event>`.
- **MCP**: Register `cursor-mem` in `~/.cursor/mcp.json` under `mcpServers`, command `python -m cursor_mem.mcp.server`.
- **Worker**: Start `python -m cursor_mem.worker.server` in background; PID in `worker.pid`; stop with SIGTERM.

### 3.3 Hook handler (hook_handler.py)

- Entry: `python -m cursor_mem.hook_handler --event <event>`, read JSON from stdin.
- **beforeSubmitPrompt**: Extract conversation_id, workspace_roots, prompt; POST `/api/session/init`; if prompt present, compress and POST `/api/observations` (type=prompt); return `{"continue": true}`.
- **afterShellExecution** / **afterFileEdit** / **afterMCPExecution**: Compress and POST `/api/observations`.
- **stop**: POST `/api/session/summarize` to trigger summary and context refresh.
- All POSTs are fire-and-forget, 3s timeout; failures do not block the IDE.

### 3.4 Compressor (context/compressor.py)

Turns raw hook payloads into a unified structure for storage and context:

- **compress_shell**: command, first 5 lines of output, duration; title truncated to 120 chars; best-effort file path extraction from command.
- **compress_file_edit**: file_path and ±lines summary of first 5 edits; path shortened to last 3 segments.
- **compress_mcp**: tool_name, short summary of tool_input/result_json, duration.
- **compress_prompt**: prompt truncated to title(120) and content(500).
- **deduplicate_observations**: merge consecutive file_edits to the same file.
- **estimate_tokens**: rough ~4 chars per token.

### 3.5 Storage (storage/)

- **database.py**: SQLite connection (WAL, foreign_keys, busy_timeout), schema creation, version in `meta` table.
- **Tables**: `sessions` (id, project, status, created_at, updated_at, summary, user_prompt), `observations` (id, session_id, type, tool_name, title, content, files, created_at), FTS5 virtual tables + triggers, `meta`.
- **session_store**: session CRUD, recent sessions by project/status, complete session (write summary), stats, cleanup by age.
- **observation_store**: get by session or project, get by ids, insert.
- **search**: FTS5 over observations/sessions with project, obs_type, limit/offset.
- **time_display**: store UTC, display in local time (DISPLAY_FMT) for builder and MCP output.

### 3.6 Context build & inject (context/)

- **builder.build_context(conn, project, config)**: Adaptive budget by project session count; assemble header, recent session summaries, latest session observations (deduped), project key files (top 15 by frequency), **MCP usage hint** (3-layer workflow), footer with local time; truncate sections to budget; use time_display.utc_to_local.
- **injector.inject_context(project_root, context_markdown)**: Write `.cursor/rules/cursor-mem.mdc` with MDC header (alwaysApply, description).

### 3.7 Session & summarization (worker/session_manager.py, summarizer/)

- **SessionManager**: `init_session` (upsert, user_prompt), `add_observation`, `complete_session` (fetch obs, AI or rule summary, write summary, refresh_context if project_root), `refresh_context` (build + inject).
- **rule_based.summarize_session**: Extract task, files, commands, MCP tools, errors, stats from observations.
- **ai_powered** (optional): Call configured OpenAI-compatible API for summary; fallback to rule-based on failure.

### 3.8 Worker API (worker/routes.py)

- Health: `GET /api/health`, `GET /api/readiness`
- Session: `POST /api/session/init`, `POST /api/session/summarize`, `GET /api/sessions`, `GET /api/sessions/{id}`
- Observations: `POST /api/observations`, `GET /api/observations`, `GET /api/observations/batch?ids=`
- Context: `GET /api/context/build?project=`, `POST /api/context/inject`
- Search: `GET /api/search/observations`, `GET /api/search/sessions`
- Timeline: `GET /api/timeline`
- Stats: `GET /api/stats`
- SSE: `GET /api/events` (broadcast on new observation / session completed)
- Cleanup: `DELETE /api/sessions/cleanup`

### 3.9 MCP (mcp/server.py)

- JSON-RPC 2.0 over stdio; handle `initialize`, `tools/list`, `tools/call`.
- **3-layer workflow** (progressive disclosure, ~10x token savings):
  1. **memory_important** — Always-visible workflow guide. Tells the agent to search first, then timeline, then get details.
  2. **memory_search** (Layer 1) — FTS over observations + sessions. Returns a **compact table** (ID, short time, title truncated to 60 chars, type). Params: `query`, `project`, `type`, `limit`, `offset`, `dateStart`, `dateEnd`, `orderBy` (relevance | date_desc | date_asc). ~50–100 tokens/result.
  3. **memory_timeline** (Layer 2) — Chronological context around an observation. Params: `anchor` (observation ID), `depth_before`, `depth_after`; or `query` to find anchor; or fallback `session_id`/`project`/`limit`. Uses `get_observations_around` in observation_store. ~100–200 tokens/entry.
  4. **memory_get** (Layer 3) — Full observation details by ids. Params: `ids`, `orderBy`, `limit`. Content truncated to 2000 chars with “(truncated)”. ~500–1000 tokens/observation.
- Storage: **search.search_observations** supports `date_start`, `date_end`, `order_by`; **observation_store.get_observations_around** returns observations before/anchor/after by `created_at`.

---

## 4. Data & Consistency

- **Sessions**: Cursor’s conversation_id is session id; multiple inits upsert; only on stop is status set to completed and summary written.
- **Observations**: Foreign key to session, ON DELETE CASCADE; FTS kept in sync by triggers.
- **Time**: Stored as UTC strings; display layer uses time_display.utc_to_local.
- **Concurrency**: Single SQLite writer; single Worker process; hooks do short POSTs and do not hold connections.

---

## 5. Security & Privacy

- Data stays local (`~/.cursor-mem` or configured dir); when AI is enabled, only summary-related text is sent to the user-configured API.
- Worker binds to 127.0.0.1 by default (Uvicorn), not exposed to the network.
- No API keys in code or default config; set via `cursor-mem config set` into config.json.

---

## 6. Extension Points

- **Summarization**: Replace or extend `summarizer/` (e.g. more rule strategies, different AI models).
- **Context**: Tune `context_budget`, `max_sessions_in_context`, or section weights in the builder.
- **Storage**: Schema version in meta table for future migrations.
- **MCP**: Add TOOLS and TOOL_HANDLERS in the server to expose new tools.

---

*Document follows the codebase; see the repo for the source of truth.*

**[中文版 (Chinese)](DESIGN_CN.md)**
