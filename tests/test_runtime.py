from __future__ import annotations

from pathlib import Path

from mokioclaw.core.agent import create_runtime
from mokioclaw.core.paths import new_task_workspace


def test_new_task_workspace_is_unique(tmp_path: Path) -> None:
    first = new_task_workspace(tmp_path)
    second = new_task_workspace(tmp_path)

    assert first != second
    assert first.parent == tmp_path / ".mokioclaw" / "workspaces"
    assert first.name.startswith("workspace-")


def test_create_runtime_uses_fresh_default_workspace(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("mokioclaw.core.paths.find_project_root", lambda start=None: tmp_path)

    first = create_runtime()
    second = create_runtime()

    assert first.workspace != second.workspace
    assert first.workspace.exists()
    assert second.workspace.exists()


def test_create_runtime_respects_explicit_workspace(tmp_path: Path) -> None:
    explicit = tmp_path / "my-workspace"

    runtime = create_runtime(explicit)

    assert runtime.workspace == explicit
    assert explicit.exists()


def test_create_runtime_sets_approval_configuration(tmp_path: Path) -> None:
    handler = lambda request: True

    runtime = create_runtime(tmp_path / "workspace", approval_mode="deny", approval_handler=handler)

    assert runtime.approval_mode == "deny"
    assert runtime.approval_handler is handler


def test_create_runtime_reads_bash_harness_env(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / "agent.env"
    monkeypatch.setenv("MOKIO_BASH_DEFAULT_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("MOKIO_BASH_MAX_TIMEOUT_SECONDS", "300")
    monkeypatch.setenv("MOKIO_BASH_MAX_OUTPUT_CHARS", "1234")
    monkeypatch.setenv("MOKIO_BASH_ENV_FILE", str(env_file))

    runtime = create_runtime(tmp_path / "workspace")

    assert runtime.bash_default_timeout_seconds == 45
    assert runtime.bash_max_timeout_seconds == 300
    assert runtime.bash_max_output_chars == 1234
    assert runtime.bash_env_file == env_file
