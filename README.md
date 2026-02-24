# cursor-mem

**Persistent memory for Cursor IDE** — automatically records session context and keeps memory across sessions.

**[中文说明 (README_CN.md)](README_CN.md)**

Tired of re-explaining "where we left off" in every new chat? cursor-mem gives Cursor **persistent memory**: it automatically records your edits, shell commands, and MCP calls, then injects recent session summaries and key context into Cursor Rules so the next conversation picks up right away. **No API key required** — just `pip install cursor-mem` and `cursor-mem install --global`. When the agent needs details, it queries history on demand via MCP, so you say less and use fewer tokens. Like claude-mem, but built for Cursor and lighter.

---

## Features

- **Cross-session memory**: Remembers last session’s actions, edited files, and shell commands
- **Zero-config**: Works out of the box with rule-based compression; no API key required
- **Optional AI summarization**: Use any OpenAI-compatible API (e.g. free Gemini) for smarter summaries
- **Full-text search**: FTS5 search over observations and sessions
- **MCP tools**: 3-layer search workflow (~10x token savings) — `memory_search` (compact index), `memory_timeline` (anchor context), `memory_get` (full details), plus `memory_important` (workflow guide)
- **Web viewer**: Browse memory stream in the browser with live updates
- **Multi-project isolation**: Separate memory per project

---

## Comparison with claude-mem

|criterion | **cursor-mem** | claude-mem |
|----------|----------------|------------|
| **Target** | Cursor IDE only, native hooks | Claude Code first, Cursor via adapter |
| **Stack** | Python 3.10+, FastAPI, SQLite | TypeScript/Bun, Express, SQLite + ChromaDB |
| **Setup** | `pip install cursor-mem` → `cursor-mem install` | Clone, build, plugin/marketplace or Cursor standalone setup |
| **Out-of-the-box** | Works immediately with no API key (rule-based compression) | AI processing is central; free tier needs Gemini/OpenRouter config |
| **Codebase size** | ~20 core modules, single package | 600+ files, plugin + worker + skills |
| **Context injection** | `.cursor/rules/cursor-mem.mdc` (Cursor Rules) | Same for Cursor; Claude Code uses `additionalContext` |
| **Search** | SQLite FTS5 only (simple, no extra deps) | FTS5 + ChromaDB vector search (hybrid) |
| **Dependencies** | Python stdlib + FastAPI/Click/httpx | Node/Bun, Claude Agent SDK, ChromaDB, etc. |

**When to choose cursor-mem:** You use Cursor only, want minimal setup and no required API key, and prefer a small Python codebase. **When to choose claude-mem:** You use Claude Code or want vector/semantic search, token economics, or the full plugin ecosystem.

---

## Quick start

```bash
# Install from PyPI
pip install cursor-mem

# One-shot setup (global; applies to all projects)
cursor-mem install --global

# Restart Cursor
```

From source (development):

```bash
pip install -e .
cursor-mem install --global
```

---

## How it works

```
User submits prompt → beforeSubmitPrompt hook
  → init session + inject history into .cursor/rules/cursor-mem.mdc

Agent runs → afterShellExecution / afterFileEdit / afterMCPExecution hooks
  → capture operations, compress, store in SQLite

Agent stops → stop hook
  → generate session summary + refresh context file for next session
```

---

## Commands

```bash
cursor-mem install [--global]   # Install hooks + start worker
cursor-mem start                # Start worker
cursor-mem stop                 # Stop worker
cursor-mem restart              # Restart worker
cursor-mem status               # Show status

cursor-mem config set <key> <val>   # Set config
cursor-mem config get [key]         # Show config

cursor-mem data stats             # Data stats
cursor-mem data projects          # List projects
cursor-mem data cleanup           # Clean old data
cursor-mem data export [file]     # Export data
```

---

## Optional AI summarization

```bash
# Gemini (free tier)
cursor-mem config set ai.enabled true
cursor-mem config set ai.base_url "https://generativelanguage.googleapis.com/v1beta/openai"
cursor-mem config set ai.api_key "your-gemini-api-key"
cursor-mem config set ai.model "gemini-2.0-flash"

# Or any OpenAI-compatible API
cursor-mem config set ai.base_url "https://api.openai.com/v1"
cursor-mem config set ai.api_key "sk-..."
cursor-mem config set ai.model "gpt-4o-mini"
```

---

## Web viewer

After install, open http://127.0.0.1:37800 for:

- Session list and details
- Observation timeline
- Full-text search
- Live SSE updates

---

## MCP tools (3-layer workflow)

Registered in `~/.cursor/mcp.json` on install. Follow the **3-layer pattern** for ~10x token savings:

1. **memory_important** — Workflow guide (always visible). Read first.
2. **memory_search(query, project?, type?, limit?, offset?, dateStart?, dateEnd?, orderBy?)** — **Step 1**: Compact index (ID, time, title, type). ~50–100 tokens/result.
3. **memory_timeline(anchor?, depth_before?, depth_after?, query?, session_id?, project?, limit?)** — **Step 2**: Context around an observation. Use `anchor` (observation ID) with depths. ~100–200 tokens/entry.
4. **memory_get(ids, orderBy?, limit?)** — **Step 3**: Full details only for filtered IDs. ~500–1000 tokens/observation.

Never fetch full details without filtering via search/timeline first.

---

## Project layout

```
cursor-mem/
├── cli.py           # CLI entry
├── installer.py     # Install logic
├── hook_handler.py  # Unified hook handler
├── config.py        # Config and paths
├── worker/          # FastAPI HTTP service
├── storage/         # SQLite layer
├── context/         # Context build and inject
├── summarizer/      # Rule-based + AI summarizer
├── mcp/             # MCP search tools
├── ui/              # Web viewer
├── pyproject.toml
└── README.md
```

---

## Documentation

| Doc | English | 中文 |
|-----|---------|------|
| **Design** | [DESIGN.md](docs/DESIGN.md) | [DESIGN_CN.md](docs/DESIGN_CN.md) |
| **Roadmap** | [ROADMAP.md](docs/ROADMAP.md) | [ROADMAP_CN.md](docs/ROADMAP_CN.md) |
| **User manual** | [USER_MANUAL.md](docs/USER_MANUAL.md) | [USER_MANUAL_CN.md](docs/USER_MANUAL_CN.md) |

## Testing

- **Automated**: `pip install -e ".[dev]"` then `pytest tests/ -v`
- **In Cursor**: See [TESTING.md](TESTING.md) for manual test cases (hooks, MCP, worker, CLI).

## License

This project is licensed under the **Apache License 2.0**. See [LICENSE](LICENSE) for the full text.

---

## Data locations

- Database: `~/.cursor-mem/cursor-mem.db`
- Config: `~/.cursor-mem/config.json`
- Logs: `~/.cursor-mem/logs/`
- Injected context: `<project>/.cursor/rules/cursor-mem.mdc`
