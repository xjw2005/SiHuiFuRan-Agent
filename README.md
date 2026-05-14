<p align="center">
  <img src="./logo.png" alt="MokioClaw Logo" width="420" />
</p>

<h1 align="center">MokioClaw</h1>

<p align="center">
  从零开始，一步步组装一个真正能做事的 Agent 系统。
</p>

## 项目主旨

MokioClaw 是一个教学优先的 Mini CodeAgent 项目。它沿着 Agent 系统自然生长的路径推进：先让模型通过 ToolCall 触碰文件和命令行，再把执行过程升级成显式的工作流，后续继续引入 MultiAgent、Context Engineering、Harness Engineering、Skill 和更完整的 Claw 产品壳。

当前项目的重点是把“Agent 怎么从聊天变成工程执行系统”讲清楚：每个阶段都要能运行、能展示、能解释。

## 当前阶段

当前处于第 2 阶段：LangGraph `planner -> actor -> verifier` 工作流。

第 1 阶段的 `create_agent` 路径已经被替换。现在 `mokioclaw "任务"` 默认运行显式 LangGraph：

```text
User Task
   |
   v
planner
   |
   v
actor
   |
   v
verifier
   | pass
   v
final
   ^
   | fail and attempts < max_attempts
   +--------- planner
```

标志性演示任务：

```bash
uv run mokioclaw "帮我用 TDD 模式开发一个终端版的《康威生命游戏》"
```

这个任务适合展示第二阶段，因为它有清晰规则、天然适合 TDD，也能让 verifier 用命令和测试判断是否过关。

## 当前 Tool 与节点

| 节点 | 使用工具 | 职责 |
| --- | --- | --- |
| `planner` | `TodoWriteTool` | 生成计划、todos、验收标准和验证命令 |
| `actor` | `FileReadTool` / `FileWriteTool` / `FileEditTool` / `GrepTool` / `BashTool` | 按计划写测试、写实现、运行命令、修复问题 |
| `verifier` | `BashTool` | 独立执行验证命令，所有命令成功才算通过 |
| `final` | 无 | 汇总计划、文件、验证结果和运行方式 |

当前工具：

| Tool | 职责 | 设计重点 |
| --- | --- | --- |
| `TodoWriteTool` | 写入 todo、验收标准、验证命令 | 让 planner 的计划外显 |
| `FileReadTool` | 读取 workspace 内文本文件 | 支持 `offset` / `limit`，记录“已读状态” |
| `FileWriteTool` | 创建文件或整文件写入 | 覆盖已有文件前要求先读 |
| `FileEditTool` | 对已有文件做局部替换 | 基于 `old_text` / `new_text`，要求唯一匹配 |
| `GrepTool` | 搜索 workspace 内文本内容 | 用结构化方式定位内容 |
| `BashTool` | 执行开发命令 | 固定 workspace、超时、输出截断、基础安全拦截 |

## 文件目录

```text
MokioAgent/
├─ logo.png
├─ README.md
├─ pyproject.toml
├─ main.py
├─ uv.lock
├─ src/
│  └─ mokioclaw/
│     ├─ cli/
│     │  ├─ app.py              # Typer CLI 入口
│     │  └─ formatter.py        # LangGraph 节点事件展示
│     ├─ core/
│     │  ├─ agent.py            # LangGraph workflow 运行入口
│     │  ├─ paths.py            # 项目根目录与 workspace 路径
│     │  └─ state.py            # RuntimeState 与文件快照
│     ├─ graph/
│     │  ├─ state.py            # Graph state
│     │  ├─ nodes.py            # planner / actor / verifier / final
│     │  └─ workflow.py         # StateGraph 组装与路由
│     ├─ providers/
│     │  └─ openai_provider.py  # 从 .env 创建 ChatOpenAI
│     ├─ prompts/
│     │  └─ stage2.py           # 当前 LangGraph 节点 prompt
│     └─ tools/
│        ├─ registry.py         # 工具注册
│        ├─ todo_tool.py        # TodoWriteTool
│        ├─ file_tools.py       # Read / Write / Edit
│        ├─ grep_tool.py        # 内容搜索
│        └─ bash_tool.py        # 命令执行
└─ tests/
   ├─ test_tools.py
   ├─ test_graph.py
   └─ test_cli_smoke.py
```

运行时会自动创建：

```text
.mokioclaw/
└─ workspace/
   └─ ... Agent 生成的代码、测试和运行产物
```

## 示例执行链路

用户输入：

```bash
uv run mokioclaw "帮我用 TDD 模式开发一个终端版的《康威生命游戏》"
```

典型链路：

1. CLI 创建 workspace 和 `RuntimeState`。
2. `planner` 生成计划：写 `test_game_of_life.py`、运行失败测试、写 `game_of_life.py`、运行最终验证。
3. `actor` 调用 `FileWriteTool` 写测试文件。
4. `actor` 调用 `BashTool` 运行 `python -m pytest -q`，观察测试失败。
5. `actor` 调用 `FileWriteTool` 写实现文件。
6. `actor` 继续调用 `BashTool` 运行测试和 demo。
7. `verifier` 独立运行：

```bash
python -m pytest -q
python game_of_life.py --demo --steps 3
```

8. 如果 verifier 失败，失败命令和 stdout/stderr 回到 `planner`，重新修订计划。
9. 如果 verifier 通过，进入 `final`，输出文件、验证命令、通过状态和运行方式。

这一阶段的教学价值是：执行流程不再藏在 Agent 黑盒里，而是变成可以讲、可以看、可以调试的 LangGraph 状态流转。

## 运行方式

`.env` 配置：

```text
API_KEY=...
MODEL=...
BASE_URL=...
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
uv run mokioclaw "帮我用 TDD 模式开发一个终端版的《康威生命游戏》"
```
