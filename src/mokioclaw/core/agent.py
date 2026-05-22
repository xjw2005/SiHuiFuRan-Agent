from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterator

from dotenv import load_dotenv
from langgraph.graph import add_messages

from mokioclaw.core.checkpoint import CheckpointManager, load_resume_inputs, normalize_checkpoint_mode
from mokioclaw.core.paths import default_workspace
from mokioclaw.core.state import RuntimeState
from mokioclaw.graph.workflow import build_workflow


def create_runtime(
    workspace: Path | None = None,
    *,
    approval_mode: str = "inline",
    approval_handler=None,
    checkpoint_mode: str | None = None,
    resume_from: Path | None = None,
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
    )


def stream_agent_events(
    task: str | None = None,
    *,
    workspace: Path | None = None,
    max_attempts: int = 3,
    approval_mode: str = "inline",
    approval_handler=None,
    checkpoint_mode: str | None = None,
    resume_workspace: Path | None = None,
) -> Iterator[dict[str, Any]]:
    resume_path = resume_workspace.expanduser() if resume_workspace is not None else None
    selected_workspace = resume_path or workspace
    state = create_runtime(
        selected_workspace,
        approval_mode=approval_mode,
        approval_handler=approval_handler,
        checkpoint_mode=checkpoint_mode,
        resume_from=resume_path,
    )
    workflow = build_workflow()
    yield {"type": "workspace", "path": str(state.workspace)}

    if resume_path is not None:
        inputs, resume_event = load_resume_inputs(state, task=task, max_attempts=max_attempts)
        yield {"type": "custom_event", "event": resume_event}
    else:
        inputs = {
            "task": task or "",
            "runtime": state,
            "messages": [],
            "attempts": 0,
            "max_attempts": max_attempts,
        }

    current_state: dict[str, Any] = dict(inputs)
    manager = CheckpointManager(state, task=str(current_state.get("task", "")))
    manager.save(current_state, status="started", latest_node="start")
    latest_node = "start"

    try:
        for mode, event in workflow.stream(inputs, stream_mode=["updates", "custom"]):
            if mode == "custom":
                manager.save(current_state, status="running", latest_node=latest_node, event={"mode": mode, "payload": event})
                yield {"type": "custom_event", "event": event}
            else:
                latest_node = _latest_graph_node(event) or latest_node
                _merge_graph_update(current_state, event)
                manager.save(current_state, status="running", latest_node=latest_node, event={"mode": mode, "payload": event})
                yield {"type": "graph_event", "event": event}
    except KeyboardInterrupt:
        saved = manager.save(current_state, status="interrupted", latest_node=latest_node)
        if saved:
            yield {"type": "custom_event", "event": saved}
        return

    saved = manager.save(current_state, status="finished", latest_node=latest_node)
    if saved:
        yield {"type": "custom_event", "event": saved}


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
