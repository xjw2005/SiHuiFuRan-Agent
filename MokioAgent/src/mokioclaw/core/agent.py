from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterator

from dotenv import load_dotenv
from langgraph.graph import add_messages

from mokioclaw.core.checkpoint import CheckpointManager, load_resume_inputs, normalize_checkpoint_mode
from mokioclaw.core.paths import default_workspace
from mokioclaw.core.session import (
    append_assistant_turn,
    append_user_turn,
    build_session_context,
    load_or_create_session,
    save_session,
    session_started_event,
    session_turn_saved_event,
    session_turn_started_event,
)
from mokioclaw.core.state import RuntimeState
from mokioclaw.core.trace import TraceRecorder, normalize_trace_mode
from mokioclaw.graph.workflow import build_complex_workflow, build_entry_workflow


def create_runtime(
    workspace: Path | None = None,
    *,
    approval_mode: str = "inline",
    approval_handler=None,
    checkpoint_mode: str | None = None,
    resume_from: Path | None = None,
    trace_mode: str | None = None,
) -> RuntimeState:
    load_dotenv()
    selected = workspace or resume_from or default_workspace()
    selected.mkdir(parents=True, exist_ok=True)
    return RuntimeState(
        workspace=selected,
        approval_mode=approval_mode,
        approval_handler=approval_handler,
        bash_default_timeout_seconds=_env_int("MOKIO_BASH_DEFAULT_TIMEOUT_SECONDS", 120),
        bash_max_timeout_seconds=_env_int("MOKIO_BASH_MAX_TIMEOUT_SECONDS", 600),
        bash_max_output_chars=_env_int("MOKIO_BASH_MAX_OUTPUT_CHARS", 6000),
        bash_env_file=_env_path("MOKIO_BASH_ENV_FILE"),
        checkpoint_mode=normalize_checkpoint_mode(checkpoint_mode or os.getenv("MOKIO_CHECKPOINT_MODE", "light")),
        resume_from=resume_from,
        trace_mode=normalize_trace_mode(trace_mode or os.getenv("MOKIO_TRACE_MODE", "on")),
    )


# stream_agent_events：Agent 的核心调度引擎
# 这是一个生成器函数，会"做一步，吐一步"地流式输出 Agent 的执行过程
# 返回值类型 Iterator[dict[str, Any]] 表示这是一个迭代器，每次产出一个字典类型的 event
def stream_agent_events(
    task: str | None = None,  # 用户的任务描述，比如"帮我创建一个Flask项目"
    *,                        # * 号表示后面的参数必须用关键字参数传，不能 positional
    workspace: Path | None = None,  # 工作目录路径，生成的文件会放这里
    max_attempts: int = 3,    # 最大尝试次数，planner/verifier 循环最多跑几轮
    approval_mode: str = "inline",  # 危险命令的审批模式：inline / auto / deny
    approval_handler=None,     # 审批回调函数，inline 模式下会弹出终端问用户 Y/N
    checkpoint_mode: str | None = None,  # 断点保存模式：light / strict / off
    resume_workspace: Path | None = None,  # 断点恢复路径，从哪个目录接着跑
    trace_mode: str | None = None,  # 追踪日志开关：on / off
) -> Iterator[dict[str, Any]]:
    # 处理恢复路径：expanduser() 把 ~ 展开成用户目录
    resume_path = resume_workspace.expanduser() if resume_workspace is not None else None

    # 如果不是断点恢复（也就是新任务），先跑 entry_workflow 做意图判断
    if resume_path is None:
        # 默认走 workflow 分支
        route = "workflow"
        # 初始化入口工作流的 state
        entry_state: dict[str, Any] = {"task": task or "", "messages": []}

        # 流式跑 entry_workflow（intent_router → chat_responder / planner）
        for mode, event in build_entry_workflow().stream(entry_state, stream_mode=["updates", "custom"]):
            if mode == "custom":
                # custom 类型的事件直接转发出去（比如 intent_router 的决策结果）
                yield {"type": "custom_event", "event": event}
                # 如果收到了 intent_decision 事件，把 route 存下来（chat 或 workflow）
                if isinstance(event, dict) and event.get("type") == "intent_decision":
                    route = str(event.get("route") or "workflow")
            else:
                # updates 类型的事件：更新 state，然后转发
                _merge_graph_update(entry_state, event)
                yield {"type": "graph_event", "event": event}

        # 如果判断是 chat（闲聊/概念问题），直接结束，不跑复杂工作流
        if route == "chat":
            return

    # ========== 下面开始跑 complex_workflow ==========

    # 确定工作目录：优先用恢复路径，其次用用户指定的 workspace
    selected_workspace = resume_path or workspace

    # 创建 runtime 对象：统一管理工作目录、审批配置、断点配置等
    state = create_runtime(
        selected_workspace,
        approval_mode=approval_mode,
        approval_handler=approval_handler,
        checkpoint_mode=checkpoint_mode,
        resume_from=resume_path,
        trace_mode=trace_mode,
    )

    # 构建复杂工作流的图对象
    workflow = build_complex_workflow()

    # 先输出一个 workspace 事件，告诉用户工作目录在哪
    yield {"type": "workspace", "path": str(state.workspace)}

    # resumed 标记：是否是从断点恢复的
    resumed = False
    # resume_event：恢复事件的详情
    resume_event: dict[str, Any] | None = None

    # 如果是断点恢复模式
    if resume_path is not None:
        # 从 checkpoint 加载恢复所需的 inputs
        inputs, resume_event = load_resume_inputs(state, task=task, max_attempts=max_attempts)
        resumed = True
        # 输出恢复事件，告诉用户"从之前的断点续跑了"
        yield {"type": "custom_event", "event": resume_event}
    else:
        # 全新任务：初始化 inputs
        inputs = {
            "task": task or "",      # 任务描述
            "runtime": state,        # runtime 对象
            "messages": [],          # 消息列表（LLM 的对话历史）
            "attempts": 0,           # 当前尝试次数
            "max_attempts": max_attempts,  # 最大尝试次数
        }

    # 复制一份 inputs 作为 current_state，用来追踪每一步的状态更新
    current_state: dict[str, Any] = dict(inputs)

    # 创建 CheckpointManager：负责保存断点
    manager = CheckpointManager(state, task=str(current_state.get("task", "")))

    # 创建 TraceRecorder：负责记录执行追踪日志
    trace = TraceRecorder(state, task=str(current_state.get("task", "")))

    # 开始追踪
    trace.start(current_state, resumed=resumed, resume_event=resume_event)

    # 如果有恢复事件，也记录到 trace 里
    if resume_event is not None:
        trace.record_custom_event(resume_event)

    # 保存第一个 checkpoint：状态为 started
    started_checkpoint = manager.save(current_state, status="started", latest_node="start")
    if started_checkpoint:
        trace.record_custom_event(started_checkpoint)

    # 记录当前跑到哪个节点了，初始是 start
    latest_node = "start"

    # ========== 核心主循环：流式跑 complex_workflow ==========
    try:
        # 流式迭代工作流的每一步
        for mode, event in workflow.stream(inputs, stream_mode=["updates", "custom"]):
            if mode == "custom":
                # custom 事件：工具调用、hand off 等非节点更新事件
                trace.record_custom_event(event)  # 记录到 trace
                # 判断这个事件是否需要触发 checkpoint（比如工具出错、需要审批）
                if _custom_event_needs_checkpoint(event):
                    saved = manager.save(current_state, status="running", latest_node=latest_node, event={"mode": mode, "payload": event})
                    if saved:
                        trace.record_custom_event(saved)
                # 输出事件给终端显示
                yield {"type": "custom_event", "event": event}
            else:
                # updates 事件：节点执行完成，state 更新了
                latest_node = _latest_graph_node(event) or latest_node  # 更新当前节点名
                _merge_graph_update(current_state, event)  # 合并 state 更新
                trace.record_graph_update(event)  # 记录到 trace
                # 保存 checkpoint
                saved = manager.save(current_state, status="running", latest_node=latest_node, event={"mode": mode, "payload": event})
                if saved:
                    trace.record_custom_event(saved)
                # 输出事件给终端显示
                yield {"type": "graph_event", "event": event}
    except KeyboardInterrupt:
        # 用户按了 Ctrl+C 中断
        # 保存 interrupted 状态的 checkpoint
        saved = manager.save(current_state, status="interrupted", latest_node=latest_node)
        if saved:
            trace.record_custom_event(saved)
            yield {"type": "custom_event", "event": saved}
        # 结束追踪，输出 trace 摘要
        trace_event = trace.end(status="interrupted", latest_node=latest_node, final_state=current_state)
        if trace_event:
            yield {"type": "custom_event", "event": trace_event}
        return  # 中断返回

    # ========== 正常跑完了，收尾 ==========
    # 保存 finished 状态的 checkpoint
    saved = manager.save(current_state, status="finished", latest_node=latest_node)
    if saved:
        trace.record_custom_event(saved)
        yield {"type": "custom_event", "event": saved}

    # 结束追踪，输出最终的 trace 摘要
    trace_event = trace.end(status="finished", latest_node=latest_node, final_state=current_state)
    if trace_event:
        yield {"type": "custom_event", "event": trace_event}


def stream_session_events(
    task: str | None = None,
    *,
    session_workspace: Path | None = None,
    max_attempts: int = 3,
    approval_mode: str = "inline",
    approval_handler=None,
    checkpoint_mode: str | None = None,
    resume_workspace: Path | None = None,
    trace_mode: str | None = None,
) -> Iterator[dict[str, Any]]:
    workspace = (resume_workspace or session_workspace or default_workspace()).expanduser()
    workspace.mkdir(parents=True, exist_ok=True)
    session = load_or_create_session(workspace)
    resumed = resume_workspace is not None
    yield {"type": "custom_event", "event": session_started_event(workspace, session, resumed=resumed)}
    yield {"type": "workspace", "path": str(workspace)}

    if not task:
        return

    turn = append_user_turn(session, task)
    save_session(workspace, session)
    yield {"type": "custom_event", "event": session_turn_started_event(workspace, session, turn=turn, task=task)}
    session_context = build_session_context(workspace, session)

    route = "workflow"
    entry_state: dict[str, Any] = {
        "task": task or "",
        "messages": [],
        "session_id": session.get("session_id", ""),
        "session_turn": turn,
        "session_context": session_context,
    }
    for mode, event in build_entry_workflow().stream(entry_state, stream_mode=["updates", "custom"]):
        if mode == "custom":
            yield {"type": "custom_event", "event": event}
            if isinstance(event, dict) and event.get("type") == "intent_decision":
                route = str(event.get("route") or "workflow")
        else:
            _merge_graph_update(entry_state, event)
            yield {"type": "graph_event", "event": event}

    if route == "chat":
        response = str(entry_state.get("chat_response") or entry_state.get("final_answer") or "")
        append_assistant_turn(session, turn=turn, route="chat", content=response, summary=response)
        save_session(workspace, session)
        yield {"type": "custom_event", "event": session_turn_saved_event(workspace, session, turn=turn, route="chat")}
        return

    workflow_events = _stream_complex_workflow(
        task=task,
        workspace=workspace,
        max_attempts=max_attempts,
        approval_mode=approval_mode,
        approval_handler=approval_handler,
        checkpoint_mode=checkpoint_mode,
        resume_workspace=resume_workspace,
        trace_mode=trace_mode,
        session=session,
        turn=turn,
        session_context=session_context,
    )
    final_answer = ""
    for event in workflow_events:
        final_answer = _final_answer_from_event(event) or final_answer
        yield event

    append_assistant_turn(session, turn=turn, route="workflow", content=final_answer, summary=final_answer)
    save_session(workspace, session)
    yield {"type": "custom_event", "event": session_turn_saved_event(workspace, session, turn=turn, route="workflow")}


def _stream_complex_workflow(
    *,
    task: str | None,
    workspace: Path,
    max_attempts: int,
    approval_mode: str,
    approval_handler,
    checkpoint_mode: str | None,
    resume_workspace: Path | None,
    trace_mode: str | None,
    session: dict[str, Any] | None = None,
    turn: int | None = None,
    session_context: str = "",
) -> Iterator[dict[str, Any]]:
    resume_path = resume_workspace.expanduser() if resume_workspace is not None else None
    state = create_runtime(
        workspace,
        approval_mode=approval_mode,
        approval_handler=approval_handler,
        checkpoint_mode=checkpoint_mode,
        resume_from=resume_path,
        trace_mode=trace_mode,
    )
    workflow = build_complex_workflow()

    resumed = False
    resume_event: dict[str, Any] | None = None
    if resume_path is not None:
        inputs, resume_event = load_resume_inputs(state, task=task, max_attempts=max_attempts)
        resumed = True
        yield {"type": "custom_event", "event": resume_event}
    else:
        inputs = {
            "task": task or "",
            "runtime": state,
            "messages": [],
            "attempts": 0,
            "max_attempts": max_attempts,
        }

    if session is not None:
        inputs["session_id"] = session.get("session_id", "")
    if turn is not None:
        inputs["session_turn"] = turn
    if session_context:
        inputs["session_context"] = session_context
    metadata = dict(inputs.get("metadata", {}))
    if session is not None:
        metadata["session_id"] = session.get("session_id", "")
    if turn is not None:
        metadata["session_turn"] = turn
    if metadata:
        inputs["metadata"] = metadata

    current_state: dict[str, Any] = dict(inputs)
    manager = CheckpointManager(state, task=str(current_state.get("task", "")))
    trace = TraceRecorder(state, task=str(current_state.get("task", "")))
    trace.start(current_state, resumed=resumed, resume_event=resume_event)
    if resume_event is not None:
        trace.record_custom_event(resume_event)
    started_checkpoint = manager.save(current_state, status="started", latest_node="start")
    if started_checkpoint:
        trace.record_custom_event(started_checkpoint)
    latest_node = "start"

    try:
        for mode, event in workflow.stream(inputs, stream_mode=["updates", "custom"]):
            if mode == "custom":
                trace.record_custom_event(event)
                if _custom_event_needs_checkpoint(event):
                    saved = manager.save(current_state, status="running", latest_node=latest_node, event={"mode": mode, "payload": event})
                    if saved:
                        trace.record_custom_event(saved)
                yield {"type": "custom_event", "event": event}
            else:
                latest_node = _latest_graph_node(event) or latest_node
                _merge_graph_update(current_state, event)
                trace.record_graph_update(event)
                saved = manager.save(current_state, status="running", latest_node=latest_node, event={"mode": mode, "payload": event})
                if saved:
                    trace.record_custom_event(saved)
                yield {"type": "graph_event", "event": event}
    except KeyboardInterrupt:
        saved = manager.save(current_state, status="interrupted", latest_node=latest_node)
        if saved:
            trace.record_custom_event(saved)
            yield {"type": "custom_event", "event": saved}
        trace_event = trace.end(status="interrupted", latest_node=latest_node, final_state=current_state)
        if trace_event:
            yield {"type": "custom_event", "event": trace_event}
        return

    saved = manager.save(current_state, status="finished", latest_node=latest_node)
    if saved:
        trace.record_custom_event(saved)
        yield {"type": "custom_event", "event": saved}
    trace_event = trace.end(status="finished", latest_node=latest_node, final_state=current_state)
    if trace_event:
        yield {"type": "custom_event", "event": trace_event}


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _env_path(name: str) -> Path | None:
    raw = os.getenv(name, "").strip()
    return Path(raw).expanduser() if raw else None


def _latest_graph_node(event: Any) -> str | None:
    if isinstance(event, dict) and event:
        return str(next(reversed(event)))
    return None


def _merge_graph_update(state: dict[str, Any], event: Any) -> None:
    if not isinstance(event, dict):
        return
    for update in event.values():
        if not isinstance(update, dict):
            continue
        for key, value in update.items():
            if key == "messages":
                state["messages"] = list(add_messages(state.get("messages", []), value))
            else:
                state[key] = value


def _custom_event_needs_checkpoint(event: Any) -> bool:
    if not isinstance(event, dict):
        return False
    if event.get("type") != "tool_result":
        return False
    result = event.get("result")
    if not isinstance(result, dict):
        return False
    return result.get("ok") is False or bool(result.get("requires_approval"))


def _final_answer_from_event(event: dict[str, Any]) -> str:
    if event.get("type") != "graph_event":
        return ""
    payload = event.get("event")
    if not isinstance(payload, dict):
        return ""
    update = payload.get("final")
    if not isinstance(update, dict):
        return ""
    return str(update.get("final_answer") or "")
