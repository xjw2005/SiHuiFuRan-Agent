<p align="center">
  <img src="./logo.png" alt="MokioClaw Logo" width="460" />
</p>

<h1 align="center">MokioClaw</h1>

<p align="center">
  从零开始，一步步丰富一个真正能做事的 Agent 系统。
</p>

## 项目主旨

MokioClaw 是一个教学优先的 Mini CodeAgent 项目。它按 Agent 系统自然生长的路径推进：先从 ToolCall 触碰文件和命令行开始，再升级到 LangGraph 显式工作流，然后继续引入 MultiAgent、Context Engineering、Harness Engineering、Skill 和更完整的 Claw 产品壳。

项目的核心不是“写一个神秘黑盒”，而是把 Agent 如何规划、调用工具、交接子 Agent、验证结果讲清楚。每个阶段都要能运行、能展示、能解释。

## 当前阶段

当前处于第 4 阶段：MultiAgent + Context Engineering 自动压缩。

第 3 阶段的图不再是固定的 `planner -> searchAgent -> codeAgent -> verifier` 顺序链路。现在外层 LangGraph 只有 supervisor 与验收循环：

```text
User Task
   |
   v
planner / supervisor
   |  toolcall: CallSearchAgentTool
   |-----------------------------> searchAgent
   |<----------------------------- research notes + sources
   |
   |  toolcall: CallCodeAgentTool
   |-----------------------------> codeAgent
   |<----------------------------- files + command results
   |
   v
context_monitor
   | token >= limit
   v
context_compressor
   |
   v
verifier / model reviewer
   | pass
   v
final
   ^
   | fail and attempts < max_attempts
   +--------- planner
```

标志性演示任务：

```bash
uv run mokioclaw "帮我查阅明日方舟阿米娅，并编写一个 HTML 介绍人物"
```

这个任务适合展示 MultiAgent，因为它需要先查资料，再把资料转成可交付的 HTML 页面，最后由模型版 verifier 读取文件、执行检查、判断是否完成。第 4 阶段会在 planner/verifier 之间自动监控上下文 token，达到阈值后插入压缩节点。

## Context Engineering

自动压缩不是简单追加一段摘要。`context_compressor` 会使用 LangGraph 的 `RemoveMessage(REMOVE_ALL_MESSAGES)` 真正清空旧 `messages`，再写入一条压缩后的上下文摘要 message。这样后续节点看到的是更小的窗口，而不是越来越长的 transcript。

压缩会保留：

- 用户任务、当前计划、todo、验收标准、验证命令
- searchAgent 的研究结论和来源链接
- codeAgent 的产物、重要文件和执行摘要
- verifier 的失败原因、下一步建议和风险
- workspace 内 `TODO.md` 和 `NOTEPAD.md` 中的持久上下文

默认压缩阈值是 `400000` token，可通过环境变量调整。为了演示压缩效果，可以临时设置小阈值：

```bash
MOKIO_CONTEXT_TOKEN_LIMIT=2000 uv run mokioclaw "帮我查阅明日方舟阿米娅，并编写一个 HTML 介绍人物"
```

## 当前 Tool 与 Agent 架构

| 节点 / Agent | 使用工具 | 职责 |
| --- | --- | --- |
| `planner` | `TodoWriteTool` / `CallSearchAgentTool` / `CallCodeAgentTool` | 制定计划，并通过 toolcall 分派专家 Agent |
| `searchAgent` | `WebSearchTool` | 调用 Tavily 搜索资料，返回研究摘要和 sources |
| `codeAgent` | `FileReadTool` / `FileWriteTool` / `FileEditTool` / `GrepTool` / `BashTool` / `TodoUpdateTool` | 写文件、运行检查、更新 todo 进度 |
| `context_monitor` | 无 | 估算当前上下文 token，决定是否触发压缩 |
| `context_compressor` | 模型压缩 prompt | 删除旧 messages，生成可恢复的压缩上下文 |
| `verifier` | `FileReadTool` / `GrepTool` / `BashTool` / `WebSearchTool` | 模型验收节点，只读检查，不修改文件 |
| `final` | 无 | 汇总计划、来源、验收结果和运行方式 |

当前工具：

| Tool | 职责 | 设计重点 |
| --- | --- | --- |
| `TodoWriteTool` | 写入 todo、验收标准、验证命令 | 让 planner 的计划外显；兼容列表、JSON 列表和以 todo id 为 key 的 description 字典 |
| `TodoUpdateTool` | 更新 todo 状态 | 同步更新 state 和 workspace 内的 `TODO.md` |
| `CallSearchAgentTool` | 调用 searchAgent | 把子 Agent 包装成 planner 的 toolcall |
| `CallCodeAgentTool` | 调用 codeAgent | 把实现专家包装成 planner 的 toolcall |
| `NotepadReadTool` | 读取长期笔记 | 从 workspace 的 `NOTEPAD.md` 恢复上下文 |
| `NotepadAppendTool` | 追加长期笔记 | 记录发现、决策、重要文件、风险和下一步 |
| `WebSearchTool` | Tavily 网络搜索 | 返回 answer 和结构化 sources |
| `FileReadTool` | 读取 workspace 内文本文件 | 支持 `offset` / `limit`，记录“已读状态” |
| `FileWriteTool` | 创建文件或整文件写入 | 覆盖已有文件前要求先读 |
| `FileEditTool` | 对已有文件做局部替换 | 基于 `old_text` / `new_text`，要求唯一匹配 |
| `GrepTool` | 搜索 workspace 内文本内容 | 用结构化方式定位内容 |
| `BashTool` | 执行开发命令 | 固定 workspace、超时、输出截断、基础安全拦截；允许 `2>/dev/null` 这类静默检查 |

## 文件目录

```text
MokioAgent/
├─ logo.png
├─ README.md
├─ pyproject.toml
├─ uv.lock
├─ src/
│  └─ mokioclaw/
│     ├─ agents/
│     │  ├─ search_agent.py     # searchAgent：Tavily 研究专家
│     │  └─ code_agent.py       # codeAgent：文件和命令执行专家
│     ├─ cli/
│     │  ├─ app.py              # Typer CLI 入口
│     │  └─ formatter.py        # Rich 事件时间线展示
│     ├─ core/
│     │  ├─ agent.py            # LangGraph workflow 运行入口
│     │  ├─ paths.py            # 项目根目录与 workspace 路径
│     │  └─ state.py            # RuntimeState 与文件快照
│     ├─ graph/
│     │  ├─ state.py            # Graph state
│     │  ├─ nodes.py            # planner / context monitor / compressor / verifier / final
│     │  └─ workflow.py         # StateGraph 组装与路由
│     ├─ providers/
│     │  └─ openai_provider.py  # 从 .env 创建 ChatOpenAI
│     ├─ prompts/
│     │  ├─ stage3.py           # 第 3 阶段节点与子 Agent prompt
│     │  └─ stage4.py           # Context compression prompt
│     └─ tools/
│        ├─ registry.py         # 工具注册
│        ├─ todo_tool.py        # TodoWrite / TodoUpdate / TODO.md 持久化
│        ├─ notepad_tool.py     # NOTEPAD.md 长期工作笔记
│        ├─ web_search_tool.py  # Tavily WebSearchTool
│        ├─ file_tools.py       # Read / Write / Edit
│        ├─ grep_tool.py        # 内容搜索
│        └─ bash_tool.py        # 命令执行
└─ tests/
   ├─ test_tools.py
   ├─ test_graph.py
   ├─ test_formatter.py
   └─ test_cli_smoke.py
```

运行时会自动创建：

```text
.mokioclaw/
└─ workspace/
   └─ workspaces/
      └─ workspace-YYYYMMDD-HHMMSS-xxxxxx/
         ├─ TODO.md       # 当前任务计划、todo、验收标准和验证命令
         ├─ NOTEPAD.md    # 长期工作笔记，压缩后仍可恢复关键信息
         └─ ... Agent 生成的代码、页面、测试和运行产物
```

默认每次新任务都会创建一个新的 `workspace-*` 目录，避免不同任务互相污染。需要复用或指定目录时，可以显式传入 `--workspace`。

## 示例执行链路

用户输入：

```bash
uv run mokioclaw "帮我查阅明日方舟阿米娅，并编写一个 HTML 介绍人物"
```

指定 workspace：

```bash
uv run mokioclaw --workspace .mokioclaw/workspaces/demo "帮我查阅明日方舟阿米娅，并编写一个 HTML 介绍人物"
```

典型链路：

1. CLI 创建 workspace 和 `RuntimeState`。
2. `planner` 生成计划：搜索资料、创建 `amiya_profile.html`、加入来源链接、运行检查。
3. `planner` 通过 `CallSearchAgentTool` 把研究任务交给 `searchAgent`。
4. `searchAgent` 调用 `WebSearchTool`，从 Tavily 返回摘要和来源链接。
5. `planner` 收到 research notes 和 sources 后，通过 `CallCodeAgentTool` 把实现任务交给 `codeAgent`。
6. `codeAgent` 调用 `TodoUpdateTool` 标记进度，调用 `FileWriteTool` 写出 HTML，并用 `BashTool` 做非交互检查。
7. `codeAgent` 可以调用 `NotepadAppendTool` 把重要发现、文件、风险和下一步写入 `NOTEPAD.md`。
8. `context_monitor` 估算 token；达到阈值时进入 `context_compressor` 压缩消息窗口。
9. `verifier` 作为模型验收节点读取 state，再调用 `FileReadTool` / `GrepTool` / `BashTool` / `WebSearchTool` 检查结果。
10. 如果 verifier 失败，失败原因和下一步建议回到 `planner`，planner 再次分派子 Agent 修复。
11. 如果 verifier 通过，进入 `final`，输出文件、来源、验收结论、压缩次数和运行方式。

这一阶段的教学价值是：MultiAgent 不只是“多个节点排队”，还可以是 supervisor 把 specialist agent 当成工具调用，让交接、上下文和职责边界都在终端里清楚呈现。

## 运行方式

`.env` 配置：

```text
API_KEY=...
MODEL=...
BASE_URL=...
TAVILY_API_KEY=...
MOKIO_CONTEXT_TOKEN_LIMIT=400000
```

同步依赖：

```bash
uv sync
```

运行测试：

```bash
uv run pytest -q
```

运行 Agent：

```bash
uv run mokioclaw "帮我查阅明日方舟阿米娅，并编写一个 HTML 介绍人物"
```
