from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Literal

import typer
from rich import box
from rich.panel import Panel

from mokioclaw.cli.formatter import print_event, safe_echo, safe_secho
from mokioclaw.core.approval import ApprovalDecision, ApprovalRequest
from mokioclaw.core.agent import stream_agent_events

app = typer.Typer(help="mokioclaw: a teaching-first mini CodeAgent.")


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    task: Annotated[str | None, typer.Argument(help="Natural-language task for the CodeAgent.")] = None,
    workspace: Annotated[
        Path | None,
        typer.Option("--workspace", "-w", help="Workspace for generated files. Defaults to a fresh .mokioclaw/workspaces/workspace-* directory."),
    ] = None,
    max_attempts: Annotated[
        int,
        typer.Option("--max-attempts", help="Maximum planner/actor/verifier attempts before finalizing."),
    ] = 3,
    approval_mode: Annotated[
        Literal["inline", "auto", "deny"],
        typer.Option("--approval-mode", help="Human approval mode for high-risk BashTool commands: inline, auto, or deny."),
    ] = "inline",
    checkpoint_mode: Annotated[
        Literal["light", "strict", "off"],
        typer.Option("--checkpoint-mode", help="Checkpoint mode: light, strict, or off."),
    ] = "light",
    trace_mode: Annotated[
        Literal["on", "off"],
        typer.Option("--trace-mode", help="Trace logging mode: on or off."),
    ] = "on",
    resume: Annotated[
        Path | None,
        typer.Option("--resume", help="Resume from an existing MokioClaw workspace."),
    ] = None,
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    configure_console()
    if not task and resume is None:
        safe_echo(ctx.get_help())
        raise typer.Exit()

    safe_secho("mokioclaw stage 5: MultiAgent + context/harness engineering", fg=typer.colors.MAGENTA)
    approval_handler = _inline_approval_handler if approval_mode == "inline" else None
    for event in stream_agent_events(
        task,
        workspace=workspace,
        max_attempts=max_attempts,
        approval_mode=approval_mode,
        approval_handler=approval_handler,
        checkpoint_mode=checkpoint_mode,
        resume_workspace=resume,
        trace_mode=trace_mode,
    ):
        print_event(event)


def _inline_approval_handler(request: ApprovalRequest) -> ApprovalDecision:
    from mokioclaw.cli.formatter import console

    console.print(
        Panel(
            f"Command:\n{request.command}\n\nRisk:\n{request.risk_reason}",
            title=f"Human Approval · {request.tool_name}",
            border_style="yellow",
            box=box.ROUNDED,
        )
    )
    answer = typer.prompt("Approve? [y/N]", default="n", show_default=False).strip().lower()
    console.print()
    approved = answer in {"y", "yes"}
    return ApprovalDecision(approved=approved, reason="" if approved else "Rejected by human operator.")
