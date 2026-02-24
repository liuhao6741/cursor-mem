# cursor-mem

**Cursor IDE 的持久化记忆系统** — 自动记录会话上下文，跨会话保持记忆。

**[English (README.md)](README.md)**

---

## 功能

- **跨会话记忆**：自动记住上一次会话的操作、修改的文件、执行的命令
- **零配置即用**：安装后无需 API Key，使用规则化压缩自动工作
- **AI 增强可选**：配置 OpenAI 兼容 API（如 Gemini 免费版）获得更智能的摘要
- **全文搜索**：FTS5 搜索历史操作和会话
- **MCP 工具**：Agent 可主动查询项目历史（`memory_search`、`memory_timeline`、`memory_get`）
- **Web 查看器**：浏览器查看记忆流，实时更新
- **多项目隔离**：按项目分别管理记忆

---

## 与 claude-mem 的对比

| 对比项 | **cursor-mem** | claude-mem |
|--------|----------------|------------|
| **目标平台** | 仅 Cursor，原生 Hooks | 以 Claude Code 为主，Cursor 通过适配层 |
| **技术栈** | Python 3.10+、FastAPI、SQLite | TypeScript/Bun、Express、SQLite + ChromaDB |
| **安装方式** | `pip install cursor-mem` → `cursor-mem install` | 克隆构建、插件市场或 Cursor 独立配置 |
| **开箱即用** | 无需 API Key 即可运行（规则化压缩） | 以 AI 处理为核心，免费需配置 Gemini/OpenRouter |
| **代码规模** | 约 20 个核心模块，单包 | 600+ 文件，插件 + Worker + Skills |
| **上下文注入** | `.cursor/rules/cursor-mem.mdc`（Cursor Rules） | Cursor 同理；Claude Code 用 `additionalContext` |
| **搜索能力** | 仅 SQLite FTS5（简单、无额外依赖） | FTS5 + ChromaDB 向量搜索（混合） |
| **依赖** | Python 标准库 + FastAPI/Click/httpx | Node/Bun、Claude Agent SDK、ChromaDB 等 |

**选 cursor-mem 当你**：只用 Cursor、希望安装简单、不想必配 API Key、偏好轻量 Python 项目。**选 claude-mem 当你**：使用 Claude Code，或需要向量/语义搜索、Token 经济学、完整插件生态。

---

## 快速开始

```bash
# 从 PyPI 安装
pip install cursor-mem

# 一键配置（全局，所有项目生效）
cursor-mem install --global

# 重启 Cursor 即可
```

从源码安装（开发用）：

```bash
pip install -e .
cursor-mem install --global
```

---

## 工作原理

```
用户提交 Prompt → beforeSubmitPrompt hook
  → 初始化会话 + 注入历史上下文到 .cursor/rules/cursor-mem.mdc

Agent 工作中 → afterShellExecution / afterFileEdit / afterMCPExecution hooks
  → 捕获操作记录，压缩存入 SQLite

Agent 结束 → stop hook
  → 生成会话摘要 + 更新上下文文件（供下次会话使用）
```

---

## 命令

```bash
cursor-mem install [--global]    # 安装 hooks + 启动 worker
cursor-mem start                 # 启动 worker 服务
cursor-mem stop                  # 停止 worker
cursor-mem restart               # 重启 worker
cursor-mem status                # 查看状态

cursor-mem config set <key> <val>  # 设置配置
cursor-mem config get [key]        # 查看配置

cursor-mem data stats              # 数据统计
cursor-mem data projects           # 列出所有项目
cursor-mem data cleanup            # 清理旧数据
cursor-mem data export [file]      # 导出数据
```

---

## 配置 AI 增强（可选）

```bash
# 使用 Gemini 免费 API
cursor-mem config set ai.enabled true
cursor-mem config set ai.base_url "https://generativelanguage.googleapis.com/v1beta/openai"
cursor-mem config set ai.api_key "your-gemini-api-key"
cursor-mem config set ai.model "gemini-2.0-flash"

# 或使用任何 OpenAI 兼容 API
cursor-mem config set ai.base_url "https://api.openai.com/v1"
cursor-mem config set ai.api_key "sk-..."
cursor-mem config set ai.model "gpt-4o-mini"
```

---

## Web 查看器

安装后访问 http://127.0.0.1:37800 查看：

- 会话列表和详情
- 操作时间线
- 全文搜索
- 实时 SSE 更新

---

## MCP 工具

安装时自动注册到 `~/.cursor/mcp.json`，提供 3 个工具：

- `memory_search(query)` — 搜索历史
- `memory_timeline(session_id?)` — 时间线视图
- `memory_get(ids)` — 获取详情

---

## 项目结构

```
cursor-mem/
├── cli.py              # CLI 入口
├── installer.py         # 安装逻辑
├── hook_handler.py     # Hook 统一处理器
├── config.py           # 配置管理
├── worker/             # FastAPI HTTP 服务
├── storage/            # SQLite 存储层
├── context/            # 上下文构建与注入
├── summarizer/         # 摘要引擎（规则化 + AI）
├── mcp/                # MCP 搜索工具
├── ui/                 # Web 查看器
├── pyproject.toml
└── README.md
```

---

## 文档

| 文档 | English | 中文 |
|------|---------|------|
| **设计文档** | [DESIGN.md](docs/DESIGN.md) | [DESIGN_CN.md](docs/DESIGN_CN.md) |
| **路线图** | [ROADMAP.md](docs/ROADMAP.md) | [ROADMAP_CN.md](docs/ROADMAP_CN.md) |
| **用户手册** | [USER_MANUAL.md](docs/USER_MANUAL.md) | [USER_MANUAL_CN.md](docs/USER_MANUAL_CN.md) |

## 测试

- **自动化**：`pip install -e ".[dev]"` 后执行 `pytest tests/ -v`
- **在 Cursor 中**：手动测试用例（Hooks、MCP、Worker、CLI）见 [TESTING.md](TESTING.md)

## 许可证

本项目采用 **Apache License 2.0**。完整条款见 [LICENSE](LICENSE)。

---

## 数据存储位置

- 数据库：`~/.cursor-mem/cursor-mem.db`
- 配置：`~/.cursor-mem/config.json`
- 日志：`~/.cursor-mem/logs/`
- 上下文注入：`<project>/.cursor/rules/cursor-mem.mdc`
