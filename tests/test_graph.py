from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES, add_messages

from mokioclaw.core.state import RuntimeState
from mokioclaw.graph.nodes import (
    AMIYA_COMMANDS,
    _call_code_agent_tool,
    _call_search_agent_tool,
    context_compressor_node,
    context_compressor_route,
    context_monitor_node,
    context_monitor_route,
    estimate_context_tokens,
    final_node,
    get_context_token_limit,
    planner_node,
    verifier_node,
    verifier_route,
)
from mokioclaw.graph.workflow import build_workflow


def test_model_verifier_passes_from_json(monkeypatch, tmp_path: Path) -> None:
    class FakeBoundModel:
        def invoke(self, messages):
            return AIMessage(
                content=json.dumps(
                    {
                        "passed": True,
                        "reason": "HTML file satisfies the request.",
                        "checks": [{"name": "html", "passed": True, "detail": "ok"}],
                        "recommended_next_instruction": "",
                    }
                )
            )

    class FakeModel:
        def bind_tools(self, tools):
            return FakeBoundModel()

    monkeypatch.setattr("mokioclaw.graph.nodes.create_model", lambda: FakeModel())
    state = {
        "runtime": RuntimeState(workspace=tmp_path),
        "task": "demo",
        "todos": [{"id": "todo-1", "content": "verify", "status": "in_progress", "note": ""}],
        "attempts": 0,
        "max_attempts": 3,
    }

    result = verifier_node(state)

    assert result["passed"] is True
    assert result["attempts"] == 1
    assert result["todos"][0]["status"] == "completed"
    assert result["verification_checks"][0]["name"] == "html"
    assert verifier_route({**state, **result}) == "final"


def test_model_verifier_invalid_json_fails_and_routes_back(monkeypatch, tmp_path: Path) -> None:
    class FakeBoundModel:
        def invoke(self, messages):
            return AIMessage(content="not json")

    class FakeModel:
        def bind_tools(self, tools):
            return FakeBoundModel()

    monkeypatch.setattr("mokioclaw.graph.nodes.create_model", lambda: FakeModel())
    state = {
        "runtime": RuntimeState(workspace=tmp_path),
        "task": "demo",
        "attempts": 0,
        "max_attempts": 3,
    }

    result = verifier_node(state)

    assert result["passed"] is False
    assert "valid JSON" in result["last_error"]
    assert verifier_route({**state, **result}) == "planner"


def test_verifier_routes_to_final_at_max_attempts() -> None:
    assert verifier_route({"passed": False, "attempts": 3, "max_attempts": 3}) == "final"


def test_final_node_reports_multiagent_status() -> None:
    result = final_node(
        {
            "passed": True,
            "plan_summary": "demo plan",
            "todos": [{"content": "write page", "status": "completed"}],
            "verification_checks": [{"name": "html", "passed": True, "detail": "ok"}],
            "sources": [{"title": "source", "url": "https://example.com"}],
            "code_agent_summary": "done",
            "verifier_summary": "looks good",
        }
    )

    assert "PASSED" in result["final_answer"]
    assert "demo plan" in result["final_answer"]
    assert "https://example.com" in result["final_answer"]


def test_workflow_compiles_without_fixed_actor_node() -> None:
    workflow = build_workflow()

    assert workflow is not None


def test_context_token_limit_defaults_and_env(monkeypatch) -> None:
    monkeypatch.delenv("MOKIO_CONTEXT_TOKEN_LIMIT", raising=False)
    assert get_context_token_limit() == 400000

    monkeypatch.setenv("MOKIO_CONTEXT_TOKEN_LIMIT", "1234")
    assert get_context_token_limit() == 1234


def test_estimate_context_tokens_uses_model_counter(monkeypatch, tmp_path: Path) -> None:
    class FakeModel:
        def get_num_tokens_from_messages(self, messages):
            return 42 + len(messages)

    monkeypatch.setattr("mokioclaw.graph.nodes.create_model", lambda: FakeModel())
    result = estimate_context_tokens(
        {
            "runtime": RuntimeState(workspace=tmp_path),
            "task": "demo",
            "messages": [HumanMessage(content="hello")],
        }
    )

    assert result == 44


def test_context_monitor_does_not_compress_below_limit(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MOKIO_CONTEXT_TOKEN_LIMIT", "100")
    monkeypatch.setattr("mokioclaw.graph.nodes.estimate_context_tokens", lambda state: 10)
    result = context_monitor_node(
        {
            "runtime": RuntimeState(workspace=tmp_path),
            "task": "demo",
            "context_next_node": "verifier",
        }
    )

    assert result["context_should_compress"] is False
    assert result["context_next_node"] == "verifier"
    assert context_monitor_route(result) == "verifier"


def test_context_monitor_compresses_at_limit(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MOKIO_CONTEXT_TOKEN_LIMIT", "100")
    monkeypatch.setattr("mokioclaw.graph.nodes.estimate_context_tokens", lambda state: 100)
    result = context_monitor_node(
        {
            "runtime": RuntimeState(workspace=tmp_path),
            "task": "demo",
            "context_next_node": "planner",
        }
    )

    assert result["context_should_compress"] is True
    assert context_monitor_route(result) == "context_compressor"


def test_context_compressor_removes_old_messages_and_preserves_state(monkeypatch, tmp_path: Path) -> None:
    calls = {"count": 0}

    def fake_estimate(state):
        calls["count"] += 1
        return 1000 if calls["count"] == 1 else 50

    monkeypatch.setattr("mokioclaw.graph.nodes.estimate_context_tokens", fake_estimate)
    monkeypatch.setattr(
        "mokioclaw.graph.nodes._compress_context_with_model",
        lambda state: {
            "summary": "compressed summary",
            "active_goal": "finish demo",
            "completed_work": "wrote file",
            "open_todos": ["verify"],
            "important_files": ["demo.py"],
            "tool_findings": "ok",
            "sources": [],
            "next_steps": "verify",
            "risks": "",
        },
    )
    state = {
        "runtime": RuntimeState(workspace=tmp_path),
        "task": "demo",
        "messages": [HumanMessage(content="old " * 200)],
        "plan_summary": "plan",
        "todos": [{"id": "todo-1", "content": "verify", "status": "pending", "note": ""}],
        "acceptance_criteria": ["done"],
        "verification_commands": ["python --version"],
        "research_notes": "research " * 100,
        "context_next_node": "verifier",
    }

    result = context_compressor_node(state)

    assert isinstance(result["messages"][0], RemoveMessage)
    assert result["messages"][0].id == REMOVE_ALL_MESSAGES
    assert "compressed summary" in result["context_summary"]
    assert result["compression_events"][0]["before_tokens"] == 1000
    assert result["compression_events"][0]["after_tokens"] == 50
    assert result["compression_events"][0]["removed_messages"] == 1
    assert result["todos"][0]["content"] == "verify" if "todos" in result else state["todos"][0]["content"] == "verify"
    merged = add_messages(state["messages"], result["messages"])
    assert len(merged) == 1
    assert "compressed summary" in merged[0].content
    assert context_compressor_route({**state, **result}) == "verifier"


def test_amiya_planner_uses_fixed_verifier_commands(monkeypatch, tmp_path: Path) -> None:
    class FakeBoundModel:
        def invoke(self, messages):
            return AIMessage(content="plan ready")

    class FakeModel:
        def bind_tools(self, tools):
            return FakeBoundModel()

    monkeypatch.setattr("mokioclaw.graph.nodes.create_model", lambda: FakeModel())
    result = planner_node(
        {
            "task": "帮我查阅明日方舟阿米娅，并编写一个 HTML 介绍人物",
            "runtime": RuntimeState(workspace=tmp_path),
            "attempts": 0,
            "max_attempts": 3,
        }
    )

    assert result["verification_commands"] == AMIYA_COMMANDS
    assert result["todos"][0]["id"] == "todo-1"
    assert result["todos"][0]["status"] == "pending"


def test_call_search_agent_tool_updates_state(monkeypatch, tmp_path: Path) -> None:
    def fake_search_agent(state, instruction, *, writer=None, max_loops=4):
        return {
            "summary": "Amiya is a key Arknights character.",
            "sources": [{"title": "Amiya", "url": "https://example.com/amiya"}],
            "queries": ["Amiya Arknights"],
        }

    monkeypatch.setattr("mokioclaw.graph.nodes.run_search_agent", fake_search_agent)
    state = {"task": "阿米娅", "runtime": RuntimeState(workspace=tmp_path)}

    result = _call_search_agent_tool(state, lambda event: None, "research Amiya")

    assert result["ok"] is True
    assert "Amiya" in state["research_notes"]
    assert state["sources"][0]["url"] == "https://example.com/amiya"
    assert state["agent_handoffs"][0]["to_agent"] == "searchAgent"


def test_call_code_agent_tool_updates_state(monkeypatch, tmp_path: Path) -> None:
    def fake_code_agent(state, instruction, *, writer=None, max_loops=10):
        return {
            "summary": "Created amiya_profile.html",
            "todos": [{"id": "todo-1", "content": "write", "status": "completed", "note": ""}],
        }

    monkeypatch.setattr("mokioclaw.graph.nodes.run_code_agent", fake_code_agent)
    state = {
        "task": "阿米娅",
        "runtime": RuntimeState(workspace=tmp_path),
        "todos": [{"id": "todo-1", "content": "write", "status": "pending", "note": ""}],
    }

    result = _call_code_agent_tool(state, lambda event: None, "write page")

    assert result["ok"] is True
    assert state["code_agent_summary"] == "Created amiya_profile.html"
    assert state["todos"][0]["status"] == "completed"
    assert state["agent_handoffs"][0]["to_agent"] == "codeAgent"
