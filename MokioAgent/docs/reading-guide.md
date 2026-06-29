# MokioAgent 代码阅读路径

## 第一阶段：入口（搞清楚怎么启动的）

1. **`__main__.py`** — `python -m mokioclaw` 启动入口，调用 `cli.app:app()`
2. **`cli/app.py`** — Typer CLI，解析参数（workspace、max-attempts、approval-mode 等），调用 `stream_agent_events()`
3. **`core/agent.py`** — ⭐ 核心调度引擎，`stream_agent_events()` 是主循环：
   - 先跑 `build_entry_workflow()` 做意图路由（chat vs workflow）
   - 再跑 `build_complex_workflow()` 执行多 Agent 工作流
   - 过程中处理 checkpoint、trace、Ctrl+C 恢复

## 第二阶段：核心图（搞清楚数据怎么流转的）⭐ 最重要

4. **`graph/state.py`** — `MokioGraphState`，图中流转的所有字段
5. **`core/state.py`** — `RuntimeState`，运行时环境（workspace、审批模式、超时等）
6. **`graph/workflow.py`** — 两个图的节点连线：
   - `entry_workflow`: intent_router → chat_responder / planner
   - `complex_workflow`: planner → context_monitor → (compressor) → verifier → planner/final
7. **`graph/nodes.py`** — ⭐⭐ 所有节点逻辑都在这里：
   - `planner_node` — 制定计划，通过 Tool 调用 searchAgent / codeAgent
   - `verifier_node` — 验证结果，不通过则回到 planner
   - `context_monitor_node` / `context_compressor_node` — 防止 token 溢出
   - `final_node` — 输出最终答案

## 第三阶段：Agent 和 Tools（搞清楚能力从哪来）

8. **`agents/code_agent.py`** — 代码执行 Agent（读写文件、跑命令）
9. **`agents/search_agent.py`** — 搜索 Agent（联网搜索）
10. **`tools/`** — 工具集：
    - `bash_tool.py` — 执行 shell 命令
    - `file_tools.py` — 文件读写
    - `grep_tool.py` — 代码搜索
    - `web_search_tool.py` — 网络搜索
    - `todo_tool.py` — 任务清单管理
11. **`prompts/stage3.py`** — planner 和 verifier 的核心提示词

## 第四阶段：支撑系统（按需阅读）

12. **`core/checkpoint.py`** — Ctrl+C 断点恢复
13. **`core/approval.py`** — 危险命令人工审批
14. **`core/session.py`** — 多轮会话管理
15. **`core/trace.py`** — 运行追踪日志
16. **`graph/memory.py`** — 分层记忆系统
17. **`providers/openai_provider.py`** — LLM 模型创建
18. **`cli/formatter.py`** — Rich 终端输出格式化

## 架构一图流

```
用户输入
  → cli/app.py 解析参数
  → core/agent.py 主调度
    → entry_workflow: intent_router 判断 chat/workflow
      → chat_responder（简单问答，结束）
      → complex_workflow（复杂任务）:
        planner（制定计划+委派 search/code agent）
          → context_monitor（token监控）
            → verifier（验证结果）
              → 通过 → final（输出答案）
              → 不通过 → 回到 planner
            → 超限 → context_compressor（压缩上下文）
```

## 阅读建议

1. **先跑起来**：`uv run mokioclaw "帮我创建hello.py"`，对照终端输出理解代码
2. **跟着 state 走**：看每个节点接收什么 state、返回什么 state 更新
3. **planner 是核心**：它把 searchAgent/codeAgent 包装成 Tool，由 LLM 自主决定调用顺序
