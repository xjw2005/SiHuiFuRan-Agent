from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterator

from dotenv import load_dotenv

from mokioclaw.core.paths import default_workspace
from mokioclaw.core.state import RuntimeState
from mokioclaw.graph.workflow import build_workflow


def create_runtime(
    workspace: Path | None = None,
    *,
    approval_mode: str = "inline",
    approval_handler=None,
) -> RuntimeState:
    load_dotenv()
    selected = workspace or default_workspace()
    selected.mkdir(parents=True, exist_ok=True)
    return RuntimeState(
        workspace=selected,
        approval_mode=approval_mode,
        approval_handler=approval_handler,
        bash_default_timeout_seconds=_env_int("MOKIO_BASH_DEFAULT_TIMEOUT_SECONDS", 120),
        bash_max_timeout_seconds=_env_int("MOKIO_BASH_MAX_TIMEOUT_SECONDS", 600),
        bash_max_output_chars=_env_int("MOKIO_BASH_MAX_OUTPUT_CHARS", 6000),
        bash_env_file=_env_path("MOKIO_BASH_ENV_FILE"),
    )


def stream_agent_events(
    task: str,
    *,
    workspace: Path | None = None,
    max_attempts: int = 3,
    approval_mode: str = "inline",
    approval_handler=None,
) -> Iterator[dict[str, Any]]:
    state = create_runtime(workspace, approval_mode=approval_mode, approval_handler=approval_handler)
    workflow = build_workflow()
    yield {"type": "workspace", "path": str(state.workspace)}

    inputs: dict[str, Any] = {
        "task": task,
        "runtime": state,
        "messages": [],
        "attempts": 0,
        "max_attempts": max_attempts,
    }
    for mode, event in workflow.stream(inputs, stream_mode=["updates", "custom"]):
        if mode == "custom":
            yield {"type": "custom_event", "event": event}
        else:
            yield {"type": "graph_event", "event": event}


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _env_path(name: str) -> Path | None:
    raw = os.getenv(name, "").strip()
    return Path(raw).expanduser() if raw else None
