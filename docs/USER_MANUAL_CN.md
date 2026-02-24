# cursor-mem 用户手册

本手册介绍如何安装、配置和使用 cursor-mem，以及常见问题排查。

---

## 1. 简介

cursor-mem 为 Cursor IDE 提供**跨会话持久记忆**：自动记录你在对话中的操作（编辑、命令、MCP 调用等），并在下次对话时通过 Cursor Rules 将近期摘要注入上下文，同时提供 MCP 工具供 Agent 主动查询历史。

- **零配置即可用**：不配置 API Key 时，使用规则压缩与规则摘要，开箱即用。
- **可选 AI 摘要**：配置 OpenAI 兼容 API（如 Gemini）后可生成更智能的会话摘要。

---

## 2. 安装

### 2.1 从 PyPI 安装（推荐）

```bash
pip install cursor-mem
```

### 2.2 从源码安装（开发）

```bash
git clone <repository-url>
cd cursor-mem
pip install -e .
# 可选：安装开发依赖
pip install -e ".[dev]"
```

### 2.3 一键安装到 Cursor

安装完包后，执行**一次**安装命令（将注册 Hooks、MCP 并启动本地 Worker）：

```bash
# 全局安装（对所有项目生效，推荐）
cursor-mem install --global

# 仅当前项目
cursor-mem install
```

安装完成后**重启 Cursor**，钩子与 MCP 才会生效。

---

## 3. 安装后发生了什么

- **Hooks**：在 `~/.cursor/hooks.json`（全局）或项目 `.cursor/hooks.json` 中注册了以下事件的命令：
  - `beforeSubmitPrompt`：提交对话前初始化会话并刷新上下文
  - `afterShellExecution` / `afterFileEdit` / `afterMCPExecution`：记录每次操作
  - `stop`：对话结束时生成摘要并再次刷新上下文
- **MCP**：在 `~/.cursor/mcp.json` 中注册了 `cursor-mem` 服务器，Agent 可调用：
  - `memory_search`、`memory_timeline`、`memory_get`
- **Worker**：在后台启动了一个 HTTP 服务（默认 `http://127.0.0.1:37800`），用于接收 Hook 上报的数据、写库、构建并注入上下文。
- **数据目录**：默认 `~/.cursor-mem/`，内含：
  - `cursor-mem.db`：SQLite 数据库
  - `config.json`：配置
  - `logs/`：日志
  - `worker.pid`：Worker 进程 ID

---

## 4. 常用命令

### 4.1 服务管理

```bash
cursor-mem start      # 启动 Worker
cursor-mem stop       # 停止 Worker
cursor-mem restart    # 重启 Worker
cursor-mem status     # 查看状态（是否运行、端口、会话/观察数量等）
```

### 4.2 配置

```bash
# 查看当前配置
cursor-mem config get

# 查看某一项
cursor-mem config get port
cursor-mem config get ai.enabled

# 修改配置
cursor-mem config set port 37800
cursor-mem config set context_budget 3000
cursor-mem config set max_sessions_in_context 3
cursor-mem config set log_level INFO
```

**常用配置项**：

| 键 | 说明 | 默认 |
|----|------|------|
| port | Worker 端口 | 37800 |
| context_budget | 注入上下文的 token 预算（约 4 字符/token） | 3000 |
| max_sessions_in_context | 注入的最近完成会话数 | 3 |
| log_level | 日志级别 | INFO |
| ai.enabled | 是否启用 AI 摘要 | false |
| ai.base_url | AI API 基础 URL | "" |
| ai.api_key | API Key | "" |
| ai.model | 模型名 | "" |

### 4.3 可选：启用 AI 摘要

使用 **Gemini 免费 tier** 示例：

```bash
cursor-mem config set ai.enabled true
cursor-mem config set ai.base_url "https://generativelanguage.googleapis.com/v1beta/openai"
cursor-mem config set ai.api_key "你的-Gemini-API-Key"
cursor-mem config set ai.model "gemini-2.0-flash"
```

使用 **OpenAI 兼容 API**（如 OpenAI、OpenRouter）：

```bash
cursor-mem config set ai.enabled true
cursor-mem config set ai.base_url "https://api.openai.com/v1"
cursor-mem config set ai.api_key "sk-..."
cursor-mem config set ai.model "gpt-4o-mini"
```

修改后无需重启 Worker，下次会话结束摘要时会生效；失败时会自动回退到规则摘要。

### 4.4 数据管理

```bash
cursor-mem data stats              # 会话与观察数量、项目列表
cursor-mem data projects           # 各项目及会话数
cursor-mem data cleanup            # 按保留天数清理旧会话（会确认）
cursor-mem data export [文件路径]  # 导出为 JSON（默认 cursor-mem-export.json）
```

清理示例：

```bash
cursor-mem data cleanup --keep-days 30           # 删除 30 天前的已完成会话
cursor-mem data cleanup --keep-days 7 --project 某项目  # 仅某项目
```

---

## 5. Web 查看器

Worker 启动后，在浏览器打开：

**http://127.0.0.1:37800**

（若修改了 `port`，请使用对应端口。）

可进行：

- 查看会话列表与详情
- 查看观察时间线
- 全文搜索
- 通过 SSE 实时看到新操作与会话完成

---

## 6. MCP 工具（三层工作流）

cursor-mem 提供 **4 个 MCP 工具**，采用**三层渐进式披露**，约 10x token 节省。Agent 应先 **search 索引 → timeline 取上下文 → 仅对筛选出的 ID 再 get 详情**。

1. **memory_important**（工作流指引）
   - 无参数。返回三层工作流说明。始终出现在工具列表中，请先阅读。

2. **memory_search** — 步骤 1：紧凑索引（约 50–100 tokens/条）
   - **query**（必填）、**project**、**type**（shell | file_edit | mcp | prompt）、**limit**、**offset**
   - **dateStart**、**dateEnd**（YYYY-MM-DD）、**orderBy**（relevance | date_desc | date_asc）
   - 返回表格：ID、短时间、标题（截断）、类型。用于筛选出感兴趣的观察 ID。

3. **memory_timeline** — 步骤 2：围绕某条观察的上下文（约 100–200 tokens/条）
   - **anchor**（观察 ID）+ **depth_before**、**depth_after**（默认 3）— 以该 ID 为中心的时间线
   - **query** — 可选；未提供 anchor 时用搜索自动确定锚点
   - **session_id**、**project**、**limit** — 不使用 anchor 时的回退参数
   - 返回简短时间线；锚点行会标 `>>>`。

4. **memory_get** — 步骤 3：完整详情（约 500–1000 tokens/条）
   - **ids**（必填）、**orderBy**（date_asc | date_desc）、**limit**
   - 返回完整 content、files；content 超过 2000 字符会截断并标「(truncated)」。
   - **仅在对 search/timeline 筛选后再调用**，避免浪费 token。

这些工具使用与 Worker 相同的 SQLite 数据库；安装并重启 Cursor 后，Agent 即可高效「回忆」历史。

---

## 7. 上下文文件说明

cursor-mem 会把「近期会话摘要 + 最近操作 + 项目关键文件」写入当前项目的：

**`<项目根>/.cursor/rules/cursor-mem.mdc`**

该文件带有 `alwaysApply: true`，Cursor 会在每次对话中自动加载。文末还包含** MCP 使用提示**（三层工作流），提醒 Agent 在需要更多细节时按 `memory_search` → `memory_timeline` → `memory_get` 查询历史。

---

## 8. 数据与隐私

- 所有数据默认仅存于本机目录（`~/.cursor-mem` 或通过环境变量 `CURSOR_MEM_DATA_DIR` 指定）。
- 仅当开启 AI 摘要并配置了 API 时，会话摘要相关文本会被发送到你配置的 API 服务；规则摘要不会外发。
- 导出与清理命令仅操作本地数据，不会上传到任何第三方。

---

## 9. 卸载

```bash
cursor-mem uninstall --global   # 全局安装时
# 或
cursor-mem uninstall            # 仅当前项目

# 然后重启 Cursor
```

会执行：移除 Hooks 中的 cursor-mem 条目、从 mcp.json 中移除 cursor-mem、停止 Worker。数据目录与数据库不会被自动删除，如需彻底清除可手动删除 `~/.cursor-mem`（或你设置的 DATA_DIR）。

---

## 10. 常见问题

### Worker 未启动或 status 显示 stopped

- 执行 `cursor-mem start`，若很快退出可查看 `~/.cursor-mem/logs/` 或 `~/.cursor-mem/worker-stderr.log`。
- 确认端口未被占用：`cursor-mem config get port`，必要时改端口或关闭占用该端口的程序。

### 上下文没有更新 / 规则里看不到新摘要

- 确认 Hooks 已安装：检查 `~/.cursor/hooks.json` 或项目 `.cursor/hooks.json` 是否包含 `cursor_mem.hook_handler`。
- 确认在「对话结束」时触发了 stop（例如正常结束对话）；stop 才会写摘要并刷新 `.cursor/rules/cursor-mem.mdc`。
- 用 `cursor-mem status` 确认 Worker 在运行，并可用浏览器打开 Web 查看器看是否有新会话与观察。

### MCP 工具无响应或报错

- 确认 `~/.cursor/mcp.json` 中存在 `cursor-mem` 的 `mcpServers` 配置。
- 确认使用与安装 cursor-mem 相同的 Python（即 `which python` / `sys.executable` 与 mcp 中 command 一致）。
- 查看 Cursor 的 MCP 或扩展日志，是否有连接或 stdio 错误。

### 时间显示不对

- 当前版本已统一：库内存 UTC，展示用本地时区。若仍异常，请确认系统时区正确，并查看 `storage/time_display.py` 的 `utc_to_local` 行为。

### 想改数据目录

在启动 Worker 或运行 CLI 前设置环境变量：

```bash
export CURSOR_MEM_DATA_DIR=/你的路径
cursor-mem start
```

---

## 11. 更多资源

- **设计文档**：[DESIGN_CN.md](DESIGN_CN.md)（中文） / [DESIGN.md](DESIGN.md)（English）
- **路线图**：[ROADMAP_CN.md](ROADMAP_CN.md)（中文） / [ROADMAP.md](ROADMAP.md)（English）
- **测试说明**：[TESTING.md](../TESTING.md)
- **README**：仓库根目录 [README.md](../README.md) / [README_CN.md](../README_CN.md)

---

*手册与当前版本功能保持一致，如有差异以实际代码与 README 为准。*

**[English version](USER_MANUAL.md)**
