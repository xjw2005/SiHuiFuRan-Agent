from __future__ import annotations

from pathlib import Path

from mokioclaw.core.state import RuntimeState
from langchain_core.messages import AIMessage

from mokioclaw.graph.nodes import actor_node, final_node, planner_node, verifier_node, verifier_route
from mokioclaw.graph.workflow import build_workflow


def test_verifier_passes_when_all_commands_succeed(tmp_path: Path) -> None:
    state = {
        "runtime": RuntimeState(workspace=tmp_path),
        "verification_commands": ["python --version"],
        "todos": [{"id": "todo-1", "content": "verify", "status": "in_progress", "note": ""}],
        "attempts": 0,
        "max_attempts": 3,
    }

    result = verifier_node(state)

    assert result["passed"] is True
    assert result["attempts"] == 1
    assert result["todos"][0]["status"] == "completed"
    assert result["todos"][0]["note"] == "verified"
    assert verifier_route({**state, **result}) == "final"


def test_verifier_routes_back_to_planner_before_max_attempts(tmp_path: Path) -> None:
    state = {
        "runtime": RuntimeState(workspace=tmp_path),
        "verification_commands": ["python missing_file.py"],
        "attempts": 0,
        "max_attempts": 3,
    }

    result = verifier_node(state)

    assert result["passed"] is False
    assert result["attempts"] == 1
    assert "missing_file.py" in result["last_error"]
    assert verifier_route({**state, **result}) == "planner"


def test_verifier_routes_to_final_at_max_attempts(tmp_path: Path) -> None:
    state = {
        "runtime": RuntimeState(workspace=tmp_path),
        "verification_commands": ["python missing_file.py"],
        "attempts": 2,
        "max_attempts": 3,
    }

    result = verifier_node(state)

    assert result["passed"] is False
    assert result["attempts"] == 3
    assert verifier_route({**state, **result}) == "final"


def test_final_node_reports_status() -> None:
    result = final_node(
        {
            "passed": True,
            "plan_summary": "demo plan",
            "todos": [{"content": "write tests", "status": "completed"}],
            "verification_results": [{"command": "python -m pytest -q", "exit_code": 0, "ok": True, "stdout": "", "stderr": ""}],
            "last_actor_summary": "done",
        }
    )

    assert "PASSED" in result["final_answer"]
    assert "demo plan" in result["final_answer"]


def test_workflow_compiles() -> None:
    workflow = build_workflow()

    assert workflow is not None


def test_conway_planner_uses_fixed_verifier_commands(monkeypatch, tmp_path: Path) -> None:
    class FakeModel:
        def invoke(self, messages):
            class Response:
                content = '{"plan_summary":"custom","todos":["todo"],"acceptance_criteria":["ok"],"verification_commands":["python game_of_life.py"]}'

            return Response()

    monkeypatch.setattr("mokioclaw.graph.nodes.create_model", lambda: FakeModel())
    result = planner_node(
        {
            "task": "帮我用 TDD 模式开发一个终端版的《康威生命游戏》",
            "runtime": RuntimeState(workspace=tmp_path),
            "attempts": 0,
            "max_attempts": 3,
        }
    )

    assert result["verification_commands"] == [
        "python -m pytest -q",
        "python game_of_life.py --demo --steps 3",
    ]
    assert result["todos"][0]["id"] == "todo-1"
    assert result["todos"][0]["status"] == "pending"


def test_actor_does_not_complete_all_todos_without_updates(monkeypatch, tmp_path: Path) -> None:
    class FakeBoundModel:
        def invoke(self, messages):
            return AIMessage(content="No tool calls.")

    class FakeModel:
        def bind_tools(self, tools):
            return FakeBoundModel()

    monkeypatch.setattr("mokioclaw.graph.nodes.create_model", lambda: FakeModel())
    result = actor_node(
        {
            "task": "demo",
            "runtime": RuntimeState(workspace=tmp_path),
            "todos": [
                {"id": "todo-1", "content": "write tests", "status": "pending", "note": ""},
                {"id": "todo-2", "content": "implement", "status": "pending", "note": ""},
            ],
            "acceptance_criteria": [],
            "verification_commands": [],
        }
    )

    assert [todo["status"] for todo in result["todos"]] == ["pending", "pending"]


def test_actor_wraps_tool_exceptions_as_tool_messages(monkeypatch, tmp_path: Path) -> None:
    class FakeBoundModel:
        def __init__(self):
            self.calls = 0

        def invoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "FileWriteTool",
                            "args": {"file_path": "../outside.py", "content": "bad"},
                            "id": "call-1",
                        }
                    ],
                )
            return AIMessage(content="saw tool error")

    class FakeModel:
        def bind_tools(self, tools):
            return FakeBoundModel()

    monkeypatch.setattr("mokioclaw.graph.nodes.create_model", lambda: FakeModel())
    result = actor_node(
        {
            "task": "demo",
            "runtime": RuntimeState(workspace=tmp_path),
            "todos": [{"id": "todo-1", "content": "write", "status": "pending", "note": ""}],
            "acceptance_criteria": [],
            "verification_commands": [],
        }
    )

    assert "saw tool error" in result["last_actor_summary"]
