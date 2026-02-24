# cursor-mem 三层工作流实现原理

本文档详细介绍 cursor-mem 的**三层渐进式检索工作流**的设计动机、实现原理与代码路径，以及为何能实现约 **10x token 节省**。

---

## 1. 为什么需要三层工作流

### 1.1 问题：一次性拉全量很费 token

若 Agent 需要「回忆」项目历史，最朴素的做法是：**一次性把最近 N 条观察的完整内容**（含 title、content、files、时间等）全部塞进上下文。例如拉 20 条完整记录，每条约 500–1000 tokens，合计 **10,000–20,000 tokens**。但多数场景下，真正有用的往往只有其中 **2–3 条**，其余 token 被浪费，且容易占满上下文窗口。

### 1.2 思路：渐进式披露（Progressive Disclosure）

改为**分步披露**：

1. **先看索引**：只返回「ID + 短标题 + 类型 + 时间」的紧凑列表，让 Agent 先「扫一眼」有哪些相关记录。
2. **再要上下文**（可选）：针对感兴趣的某条记录，拉取它**前后几条**的简短时间线，理解前因后果。
3. **最后取详情**：仅对**筛选后的少数 ID** 拉取完整 content、files 等。

这样，大量 token 只消耗在「最终选中的」少数几条上，从而实现 **约 10x 的 token 节省**。

### 1.3 三层与 token 量级

| 层级 | 工具 | 每条/每批 token 量级 | 作用 |
|------|------|----------------------|------|
| 第一层 | memory_search | ~50–100 tokens/条 | 紧凑索引，先筛选 |
| 第二层 | memory_timeline | ~100–200 tokens/条 | 锚点前后上下文 |
| 第三层 | memory_get | ~500–1000 tokens/条 | 仅对选中 ID 取详情 |

另有一个**不占查询 token** 的引导工具 **memory_important**，用于在工具列表中始终展示「先 search → 再 timeline → 再 get」的说明，促使 Agent 按该顺序调用。

---

## 2. 第一层：memory_search（紧凑索引）

### 2.1 设计目标

- 返回**仅够做筛选**的信息：ID、短时间、标题（截断）、类型。
- **不返回** content、files 等大字段，从而把单条结果控制在约 50–100 tokens。

### 2.2 实现路径

**入口**：MCP 工具 `memory_search`，handler 为 `mcp/server.py` 中的 `handle_memory_search`。

1. **参数**：`query`（必填）、`project`、`type`、`limit`、`offset`、`dateStart`、`dateEnd`、`orderBy`。
2. **存储层**：调用 `storage/search.py` 的 `search_observations()`：
   - 使用 SQLite **FTS5** 虚拟表 `observations_fts`，对 `title`、`content`、`tool_name`、`files` 做全文匹配。
   - 支持 `date_start`/`date_end` 做时间范围过滤（`created_at >= ? AND created_at <= ?`）。
   - 支持 `order_by`：`relevance`（按 FTS rank）、`date_desc`、`date_asc`。
   - 返回的每一行仍包含完整列（含 content），但**不会原样交给 Agent**。
3. **输出格式化**（在 MCP handler 内）：
   - 观察结果：只取 `id`、`created_at`、`title`、`type`。
   - 时间转为本地显示后截成短格式（如 `02-24 10:01`）。
   - 标题用 `_truncate(title, 60)` 截断。
   - 拼成 **Markdown 表格**，例如：
     ```text
     ## Observations (5 matches)
     | ID | Time | Title | Type |
     |---|---:|---|---|
     | #123 | 02-24 10:01 | Fix time display bug | file_edit |
     ```
   - 会话结果同理：紧凑表，只含 ID 前 8 位、project、summary 截断 80 字。

这样，Agent 拿到的是一张「目录表」，可以根据 ID 决定下一步是看时间线还是直接取详情。

### 2.3 关键代码位置

- 搜索逻辑：`storage/search.py` 的 `search_observations()`（FTS5 查询、日期、排序、分页）。
- 输出格式：`mcp/server.py` 的 `handle_memory_search()`（表格化、截断、本地时间）。

---

## 3. 第二层：memory_timeline（锚点上下文）

### 3.1 设计目标

- 以**某一条观察**为锚点，看它**之前**和**之后**各 N 条观察，形成一段短时间线。
- 用于理解「这件事发生前后还做了什么」，而不必先拉取每条完整 content。
- 单条仅输出：时间 + 类型 + ID + 标题（截断 80 字），约 100–200 tokens/条。

### 3.2 锚点与深度

- **anchor**：观察的 ID（整数）。时间线以这条为中心。
- **depth_before**：锚点**之前**取几条（默认 3）。
- **depth_after**：锚点**之后**取几条（默认 3）。
- 也可不传 `anchor` 而传 **query**：先用 `search_observations(conn, query, limit=1)` 找到一条作为锚点，再按该 ID 取前后。

若既不传 anchor 也不传 query，则退化为「按 session 或 project 取最近 N 条」的旧逻辑，便于兼容。

### 3.3 实现路径

**存储层**：`storage/observation_store.py` 的 `get_observations_around()`。

1. 根据 `anchor_id` 查出该条观察的 `created_at`（若不存在则返回空列表）。
2. **之前**：`WHERE (created_at < anchor_ts OR (created_at = anchor_ts AND id < anchor_id))`，按时间倒序取 `depth_before` 条。
3. **锚点本身**：再查一次 `id = anchor_id` 的完整行。
4. **之后**：`WHERE (created_at > anchor_ts OR (created_at = anchor_ts AND id > anchor_id))`，按时间正序取 `depth_after` 条。
5. 拼接顺序：`[...before 逆序..., anchor, ...after...]`，保证时间线按**时间升序**输出。
6. 若传入 `project`，则只在该项目的会话内取（通过 `session_id IN (SELECT id FROM sessions WHERE project = ?)` 过滤）。

**MCP 层**：`handle_memory_timeline()`：

- 若无 `anchor` 但有 `query`，先调用 `search_observations(..., limit=1)` 得到 `anchor_id`。
- 调用 `get_observations_around(conn, anchor_id, depth_before, depth_after, project)`。
- 输出格式：每行 `- [短时间] **type** #id: 标题`；锚点行末尾加 `**>>>**` 标记。

### 3.4 关键代码位置

- 锚点前后查询：`storage/observation_store.py` 的 `get_observations_around()`。
- 参数解析与 query→anchor：`mcp/server.py` 的 `handle_memory_timeline()`。

---

## 4. 第三层：memory_get（按需详情）

### 4.1 设计目标

- 仅对**已经通过 search/timeline 筛选出的 ID** 拉取完整内容。
- 单条观察可能包含很长 content，因此做**长度上限**控制，避免单条爆 token。

### 4.2 实现路径

**存储层**：`observation_store.get_observations_by_ids(conn, ids)` — 常规的 `WHERE id IN (...)`，按 `created_at` 排序返回。

**MCP 层**：`handle_memory_get()`：

- 参数：`ids`（必填）、`orderBy`（date_asc / date_desc）、`limit`。
- 取回列表后可按 `orderBy` 反转，再截断到 `limit` 条。
- 对每条观察：
  - 输出：标题、session_id、时间、**content**、files。
  - **content**：若长度超过 2000 字符，则截断为 `content[:2000] + "\n... (truncated)"`，避免单条过长。

这样，Agent 只有在「已经知道要哪几条」的情况下才付出 500–1000 tokens/条的代价，而不是对整库全量付出。

### 4.3 关键代码位置

- 按 ID 批量查：`storage/observation_store.py` 的 `get_observations_by_ids()`。
- 输出与截断：`mcp/server.py` 的 `handle_memory_get()`。

---

## 5. memory_important（工作流引导）

### 5.1 作用

- 不依赖用户/Agent 记忆「先搜再取」的约定，而是在**工具列表里始终有一个工具**，其描述和返回值都是同一段「三层工作流」说明。
- Agent 在选用 memory 相关工具时容易先看到或先调用它，从而被提醒：先 `memory_search` → 再视情况 `memory_timeline` → 最后 `memory_get(ids)`。

### 5.2 memory_important 何时被调用？

**没有自动调用**。cursor-mem 不会在后台或任何钩子里主动调用 `memory_important`。

- **调用时机**：仅当 **Cursor 的 Agent（或用户）在对话中显式选择并执行**「memory_important」这个工具时，MCP server 才会执行其 handler，返回 `_WORKFLOW_TEXT`。
- **工具列表中的曝光**：Cursor 向 MCP 请求 `tools/list` 时，会拿到所有 4 个工具的名称、描述（description）、参数 schema。`memory_important` 的 **description** 里已经写入了完整的三层工作流说明（与返回值一致）。因此，即使用户从未点击「调用」memory_important，Agent 在**选择要使用哪个工具**时，也能在工具描述里看到这段说明，从而被引导按 search → timeline → get 的顺序使用。
- **总结**：调用 = 仅当 Agent/用户显式调用该工具时；但工作流说明还会通过 **tools/list 的 description** 持续暴露给 Agent，起到「始终可见」的提醒作用。

### 5.3 实现

- 工具名：`memory_important`。
- 无参数；handler 直接返回常量 `_WORKFLOW_TEXT`（约 4 行英文说明）。
- 与其它三个工具一起注册在 `TOOLS` 和 `TOOL_HANDLERS` 中，由 MCP 的 `tools/list` 暴露给 Cursor。

---

## 6. 三层中的「筛选」是如何做的？

**筛选不是服务端自动完成的**，而是 **Agent 根据第一层（及可选的第二层）的返回结果，自己决定「要对哪些 ID 取详情」**，再调用 `memory_get(ids=[...])`。

- **第一层之后**：服务端只负责按 query（和 project/type/日期等）做 FTS5 搜索，返回一张**紧凑索引表**（ID、时间、标题、类型）。表中每一行对应一条匹配的观察。**由 Agent 阅读这张表**，在内部决定「我对 #42、#55 感兴趣，要看完整内容」，然后发起 `memory_get(ids=[42, 55])`。也就是说，「选哪些 ID」是 **Agent 的决策**，不是服务端再跑一层算法或规则。
- **第二层（可选）**：若 Agent 先调用了 `memory_timeline(anchor=42, ...)`，会得到以 #42 为中心的一段短时间线。Agent 可以据此再决定「除了 #42，还要 get 哪几条」（例如时间线上出现的 #40、#45），再调用 `memory_get(ids=[40, 42, 45])`。同样，**选哪些 ID 仍由 Agent 根据时间线内容决定**。
- **服务端职责**：只做「按条件返回紧凑结果」和「按 ids 返回详情」，不做「自动筛选」或「自动挑出最相关的 N 条再取详情」。这样设计可以保证 token 只花在 Agent 明确选择的那几条上，从而实现约 10x 的节省。

**总结**：三层披露里的「筛选」= **Agent 根据第一层（及可选的第二层）返回的索引/时间线，自行选择要取详情的 observation ID 列表，再调用第三层 memory_get(ids=[...])**；服务端不替 Agent 做筛选决策。

---

## 7. 数据流与调用顺序

```
Agent 想查历史
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. memory_search(query="...", limit=10)                     │
│    → FTS5 查询 observations_fts + sessions_fts               │
│    → 返回紧凑表：ID、短时间、标题(60字)、类型                  │
│    → 约 500–1000 tokens（10 条）                             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼ Agent 根据表格选出感兴趣 ID（如 #42, #55）
    │
┌─────────────────────────────────────────────────────────────┐
│ 2. memory_timeline(anchor=42, depth_before=3, depth_after=3)  │  （可选）
│    → get_observations_around(42, 3, 3)                       │
│    → 返回 7 条短时间线（时间 + 类型 + #id + 标题 80 字）      │
│    → 约 700–1400 tokens                                      │
└─────────────────────────────────────────────────────────────┘
    │
    ▼ Agent 确认要读 #42、#55 的完整内容
    │
┌─────────────────────────────────────────────────────────────┐
│ 3. memory_get(ids=[42, 55])                                  │
│    → get_observations_by_ids([42, 55])                       │
│    → 返回 2 条完整记录，content 超 2000 字则截断              │
│    → 约 1000–2000 tokens                                     │
└─────────────────────────────────────────────────────────────┘

合计：约 2200–4400 tokens，且全部是「筛选后」的相关内容。
若一次性拉 20 条完整：约 10000–20000 tokens，其中大部分可能无关。
```

---

## 8. Token 节省为何能到「约 10x」

- **传统做法**：一次拉 20 条完整观察 → 20 × (500–1000) ≈ **10,000–20,000 tokens**，其中可能只有 2–3 条真正有用，**有效比例低**。
- **三层做法**：  
  - 第一层：10 条索引 ≈ 500–1000 tokens。  
  - 第二层（可选）：7 条时间线 ≈ 700–1400 tokens。  
  - 第三层：只拉 2–3 条详情 ≈ 1000–3000 tokens。  
  - **合计约 2,200–5,400 tokens**，且**几乎全部是 Agent 主动筛选后的内容**。
- 在「只关心少数几条」的典型场景下，总 token 可降为原来的约 **1/5～1/10**，因此称为「约 10x token 节省」。实际倍数取决于 Agent 的查询习惯和筛选比例。

---

## 9. 与 Worker HTTP API 的对应关系

三层工具在 HTTP 层有对应接口，便于 Web 查看器或其它客户端复用同一逻辑：

| MCP 工具 | HTTP 接口 | 说明 |
|----------|-----------|------|
| memory_search | `GET /api/search/observations?q=...&dateStart=...&orderBy=...` | 同 FTS5 + 日期 + 排序 |
| memory_timeline | `GET /api/timeline?anchor=...&depth_before=...&depth_after=...` | 同 get_observations_around |
| memory_get | `GET /api/observations/batch?ids=...&orderBy=...&limit=...` | 同 get_observations_by_ids |

实现见 `worker/routes.py` 中上述路由；MCP server 直接使用同一套 `storage` 与 `search` 模块，不经过 HTTP，但逻辑一致。

---

## 10. 小结

- **第一层**：FTS5 搜索 + 紧凑表格输出（仅 ID、时间、标题、类型），控制 ~50–100 tokens/条，用于筛选。
- **第二层**：以 anchor 为中心取前后 N 条，存储层用 `get_observations_around` 按时间拼接，输出短时间线并标记锚点，~100–200 tokens/条。
- **第三层**：仅对给定 ids 拉取完整观察，content 做 2000 字截断，~500–1000 tokens/条。
- **memory_important**：固定返回工作流说明，引导 Agent 按「search → timeline → get」顺序调用，从设计上减少「未筛选就拉全量」的 token 浪费。

整体上，通过**渐进式披露**和**按需取详情**，在保证「能回忆历史」的前提下，将 token 消耗压到约原来的 1/5～1/10，即「约 10x token 节省」。

**[English version](THREE_LAYER_WORKFLOW.md)**
