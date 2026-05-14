from __future__ import annotations

from mokioclaw.cli.formatter import render_plan


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
