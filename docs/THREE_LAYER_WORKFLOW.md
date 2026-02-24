# cursor-mem Three-Layer Workflow: Implementation Details

This document describes the **three-layer progressive disclosure workflow** in cursor-mem: why it exists, how each layer is implemented, and how it achieves ~**10x token savings**.

---

## 1. Why a Three-Layer Workflow?

### 1.1 The problem: full dumps are token-heavy

If the agent needs to “recall” project history, the naive approach is to **fetch the full content** of the last N observations (title, content, files, timestamps) in one go. For example, 20 full records at 500–1000 tokens each can total **10,000–20,000 tokens**. In practice, only **2–3** of those are usually relevant; the rest waste tokens and can fill the context window.

### 1.2 Idea: progressive disclosure

Instead, we **disclose in steps**:

1. **Index first**: Return only a compact list of “ID + short title + type + time” so the agent can scan what’s available.
2. **Context next** (optional): For an interesting record, fetch a short **timeline** of observations before and after it.
3. **Details last**: Fetch **full content** only for the **few IDs** the agent chose.

Most tokens are then spent only on the selected items, giving roughly **10x token savings**.

### 1.3 The three layers and token ranges

| Layer | Tool | Tokens per item/batch | Role |
|-------|------|------------------------|------|
| 1 | memory_search | ~50–100 per row | Compact index for filtering |
| 2 | memory_timeline | ~100–200 per row | Context around an anchor |
| 3 | memory_get | ~500–1000 per observation | Full details for selected IDs only |

A fourth tool, **memory_important**, is a **workflow guide** (no query cost): it is always visible in the tool list and tells the agent to use search → timeline → get in that order.

---

## 2. Layer 1: memory_search (compact index)

### 2.1 Goal

- Return **only what’s needed to choose**: ID, short time, title (truncated), type.
- **Do not** return content, files, etc., so each result stays around 50–100 tokens.

### 2.2 Implementation

**Entry**: MCP tool `memory_search`, handled by `handle_memory_search` in `mcp/server.py`.

1. **Parameters**: `query` (required), `project`, `type`, `limit`, `offset`, `dateStart`, `dateEnd`, `orderBy`.
2. **Storage**: `storage/search.py` → `search_observations()`:
   - Uses SQLite **FTS5** virtual table `observations_fts` over `title`, `content`, `tool_name`, `files`.
   - Optional `date_start` / `date_end` filter on `created_at`.
   - `order_by`: `relevance` (FTS rank), `date_desc`, or `date_asc`.
   - Returns full rows from the DB, but the handler does **not** pass them through as-is.
3. **Output formatting** (in the MCP handler):
   - For observations: keep only `id`, `created_at`, `title`, `type`.
   - Convert time to local and shorten (e.g. `02-24 10:01`).
   - Truncate title with `_truncate(title, 60)`.
   - Emit a **Markdown table**, e.g.:
     ```
     ## Observations (5 matches)
     | ID | Time | Title | Type |
     |---|---:|---|---|
     | #123 | 02-24 10:01 | Fix time display bug | file_edit |
     ```
   - Sessions: similar compact table (short id, project, summary truncated to 80 chars).

The agent thus gets a “table of contents” and can decide which IDs to inspect via timeline or get.

### 2.3 Code locations

- Search: `storage/search.py` → `search_observations()` (FTS5, date range, ordering, pagination).
- Formatting: `mcp/server.py` → `handle_memory_search()` (table, truncation, local time).

---

## 3. Layer 2: memory_timeline (anchor context)

### 3.1 Goal

- Center on **one observation** (anchor) and show **N observations before** and **N after** it.
- Lets the agent see “what happened around this point” without pulling full content for each.
- Each line: time + type + ID + title (truncated 80 chars), ~100–200 tokens per line.

### 3.2 Anchor and depth

- **anchor**: Observation ID (integer). The timeline is centered on this row.
- **depth_before**: How many rows **before** the anchor (default 3).
- **depth_after**: How many rows **after** the anchor (default 3).
- **query** (optional): If `anchor` is not set, run `search_observations(conn, query, limit=1)` and use the first result’s ID as the anchor.

If neither anchor nor query is provided, the handler falls back to “last N observations by session or project” for backward compatibility.

### 3.3 Implementation

**Storage**: `storage/observation_store.py` → `get_observations_around()`.

1. Load the anchor row by `anchor_id` to get `created_at` (return empty if missing).
2. **Before**: `WHERE (created_at < anchor_ts OR (created_at = anchor_ts AND id < anchor_id))`, order by time descending, take `depth_before` rows.
3. **Anchor**: Fetch the full row for `id = anchor_id`.
4. **After**: `WHERE (created_at > anchor_ts OR (created_at = anchor_ts AND id > anchor_id))`, order by time ascending, take `depth_after` rows.
5. Concatenate: `[...before reversed..., anchor, ...after...]` so the final list is in **ascending time**.
6. If `project` is given, restrict to sessions in that project via `session_id IN (SELECT id FROM sessions WHERE project = ?)`.

**MCP**: `handle_memory_timeline()`:

- If no `anchor` but `query` is set, call `search_observations(..., limit=1)` to get `anchor_id`.
- Call `get_observations_around(conn, anchor_id, depth_before, depth_after, project)`.
- Format: each line `- [short_time] **type** #id: title`; the anchor line is suffixed with `**>>>**`.

### 3.4 Code locations

- Anchor ± depth: `storage/observation_store.py` → `get_observations_around()`.
- Params and query→anchor: `mcp/server.py` → `handle_memory_timeline()`.

---

## 4. Layer 3: memory_get (on-demand details)

### 4.1 Goal

- Return full content only for **IDs already chosen** via search or timeline.
- Cap the size of each observation’s content so a single item cannot blow the token budget.

### 4.2 Implementation

**Storage**: `observation_store.get_observations_by_ids(conn, ids)` — standard `WHERE id IN (...)` ordered by `created_at`.

**MCP**: `handle_memory_get()`:

- Parameters: `ids` (required), `orderBy` (date_asc / date_desc), `limit`.
- After loading, optionally reverse by `orderBy` and slice to `limit`.
- For each observation: output title, session_id, time, **content**, files.
- **Content**: if longer than 2000 characters, replace with `content[:2000] + "\n... (truncated)"`.

So the agent pays 500–1000 tokens per observation only for the few it actually selected.

### 4.3 Code locations

- Batch by IDs: `storage/observation_store.py` → `get_observations_by_ids()`.
- Output and truncation: `mcp/server.py` → `handle_memory_get()`.

---

## 5. memory_important (workflow guide)

### 5.1 Role

- Ensures the “search first, then get details” pattern is visible **in the tool list** and in a tool’s return value, so the agent is nudged to call search → timeline → get instead of fetching everything at once.

### 5.2 When is memory_important called?

**There is no automatic invocation.** cursor-mem does not call `memory_important` from the background or from any hook.

- **Invocation**: The MCP server runs `memory_important`'s handler **only when the Cursor agent (or user) explicitly selects and invokes** the "memory_important" tool in the conversation.
- **Exposure in the tool list**: When Cursor requests `tools/list`, it gets all four tools' names, **descriptions**, and parameter schemas. The **description** of `memory_important` already contains the full 3-layer workflow text. So even if the user never calls memory_important, the agent can **see** that text when choosing which tool to use.
- **Summary**: The tool is *called* only when the agent/user explicitly invokes it; the workflow text is also **always visible** via the tool's description in `tools/list`.

### 5.3 Implementation

- Tool name: `memory_important`.
- No parameters; handler returns the constant `_WORKFLOW_TEXT` (a short 3-layer workflow description).
- Registered in `TOOLS` and `TOOL_HANDLERS` and exposed via MCP `tools/list`.

---

## 6. How is “filtering” done in the three layers?

**Filtering is not done automatically on the server.** The **agent** uses the results from layer 1 (and optionally layer 2) to **decide which observation IDs it wants in full**, then calls `memory_get(ids=[...])`.

- **After layer 1**: The server only runs the FTS5 search (with query, project, type, date, etc.) and returns a **compact index table** (ID, time, title, type). The **agent** reads this table and decides, e.g. “I want full content for #42 and #55,” then calls `memory_get(ids=[42, 55])`. So **which IDs to fetch** is the **agent’s decision**, not an extra server-side algorithm.
- **Layer 2 (optional)**: If the agent first calls `memory_timeline(anchor=42, ...)`, it gets a short timeline around #42. It can then decide “I also want #40 and #45 from that timeline” and call `memory_get(ids=[40, 42, 45])`. Again, **choice of IDs is made by the agent** from the timeline.
- **Server’s role**: Only “return compact results for the query” and “return full details for the given ids”; no “auto-filter” or “auto-pick top-N and then fetch details.” That way, tokens are spent only on the observations the agent explicitly selects, giving ~10x savings.

**Summary**: “Filtering” in the three-layer flow = **the agent chooses which observation IDs to pass to `memory_get(ids=[...])` based on the index (and optionally timeline) from layers 1 and 2**; the server does not perform that selection.

---

## 7. Data flow and call order

```
Agent wants to recall history
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. memory_search(query="...", limit=10)                      │
│    → FTS5 on observations_fts + sessions_fts                 │
│    → Compact table: ID, short time, title(60), type          │
│    → ~500–1000 tokens (10 rows)                             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼ Agent picks IDs of interest (e.g. #42, #55)
    │
┌─────────────────────────────────────────────────────────────┐
│ 2. memory_timeline(anchor=42, depth_before=3, depth_after=3)│  (optional)
│    → get_observations_around(42, 3, 3)                      │
│    → 7 short timeline lines (time + type + #id + title 80)  │
│    → ~700–1400 tokens                                       │
└─────────────────────────────────────────────────────────────┘
    │
    ▼ Agent decides to read full content of #42, #55
    │
┌─────────────────────────────────────────────────────────────┐
│ 3. memory_get(ids=[42, 55])                                  │
│    → get_observations_by_ids([42, 55])                      │
│    → 2 full rows, content truncated at 2000 chars            │
│    → ~1000–2000 tokens                                      │
└─────────────────────────────────────────────────────────────┘

Total: ~2200–4400 tokens, all for selected items.
One-shot full fetch of 20 observations: ~10000–20000 tokens, much of it irrelevant.
```

---

## 8. Why “~10x” token savings?

- **Traditional**: Fetch 20 full observations → 20 × (500–1000) ≈ **10,000–20,000 tokens**, with only 2–3 typically relevant → **low relevance ratio**.
- **Three-layer**:
  - Layer 1: 10 index rows ≈ 500–1000 tokens.
  - Layer 2 (optional): 7 timeline rows ≈ 700–1400 tokens.
  - Layer 3: 2–3 full details ≈ 1000–3000 tokens.
  - **Total ≈ 2,200–5,400 tokens**, almost all **actively chosen** by the agent.
- So in the common case “only a few matter,” total tokens can drop to about **1/5–1/10** of the naive approach — hence “~10x token savings.” The exact factor depends on how the agent uses search and how many IDs it finally fetches.

---

## 9. Mapping to Worker HTTP API

The same logic is exposed over HTTP for the web viewer or other clients:

| MCP tool | HTTP endpoint | Notes |
|----------|----------------|--------|
| memory_search | `GET /api/search/observations?q=...&dateStart=...&orderBy=...` | Same FTS5 + date + order |
| memory_timeline | `GET /api/timeline?anchor=...&depth_before=...&depth_after=...` | Same get_observations_around |
| memory_get | `GET /api/observations/batch?ids=...&orderBy=...&limit=...` | Same get_observations_by_ids |

See `worker/routes.py`. The MCP server uses the same `storage` and `search` modules directly (no HTTP in between), but behavior is aligned.

---

## 10. Summary

- **Layer 1**: FTS5 search + compact table (ID, time, title, type only), ~50–100 tokens/row, for filtering.
- **Layer 2**: Timeline around an anchor via `get_observations_around`; short lines with anchor marked; ~100–200 tokens/row.
- **Layer 3**: Full observations for given ids only; content truncated at 2000 chars; ~500–1000 tokens/row.
- **memory_important**: Fixed workflow text so the agent is guided to use search → timeline → get and avoid unbounded full fetches.

By **progressive disclosure** and **on-demand details**, cursor-mem keeps “memory” useful while cutting token use to roughly **1/5–1/10** in typical usage — i.e. ~10x token savings.

**[中文版 (Chinese)](THREE_LAYER_WORKFLOW_CN.md)**
