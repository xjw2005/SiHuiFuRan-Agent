from __future__ import annotations

from mokioclaw.cli.formatter import render_context_compression, render_context_monitor, render_plan, render_sources, render_verifier


def test_render_plan_handles_todo_table(capsys) -> None:
    render_plan(
        {
            "plan_summary": "demo plan",
            "todos": [
                {"id": "todo-1", "content": "write tests", "status": "completed", "note": "done"},
                {"id": "todo-2", "content": "implement", "status": "in_progress", "note": ""},
            ],
            "verification_commands": ["python -m pytest -q"],
        },
        title="Test Plan",
    )

    output = capsys.readouterr().out
    assert "demo plan" in output
    assert "todo-1" in output
    assert "python -m pytest -q" in output


def test_render_sources_handles_source_table(capsys) -> None:
    render_sources(
        [{"title": "Amiya", "url": "https://example.com/amiya", "content": "Arknights character"}],
        title="searchAgent",
        answer="Amiya summary",
    )

    output = capsys.readouterr().out
    assert "Amiya summary" in output
    assert "https://example.com/amiya" in output


def test_render_verifier_handles_model_checks(capsys) -> None:
    render_verifier(
        {
            "passed": True,
            "attempts": 1,
            "verifier_summary": "looks good",
            "verification_checks": [{"name": "html", "passed": True, "detail": "file exists"}],
        }
    )

    output = capsys.readouterr().out
    assert "looks good" in output
    assert "html" in output


def test_render_context_monitor(capsys) -> None:
    render_context_monitor(
        {
            "context_token_count": 120,
            "context_token_limit": 100,
            "context_should_compress": True,
            "context_next_node": "verifier",
        }
    )

    output = capsys.readouterr().out
    assert "120" in output
    assert "verifier" in output


def test_render_context_compression(capsys) -> None:
    render_context_compression(
        {
            "compression_events": [
                {
                    "before_tokens": 1000,
                    "after_tokens": 80,
                    "removed_messages": 12,
                    "next_node": "planner",
                    "summary": "compressed",
                }
            ]
        }
    )

    output = capsys.readouterr().out
    assert "1000" in output
    assert "compressed" in output
