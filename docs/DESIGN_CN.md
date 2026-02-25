# cursor-mem 设计文档

## 1. 概述

cursor-mem 是面向 **Cursor IDE** 的持久化记忆系统，在无 API Key 的前提下即可工作，通过 Cursor 原生 Hooks 自动记录会话上下文，并在多会话间保持记忆。

### 1.1 设计目标

- **跨会话记忆**：记住最近会话的操作、编辑的文件和执行的命令
- **零配置可用**：开箱即用，基于规则的压缩，无需 API Key
- **可选 AI 摘要**：可接入任意 OpenAI 兼容 API（如免费 Gemini）做更智能的会话摘要
- **全文检索**：基于 SQLite FTS5 对观察与会话做全文搜索
- **Agent 可查询**：MCP 工具采用**三层渐进式检索工作流**（约 10x token 节省）：紧凑索引 → 锚点上下文 → 完整详情
- **多项目隔离**：按项目分别存储与注入上下文

### 1.2 技术栈

| 层级     | 技术选型                    |
|----------|-----------------------------|
| 语言     | Python 3.10+                |
| CLI      | Click                      |
| HTTP 服务 | FastAPI + Uvicorn          |
| 存储     | SQLite（WAL + FTS5）       |
| 协议     | Cursor Hooks JSON、MCP stdio、SSE |

---

## 2. 系统架构

### 2.1 整体数据流

```
用户提交 Prompt
    → beforeSubmitPrompt 钩子
    → Worker: 初始化会话 + 刷新 .cursor/rules/cursor-mem.mdc（注入历史）

Agent 运行中
    → afterShellExecution / afterFileEdit / afterMCPExecution 钩子
    → Hook 脚本压缩 payload → POST 到 Worker
    → Worker 写入 SQLite

Agent 停止
    → stop 钩子
    → Worker: 生成会话摘要（规则 / AI）→ 完成会话 → 再次刷新上下文文件
```

### 2.2 组件关系图

```
                    ┌─────────────────┐
                    │   Cursor IDE     │
                    │  (hooks 触发)    │
                    └────────┬────────┘
                             │ JSON stdin/stdout
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  cursor_mem.hook_handler                                          │
│  - 解析 --event，读 stdin JSON                                     │
│  - 调用 compressor 压缩                                            │
│  - POST 到 Worker (fire-and-forget, 3s timeout)                   │
└────────┬─────────────────────────────────────────────────────────┘
         │ HTTP POST
         ▼
┌──────────────────────────────────────────────────────────────────┐
│  Worker (FastAPI, 默认 37800)                                      │
│  - SessionManager: 会话生命周期、摘要、上下文刷新                    │
│  - routes: /api/session/*, /api/observations, /api/context/*,     │
│            /api/search/*, /api/timeline, /api/events (SSE)         │
└────────┬─────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────┐
│  Storage (SQLite)                                                  │
│  - sessions / observations + FTS5 (observations_fts, sessions_fts)│
│  - session_store, observation_store, search                       │
└──────────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────┐
│  Context 注入                                                       │
│  - context/builder: 按 token 预算组装近期会话摘要 + 最近操作 + 关键文件 │
│  - context/injector: 写入 <project>/.cursor/rules/cursor-mem.mdc   │
└──────────────────────────────────────────────────────────────────┘
```

同时：

- **MCP Server**（`cursor_mem.mcp.server`）通过 stdio 与 Cursor 通信，内部使用同一 SQLite 与 search/observation_store/session_store，实现 4 个工具：memory_important、memory_search、memory_timeline、memory_get（三层工作流）。
- **Web Viewer** 通过 HTTP 访问 Worker 的 /api/* 与 /api/events（SSE）查看会话与时间线并实时更新。

---

## 3. 核心模块

### 3.1 配置 (config.py)

- **路径**：数据目录 `CURSOR_MEM_DATA_DIR` 或 `~/.cursor-mem`，其下 `config.json`、`cursor-mem.db`、`logs/`、`worker.pid`。
- **配置项**：
  - `port`：Worker 端口，默认 37800
  - `context_budget`：注入上下文的 token 预算（默认 3000，配合三层 MCP 按需查询）
  - `max_sessions_in_context`：注入的最近完成会话数量
  - `log_level`：日志级别
  - `ai.*`：可选 AI 摘要（enabled, base_url, api_key, model）

支持 `config set/get` 的 dotted key（如 `ai.enabled`）。

### 3.2 安装与进程 (installer.py)

- **Hooks**：向 `~/.cursor/hooks.json`（全局）或 `<project>/.cursor/hooks.json` 合并写入各事件的 command（`python -m cursor_mem.hook_handler --event <event>`）。
- **MCP**：在 `~/.cursor/mcp.json` 的 `mcpServers` 中注册 `cursor-mem`，command 为 `python -m cursor_mem.mcp.server`。
- **Worker**：后台启动 `python -m cursor_mem.worker.server`，PID 写入 `worker.pid`，SIGTERM 停止。

### 3.3 钩子处理 (hook_handler.py)

- 入口：`python -m cursor_mem.hook_handler --event <event>`，从 stdin 读 JSON。
- 事件与处理：
  - **beforeSubmitPrompt**：提取 conversation_id、workspace_roots、prompt；POST `/api/session/init`；若有 prompt 则压缩后 POST `/api/observations`（type=prompt）；返回 `{ "continue": true }`。
  - **afterShellExecution**：压缩 shell → POST `/api/observations`。
  - **afterFileEdit**：压缩 file_edit → POST `/api/observations`。
  - **afterMCPExecution**：压缩 mcp → POST `/api/observations`。
  - **stop**：POST `/api/session/summarize`，触发摘要与上下文刷新。
- 所有 POST 为 fire-and-forget，超时 3 秒，失败不阻塞 IDE。

### 3.4 压缩 (context/compressor.py)

将原始 hook payload 压成统一结构，便于存储与上下文展示：

- **compress_shell**：command + 输出前 5 行 + duration，title 截断 120 字符，并尝试从命令中提取文件路径。
- **compress_file_edit**：file_path + 前 5 个 edit 的 ±lines 摘要，path 缩短为最后 3 段。
- **compress_mcp**：tool_name + tool_input/result_json 的简短摘要 + duration。
- **compress_prompt**：prompt 截断为 title(120) 与 content(500)。

另提供 **deduplicate_observations**（合并同文件连续 file_edit）和 **estimate_tokens**（按字符数/4 粗算 token）。

### 3.5 存储 (storage/)

- **database.py**：SQLite 连接（WAL、foreign_keys、busy_timeout）、建表与 schema 版本（meta 表）。
- **表结构**：
  - **sessions**：id, project, status, created_at, updated_at, summary, user_prompt
  - **observations**：id, session_id, type, tool_name, title, content, files, created_at
  - **observations_fts / sessions_fts**：FTS5 虚拟表 + 触发器同步
  - **meta**：schema_version 等
- **session_store**：会话 CRUD、按项目/状态取最近会话、完成会话（写 summary）、统计、按时间清理。
- **observation_store**：按 session 或按项目取观察、按 id 批量取、插入观察。
- **search**：FTS5 搜索 observations/sessions，支持 project、obs_type、limit/offset。
- **time_display**：UTC 存、本地时区显示（DISPLAY_FMT），供 builder 与 MCP 输出使用。

### 3.6 上下文构建与注入 (context/)

- **builder.build_context(conn, project, config)**：
  - 根据项目会话数量做**自适应 budget**（新项目更小，成熟项目用满 context_budget）。
  - 组装：标题 + 近期完成会话摘要（_build_summaries_section）+ 最近一场会话的观察列表（_build_observations_section，含去重）+ 项目关键文件列表（_build_files_section，按出现次数排序前 15）+ **MCP 使用提示**（三层工作流）+ 页脚（含本地时间）。
  - 各段在 budget 内截断，时间统一用 time_display.utc_to_local。
- **injector.inject_context(project_root, context_markdown)**：写入 `.cursor/rules/cursor-mem.mdc`，带 MDC 头（alwaysApply、description）。

### 3.7 会话与摘要 (worker/session_manager.py, summarizer/)

- **SessionManager**：
  - `init_session`：upsert session，记录 user_prompt
  - `add_observation`：确保 session 存在并写入 observation
  - `complete_session`：拉取观察列表，若启用 AI 则调用 AI 摘要，否则规则摘要；写回 session summary、status=completed；若有 project_root 则 refresh_context
  - `refresh_context`：build_context + inject_context
- **rule_based.summarize_session**：从观察中提取任务描述、修改文件、执行命令、MCP 工具、错误信息、简单统计，拼接成一段摘要。
- **ai_powered**（可选）：调用配置的 OpenAI 兼容 API 生成会话摘要；失败时回退到规则摘要。

### 3.8 Worker API (worker/routes.py)

- 健康：`GET /api/health`, `GET /api/readiness`
- 会话：`POST /api/session/init`, `POST /api/session/summarize`, `GET /api/sessions`, `GET /api/sessions/{id}`
- 观察：`POST /api/observations`, `GET /api/observations`, `GET /api/observations/batch?ids=`
- 上下文：`GET /api/context/build?project=`, `POST /api/context/inject`
- 搜索：`GET /api/search/observations`, `GET /api/search/sessions`
- 时间线：`GET /api/timeline`
- 统计：`GET /api/stats`
- SSE：`GET /api/events`（新观察/会话完成时广播）
- 清理：`DELETE /api/sessions/cleanup`

### 3.9 MCP (mcp/server.py)

- 通过 stdio 实现 JSON-RPC 2.0，处理 `initialize`、`tools/list`、`tools/call`。
- **三层工作流**（渐进式披露，约 10x token 节省）：
  1. **memory_important** — 始终可见的工作流指引，提醒 Agent 先 search、再 timeline、最后 get 详情。
  2. **memory_search**（第一层）— 对 observations + sessions 做 FTS。返回**紧凑表格**（ID、短时间、标题截断 60 字、类型）。参数：`query`、`project`、`type`、`limit`、`offset`、`dateStart`、`dateEnd`、`orderBy`（relevance | date_desc | date_asc）。约 50–100 tokens/条。
  3. **memory_timeline**（第二层）— 围绕某条观察的时间线上下文。参数：`anchor`（观察 ID）、`depth_before`、`depth_after`；或 `query` 自动找锚点；或回退 `session_id`/`project`/`limit`。使用 observation_store 的 `get_observations_around`。约 100–200 tokens/条。
  4. **memory_get**（第三层）— 按 ids 取完整观察详情。参数：`ids`、`orderBy`、`limit`。content 超过 2000 字符会截断并标 “(truncated)”。约 500–1000 tokens/条。
- 存储层：**search.search_observations** 支持 `date_start`、`date_end`、`order_by`；**observation_store.get_observations_around** 按 `created_at` 返回锚点前/锚点/锚点后的观察。

---

## 4. 数据与一致性

- **会话**：以 Cursor 的 conversation_id 为 session id；同一会话多次 init 会 upsert；仅在 stop 时标记 completed 并写 summary。
- **观察**：与 session 外键关联，ON DELETE CASCADE；FTS 通过触发器与主表同步。
- **时间**：库内统一 UTC 字符串；展示层用 time_display.utc_to_local 转为本地时间。
- **并发**：SQLite 单写；Worker 单进程；Hook 短时 POST，不持有连接。

---

## 5. 安全与隐私

- 数据仅存本地（`~/.cursor-mem` 或指定目录）；可选 AI 时仅将摘要相关文本发送到用户配置的 API。
- Worker 默认绑定 0.0.0.0（Uvicorn），Web 查看器可从局域网访问；将 host 设为 127.0.0.1 可仅限本机。
- 不在代码或默认配置中硬编码 API Key；通过 `cursor-mem config set` 写入 config.json。

---

## 6. 扩展点

- **摘要**：可替换或扩展 `summarizer/`（如更多规则策略、不同 AI 模型）。
- **上下文**：可调整 `context_budget`、`max_sessions_in_context` 或 builder 中各段权重。
- **存储**：schema 版本在 meta 表，便于后续加表或迁移。
- **MCP**：在 server 中增加 TOOLS 与 TOOL_HANDLERS 即可暴露新工具。

---

*文档版本与代码同步，以仓库为准。*

**[English version](DESIGN.md)**
