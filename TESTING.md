# cursor-mem 测试说明

## 一、自动化测试（在终端运行）

在项目根目录 `cursor-mem/` 下执行：

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行全部测试
pytest tests/ -v

# 带覆盖率
pytest tests/ -v --cov=cursor_mem --cov-report=term-missing
```

测试会使用临时目录（`CURSOR_MEM_DATA_DIR`），不会改动你本机的 `~/.cursor-mem` 数据。

---

## 二、在 Cursor 中的功能测试（手动用例）

以下用例在 **Cursor IDE** 中操作，用于验证 Hooks、MCP 和 Worker 的完整流程。前提：已执行 `cursor-mem install --global` 且 Worker 处于运行状态（`cursor-mem status` 显示 Worker: running）。

### 前置条件

1. 终端执行：`cursor-mem install --global`，并重启 Cursor。
2. 终端执行：`cursor-mem start`（若未运行），然后 `cursor-mem status` 确认 Worker 为 running。
3. 打开一个项目（例如本仓库 `cursor-mem`）作为工作区。

---

### 用例 1：提交 Prompt → 会话初始化与记录

**步骤：**

1. 在 Cursor 的 AI 输入框输入一句提示，例如：  
   **「请列出当前项目根目录下的所有 .md 文件。」**
2. 发送该条消息（可不必等 Agent 执行完）。

**预期：**

- `beforeSubmitPrompt` 被触发，Worker 会创建/更新会话并记录本次 prompt。
- 在浏览器打开 http://127.0.0.1:37800 ，在「会话列表」或「时间线」中能看到新会话或新的一条「prompt」类记录。

**校验：**

- 终端执行：`cursor-mem data stats`，应看到 Sessions 总数 ≥ 1。
- 或在 Web 查看器里看到对应会话与一条 prompt 记录。

---

### 用例 2：Agent 执行 Shell → 记录 Shell 观测

**步骤：**

1. 在 Cursor 对话里输入：  
   **「在项目根目录执行：`ls -la`，并把结果发给我。」**
2. 等待 Agent 执行完该命令。

**预期：**

- `afterShellExecution` 被触发，Worker 收到并存储一条 type=shell 的观测。
- Web 查看器时间线中会出现一条与 `ls -la` 相关的记录（标题或内容含命令/输出摘要）。

**校验：**

- 打开 http://127.0.0.1:37800 ，在时间线或会话详情中查看是否有「shell」类型记录，内容包含 `ls` 或输出片段。

---

### 用例 3：Agent 编辑文件 → 记录文件编辑

**步骤：**

1. 在对话里输入：  
   **「在项目根目录创建一个文件 `test_manual.txt`，内容写一行：Hello cursor-mem.」**
2. 等待 Agent 创建/编辑文件完成。

**预期：**

- `afterFileEdit` 被触发，Worker 存储一条 type=file_edit 的观测。
- Web 查看器中能看到对 `test_manual.txt` 的编辑记录。

**校验：**

- Web 查看器时间线或会话详情中有「file_edit」类型，且与 `test_manual.txt` 相关。

---

### 用例 4：在对话中使用 MCP 记忆搜索

**步骤：**

1. 在 Cursor 对话里输入（让 Agent 调用 MCP）：  
   **「请用 memory_search 查一下和 “test” 或 “README” 相关的历史记录，并简要总结。」**
2. 等待 Agent 调用 `memory_search` 并回复。

**预期：**

- Agent 能成功调用 MCP 工具 `memory_search`。
- `afterMCPExecution` 被触发，Worker 会记录此次 MCP 调用。
- 若之前有包含 "test" 或 "README" 的会话/观测，应能搜到并出现在回复或 MCP 结果中。

**校验：**

- Web 查看器时间线中出现 type=mcp、tool 为 memory_search 的记录。
- Agent 回复中提及搜索到的内容或「没有找到」等结论。

---

### 用例 5：会话结束 → 摘要与上下文更新

**步骤：**

1. 完成上述若干轮对话（例如 1～4 都做过）后，结束当前对话（例如新开一个 Chat 或关闭当前 Chat 以触发 stop）。
2. 若 Cursor 的 stop hook 会在「会话结束」时触发，则 Worker 会收到 `stop` 并执行 summarize。

**预期：**

- `stop` 被调用后，Worker 对该会话做摘要（若启用 AI 则可能更丰富，否则为规则摘要）。
- 会话状态变为 completed，且项目下的 `.cursor/rules/cursor-mem.mdc`（或全局注入路径）会更新，包含近期会话摘要/观测摘要。

**校验：**

- 终端：`cursor-mem data stats` 中 completed 会话数增加。
- 打开当前项目下的 `.cursor/rules/cursor-mem.mdc`，应能看到与最近会话相关的摘要或观测摘要（视配置而定）。

---

### 用例 6：新对话注入历史上下文

**步骤：**

1. 在**同一项目**中新建一个 Cursor Chat。
2. 在第一条消息里输入：  
   **「根据你记得的之前在这个项目里做过的事情，简要列出来。」**

**预期：**

- 新对话的 `beforeSubmitPrompt` 会触发，Worker 会为该会话初始化并调用 context 构建/注入。
- Agent 能读到 `.cursor/rules/cursor-mem.mdc` 中的历史摘要，回复中应能提及之前做过的操作（如 ls、创建 test_manual.txt、memory_search 等）。

**校验：**

- Agent 的回复应包含对「之前做过的事」的概括（来自 cursor-mem 注入的上下文）。

---

### 用例 7：MCP 时间线与详情

**步骤：**

1. 在对话中让 Agent 调用：  
   **「调用 memory_timeline，把最近 5 条时间线记录发给我。」**
2. 再让 Agent 调用：  
   **「用 memory_get 查一下刚才时间线里第一条观测的 id 的详情。」**（若 Agent 能拿到 id）

**预期：**

- `memory_timeline` 返回最近观测的时间线列表。
- `memory_get` 根据传入的 id 列表返回对应观测详情。

**校验：**

- 回复中有时间线条目和/或观测详情，与 Web 查看器中的数据一致。

---

### 用例 8：CLI 与 Web 查看器

**步骤：**

1. 终端执行：`cursor-mem status` → 确认 Worker、Port、Data dir、AI 状态。
2. 执行：`cursor-mem config get` → 查看当前配置。
3. 执行：`cursor-mem data stats`、`cursor-mem data projects`。
4. 浏览器打开 http://127.0.0.1:37800 → 查看会话列表、时间线、搜索框。

**预期：**

- status 显示 Worker running、Port 37800、Data dir 为 `~/.cursor-mem`。
- config get 输出合法 JSON 或 key=value。
- data stats 显示会话与观测数量；data projects 列出项目。
- Web 页面能加载，会话/时间线/搜索与当前数据一致。

---

## 三、故障排查

- **Hook 没触发**：确认 `~/.cursor/hooks.json`（全局）或 `<project>/.cursor/hooks.json`（项目）中存在 cursor-mem 的 command，且 Cursor 已重启。
- **Worker 显示 stopped**：执行 `cursor-mem start`，若仍退出则查看 `~/.cursor-mem/worker-stderr.log`；或前台运行 `python -m cursor_mem.worker.server` 看报错。
- **MCP 无响应**：确认 `~/.cursor/mcp.json` 中已注册 `cursor-mem`，且 Worker 在运行；在 Cursor 设置中确认 MCP 已启用。
