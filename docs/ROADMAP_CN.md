# cursor-mem 产品路线图

本文档描述 cursor-mem 的版本规划与功能演进，便于用户和贡献者了解方向。

---

## 版本状态说明

- **已完成**：已发布或已合并到主分支
- **进行中**：当前版本正在实现
- **计划中**：后续版本或待定优先级

---

## 已完成

### 核心能力 (v0.1.x)

- **Cursor Hooks 集成**
  - beforeSubmitPrompt：会话初始化与上下文注入
  - afterShellExecution / afterFileEdit / afterMCPExecution：操作记录
  - stop：会话结束摘要与上下文刷新
- **本地存储**
  - SQLite + WAL，sessions / observations 表
  - FTS5 全文索引（observations_fts、sessions_fts）
  - 多项目隔离（按 project 过滤）
- **上下文注入**
  - 近期会话摘要 + 最近操作时间线 + 项目关键文件
  - Token 预算与自适应 budget（新项目更小）
  - 写入 `.cursor/rules/cursor-mem.mdc`，alwaysApply
- **规则压缩与摘要**
  - 无 API 的 shell/file_edit/mcp/prompt 压缩
  - 规则式会话摘要（任务、文件、命令、工具、错误、统计）
- **Worker HTTP 服务**
  - FastAPI，会话与观察的 CRUD、搜索、时间线、统计
  - 上下文构建与注入 API
  - SSE 实时推送（供 Web 查看器使用）
- **CLI**
  - install / uninstall（含 --global）
  - start / stop / restart / status
  - config set / get
  - data stats / projects / cleanup / export
- **MCP 工具**
  - memory_search：全文搜索观察与会话
  - memory_timeline：按会话或项目的时间线
  - memory_get：按 ID 获取观察详情
- **可选 AI 摘要**
  - 支持任意 OpenAI 兼容 API（含 Gemini 等）
  - 失败时回退到规则摘要
- **Web 查看器**
  - 会话列表与详情、观察时间线、全文搜索、SSE 实时更新
- **时间显示**
  - 存储为 UTC，展示为本地时区（time_display 模块）

### 交付与质量

- PyPI 发布（pip install cursor-mem）
- 单包结构，依赖精简（click, fastapi, uvicorn, httpx）
- 测试：pytest，覆盖 config、storage、compressor、hook_handler、worker routes、CLI
- 文档：README、README_CN、TESTING.md

---

## 进行中 / 短期 (v0.2.x 候选)

- **稳定性与体验**
  - 更多边界情况测试（无网络、Worker 未启动、大 payload）
  - 日志与错误信息优化，便于排查
- **配置与可观测性**
  - 可配置 Worker 绑定地址（当前默认 127.0.0.1:37800）
  - status 输出更多统计（如各项目会话数）
- **文档与示例**
  - 设计文档、用户手册、Roadmap（本文档）
  - 可选：示例项目或录屏演示

---

## 计划中（中期）

- **检索增强**
  - 可选向量检索（如本地 embedding + 向量库），与现有 FTS5 并存
  - 更细粒度的搜索过滤（时间范围、文件路径）
- **上下文策略**
  - 可配置「仅摘要 / 摘要+最近操作 / 关键文件权重」等策略
  - 按会话标签或手动标记「重要会话」优先注入
- **数据与隐私**
  - 导出格式增强（如 Markdown、按项目导出）
  - 敏感字段脱敏或排除（如命令参数、文件内容片段）
- **安装与集成**
  - 可选：Cursor 扩展或一键安装脚本
  - 更清晰的升级与迁移说明

---

## 计划中（长期 / 探索）

- **多 IDE 适配**
  - 在架构允许的前提下，探索其他编辑器的 Hook/API 适配
- **协作与同步**
  - 仅作探索：团队共享记忆、只读快照等，需严格考虑隐私与复杂度
- **性能与规模**
  - 大量会话下的索引与查询优化
  - 可选的观察采样或归档策略

---

## 版本号约定

- **主版本**：不兼容的 API 或配置变更
- **次版本**：新功能、兼容的增强
- **修订号**：问题修复、文档与小幅改进

当前主线为 **0.1.x**，进入 0.2 后将按上述短期项推进，中长期项会根据反馈与优先级调整。

---

*最后更新：与当前仓库状态同步。*

**[English version](ROADMAP.md)**
