# cursor-mem User Manual

This manual covers installing, configuring, and using cursor-mem, plus troubleshooting.

---

## 1. Introduction

cursor-mem gives **Cursor IDE** persistent memory across sessions: it records your actions in a conversation (edits, commands, MCP calls, etc.) and injects recent summaries into the next conversation via Cursor Rules, while exposing MCP tools so the agent can query history.

- **Works without config**: With no API key, it uses rule-based compression and summarization out of the box.
- **Optional AI summaries**: Configure an OpenAI-compatible API (e.g. Gemini) for smarter session summaries.

---

## 2. Installation

### 2.1 From PyPI (recommended)

```bash
pip install cursor-mem
```

### 2.2 From source (development)

```bash
git clone <repository-url>
cd cursor-mem
pip install -e .
# Optional: dev dependencies
pip install -e ".[dev]"
```

### 2.3 One-time Cursor setup

After installing the package, run the install command once (registers Hooks, MCP, and starts the local Worker):

```bash
# Global (all projects; recommended)
cursor-mem install --global

# Current project only
cursor-mem install
```

**Restart Cursor** after install so hooks and MCP take effect.

---

## 3. What the install does

- **Hooks**: Registers commands in `~/.cursor/hooks.json` (global) or the project’s `.cursor/hooks.json`:
  - `beforeSubmitPrompt`: init session and refresh context before sending
  - `afterShellExecution` / `afterFileEdit` / `afterMCPExecution`: record each action
  - `stop`: generate summary and refresh context when the conversation ends
- **MCP**: Registers the `cursor-mem` server in `~/.cursor/mcp.json`; the agent can call `memory_search`, `memory_timeline`, `memory_get`.
- **Worker**: Starts an HTTP service in the background (default `http://127.0.0.1:37800`) to receive hook data, write to the DB, and build/inject context.
- **Data directory**: Default `~/.cursor-mem/` with `cursor-mem.db`, `config.json`, `logs/`, `worker.pid`.

---

## 4. Commands

### 4.1 Service

```bash
cursor-mem start      # Start Worker
cursor-mem stop       # Stop Worker
cursor-mem restart    # Restart Worker
cursor-mem status     # Status (running, port, session/observation counts)
```

### 4.2 Config

```bash
cursor-mem config get                    # Show all config
cursor-mem config get port                # One key
cursor-mem config get ai.enabled

cursor-mem config set port 37800
cursor-mem config set context_budget 3000
cursor-mem config set max_sessions_in_context 3
cursor-mem config set log_level INFO
```

**Common options**:

| Key | Description | Default |
|-----|-------------|---------|
| port | Worker port | 37800 |
| context_budget | Token budget for injected context (~4 chars/token) | 3000 |
| max_sessions_in_context | Number of recent completed sessions to inject | 3 |
| log_level | Log level | INFO |
| ai.enabled | Enable AI summarization | false |
| ai.base_url | AI API base URL | "" |
| ai.api_key | API key | "" |
| ai.model | Model name | "" |

### 4.3 Optional: enable AI summarization

Example with **Gemini (free tier)**:

```bash
cursor-mem config set ai.enabled true
cursor-mem config set ai.base_url "https://generativelanguage.googleapis.com/v1beta/openai"
cursor-mem config set ai.api_key "YOUR_GEMINI_API_KEY"
cursor-mem config set ai.model "gemini-2.0-flash"
```

Example with **OpenAI-compatible API** (OpenAI, OpenRouter, etc.):

```bash
cursor-mem config set ai.enabled true
cursor-mem config set ai.base_url "https://api.openai.com/v1"
cursor-mem config set ai.api_key "sk-..."
cursor-mem config set ai.model "gpt-4o-mini"
```

No Worker restart needed; the next session completion will use AI summary, with fallback to rule-based on failure.

### 4.4 Data

```bash
cursor-mem data stats              # Session/observation counts, projects
cursor-mem data projects           # Projects and session counts
cursor-mem data cleanup            # Remove old sessions (with confirmation)
cursor-mem data export [path]      # Export to JSON (default: cursor-mem-export.json)
```

Cleanup examples:

```bash
cursor-mem data cleanup --keep-days 30
cursor-mem data cleanup --keep-days 7 --project my-project
```

---

## 5. Web viewer

With the Worker running, open in a browser:

**http://127.0.0.1:37800**

(Use your configured `port` if different.)

You can:

- View session list and details
- View observation timeline
- Full-text search
- See new operations and session completion in real time via SSE

---

## 6. MCP tools (3-layer workflow)

cursor-mem exposes **4 MCP tools** following a **3-layer progressive disclosure** pattern for ~10x token savings. The agent should **search first → timeline for context → get details only for filtered IDs**.

1. **memory_important** (workflow guide)
   - No parameters. Returns the 3-layer workflow reminder. Always visible in the tool list; read this first.

2. **memory_search** — Step 1: compact index (~50–100 tokens/result)
   - **query** (required), **project**, **type** (shell | file_edit | mcp | prompt), **limit**, **offset**
   - **dateStart**, **dateEnd** (YYYY-MM-DD), **orderBy** (relevance | date_desc | date_asc)
   - Returns a table: ID, short time, title (truncated), type. Use this to find relevant observation IDs.

3. **memory_timeline** — Step 2: context around an observation (~100–200 tokens/entry)
   - **anchor** (observation ID) + **depth_before**, **depth_after** (default 3) — timeline centered on that ID
   - **query** — optional; if no anchor, search is used to find an anchor automatically
   - **session_id**, **project**, **limit** — fallback when not using anchor
   - Returns a short timeline; the anchor line is marked with `>>>`.

4. **memory_get** — Step 3: full details (~500–1000 tokens/observation)
   - **ids** (required), **orderBy** (date_asc | date_desc), **limit**
   - Full content and files; content is truncated at 2000 characters with “(truncated)”.
   - **Only call after filtering** with search or timeline to avoid token waste.

These use the same SQLite DB as the Worker; after install and Cursor restart, the agent can recall past work efficiently.

---

## 7. Context file

cursor-mem writes “recent session summaries + latest operations + project key files” to:

**`<project-root>/.cursor/rules/cursor-mem.mdc`**

This file has `alwaysApply: true`, so Cursor loads it every conversation. It also includes a short **MCP usage hint** (3-layer workflow) so the agent knows to query history via `memory_search` → `memory_timeline` → `memory_get` when more detail is needed.

---

## 8. Data and privacy

- All data stays local by default (`~/.cursor-mem` or `CURSOR_MEM_DATA_DIR`).
- Only when AI summarization is enabled and an API is configured is summary-related text sent to that API; rule-based summarization does not send data out.
- Export and cleanup only touch local data.

---

## 9. Uninstall

```bash
cursor-mem uninstall --global   # If you installed globally
# or
cursor-mem uninstall            # Current project only

# Then restart Cursor
```

This removes cursor-mem from Hooks and mcp.json and stops the Worker. The data directory is not deleted; remove `~/.cursor-mem` (or your DATA_DIR) manually if you want to wipe everything.

---

## 10. Troubleshooting

### Worker not running / status shows stopped

- Run `cursor-mem start`. If it exits quickly, check `~/.cursor-mem/logs/` or `~/.cursor-mem/worker-stderr.log`.
- Ensure the port is free: `cursor-mem config get port`; change it or stop whatever is using it.

### Context not updating / no new summary in rules

- Confirm Hooks are installed: `~/.cursor/hooks.json` or the project’s `.cursor/hooks.json` should contain `cursor_mem.hook_handler`.
- The summary is written when the conversation **stops** (e.g. you end the chat); the stop hook triggers the refresh of `.cursor/rules/cursor-mem.mdc`.
- Use `cursor-mem status` to confirm the Worker is running and open the web viewer to see if new sessions/observations appear.

### MCP tools not responding or erroring

- Check that `~/.cursor/mcp.json` has the `cursor-mem` entry under `mcpServers`.
- Use the same Python that has cursor-mem installed (the `command` in mcp.json should match that interpreter).
- Check Cursor’s MCP or extension logs for connection or stdio errors.

### Wrong time display

- The app stores UTC and displays in local time. If it still looks wrong, verify the system timezone and see `storage/time_display.py` (`utc_to_local`).

### Custom data directory

Set the env var before starting the Worker or running CLI:

```bash
export CURSOR_MEM_DATA_DIR=/your/path
cursor-mem start
```

---

## 11. More

- **Design**: [DESIGN.md](DESIGN.md) (English) / [DESIGN_CN.md](DESIGN_CN.md) (中文)
- **3-layer workflow**: [THREE_LAYER_WORKFLOW.md](THREE_LAYER_WORKFLOW.md) (English) / [THREE_LAYER_WORKFLOW_CN.md](THREE_LAYER_WORKFLOW_CN.md) (中文)
- **Roadmap**: [ROADMAP.md](ROADMAP.md) (English) / [ROADMAP_CN.md](ROADMAP_CN.md) (中文)
- **Testing**: [TESTING.md](../TESTING.md)
- **README**: [README.md](../README.md) / [README_CN.md](../README_CN.md)

---

*Manual is aligned with the current release; see the repo and README for the source of truth.*

**[中文版 (Chinese)](USER_MANUAL_CN.md)**
