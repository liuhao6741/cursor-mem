# cursor-mem

**Persistent memory for Cursor IDE** — automatically records session context and keeps memory across sessions.

**[中文说明 (README_CN.md)](README_CN.md)**

---

## Features

- **Cross-session memory**: Remembers last session’s actions, edited files, and shell commands
- **Zero-config**: Works out of the box with rule-based compression; no API key required
- **Optional AI summarization**: Use any OpenAI-compatible API (e.g. free Gemini) for smarter summaries
- **Full-text search**: FTS5 search over observations and sessions
- **MCP tools**: Agent can query project history (`memory_search`, `memory_timeline`, `memory_get`)
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
# Install
pip install -e .

# One-shot setup (global; applies to all projects)
cursor-mem install --global

# Restart Cursor
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

## MCP tools

Registered in `~/.cursor/mcp.json` on install:

- `memory_search(query)` — search history
- `memory_timeline(session_id?)` — timeline view
- `memory_get(ids)` — fetch observation details

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

## License

This project is licensed under the **Apache License 2.0**. See [LICENSE](LICENSE) for the full text.

---

## Data locations

- Database: `~/.cursor-mem/cursor-mem.db`
- Config: `~/.cursor-mem/config.json`
- Logs: `~/.cursor-mem/logs/`
- Injected context: `<project>/.cursor/rules/cursor-mem.mdc`
