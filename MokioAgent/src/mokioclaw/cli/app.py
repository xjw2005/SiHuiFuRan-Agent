from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Literal

import typer
from rich import box
from rich.panel import Panel
from typer.core import TyperGroup

from mokioclaw.cli.formatter import print_event, safe_echo, safe_secho
from mokioclaw.core.approval import ApprovalDecision, ApprovalRequest
from mokioclaw.core.agent import stream_agent_events


class MokioClawGroup(TyperGroup):
    """Let ``mokioclaw "task"`` coexist with real subcommands."""

    def parse_args(self, ctx, args):  # type: ignore[no-untyped-def]
        commands = set(self.commands)
        remaining: list[str] = []
        task_parts: list[str] = []
        index = 0
        while index < len(args):
            arg = args[index]
            if arg in commands or arg == "--help":
                remaining.extend(args[index:])
                break
            if arg.startswith("-"):
                remaining.append(arg)
                if "=" not in arg and index + 1 < len(args) and not args[index + 1].startswith("-"):
                    remaining.append(args[index + 1])
                    index += 2
                    continue
                index += 1
                continue
            task_parts.extend(args[index:])
            break
        if task_parts:
            ctx.obj = dict(ctx.obj or {})
            ctx.obj["task_arg"] = " ".join(task_parts)
        return super().parse_args(ctx, remaining)


app = typer.Typer(
    cls=MokioClawGroup,
    help='mokioclaw: a teaching-first mini CodeAgent. Use `mokioclaw "task"` for Rich output or `mokioclaw tui` for Textual TUI.',
)


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


# @app.callback 表示这是 Typer 的"默认回调函数"
# invoke_without_command=True 意思是：即使用户没有输入子命令（比如只输入 mokioclaw "xxx"），也执行这个函数
@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,  # Typer 提供的上下文对象，用来获取命令行解析的额外信息

    # --workspace / -w：指定工作目录（Agent 生成的文件会放这里）
    # 如果不指定，会自动创建一个带时间戳的新目录：.mokioclaw/workspaces/workspace-YYYYMMDD-HHMMSS-xxxxxx
    workspace: Annotated[
        Path | None,
        typer.Option("--workspace", "-w", help="Workspace for generated files. Defaults to a fresh .mokioclaw/workspaces/workspace-* directory."),
    ] = None,

    # --max-attempts：最大尝试次数，planner/verifier 循环最多跑几轮就强制结束，默认3次
    max_attempts: Annotated[
        int,
        typer.Option("--max-attempts", help="Maximum planner/actor/verifier attempts before finalizing."),
    ] = 3,

    # --approval-mode：危险命令的人工审批模式
    #   inline = 执行前在终端询问用户是否同意（默认）
    #   auto   = 自动批准所有命令（无需确认）
    #   deny   = 自动拒绝所有危险命令
    approval_mode: Annotated[
        Literal["inline", "auto", "deny"],
        typer.Option("--approval-mode", help="Human approval mode for high-risk BashTool commands: inline, auto, or deny."),
    ] = "inline",

    # --checkpoint-mode：断点保存模式
    #   light  = 只保存摘要信息，恢复快但不完整（默认）
    #   strict = 保存完整状态，可精确恢复但占空间
    #   off    = 不保存，中断即丢失
    checkpoint_mode: Annotated[
        Literal["light", "strict", "off"],
        typer.Option("--checkpoint-mode", help="Checkpoint mode: light, strict, or off."),
    ] = "light",

    # --trace-mode：是否开启追踪日志（记录每个节点/工具的执行过程）
    trace_mode: Annotated[
        Literal["on", "off"],
        typer.Option("--trace-mode", help="Trace logging mode: on or off."),
    ] = "on",

    # --resume：从之前中断的 workspace 目录恢复，传入路径即可续跑
    resume: Annotated[
        Path | None,
        typer.Option("--resume", help="Resume from an existing MokioClaw workspace."),
    ] = None,
) -> None:
    # 如果用户调用了子命令（比如 mokioclaw tui），这里直接返回，交给子命令处理
    if ctx.invoked_subcommand is not None:
        return

    # 配置终端为 UTF-8 编码，防止中文乱码
    configure_console()

    # 先把 task 设为 None，后面尝试从上下文中取出用户输入的任务文本
    task = None
    # MokioClawGroup.parse_args() 会把 "mokioclaw 后面紧跟的文本" 放到 ctx.obj["task_arg"] 里
    if isinstance(ctx.obj, dict):
        task = ctx.obj.get("task_arg")

    # 如果既没有任务文本，也没有 --resume 恢复路径，说明用户啥也没输入
    # 那就打印帮助信息然后退出
    if not task and resume is None:
        safe_echo(ctx.get_help())
        raise typer.Exit()

    # 打印一行启动横幅（紫色文字），告知当前是 stage 5 版本
    safe_secho("mokioclaw stage 5: MultiAgent + context/harness engineering", fg=typer.colors.MAGENTA)

    # 如果审批模式是 inline，就用 _inline_approval_handler（终端里问 Y/N）
    # 否则设为 None（auto/deny 模式不需要交互）
    approval_handler = _inline_approval_handler if approval_mode == "inline" else None

    # 调用 stream_agent_events() 启动 Agent 主循环
    # 这是一个生成器（generator），会持续产出事件（event）
    # 每个 event 代表 Agent 执行过程中的一个步骤（比如开始规划、调用工具、得到结果等）
    for event in stream_agent_events(
        task,                    # 用户的任务描述
        workspace=workspace,     # 工作目录
        max_attempts=max_attempts,  # 最大尝试轮次
        approval_mode=approval_mode,  # 审批模式
        approval_handler=approval_handler,  # 审批回调函数（inline 时用）
        checkpoint_mode=checkpoint_mode,    # 断点模式
        resume_workspace=resume,  # 恢复路径
        trace_mode=trace_mode,    # 追踪日志开关
    ):
        # 每个事件用 print_event() 漂亮地打印到终端（带颜色、面板、图标等）
        print_event(event)


# @app.command("tui") 注册一个子命令：mokioclaw tui
# 这是一个交互式的 Textual 图形界面（TUI = Terminal UI）
@app.command("tui")
def tui(
    # 可以直接在启动 TUI 时带任务，比如 mokioclaw tui "帮我创建一个项目"
    task: Annotated[str | None, typer.Argument(help="Optional initial task for the Textual TUI.")] = None,

    # --workspace / -w：和 main 函数一样，指定工作目录
    workspace: Annotated[
        Path | None,
        typer.Option("--workspace", "-w", help="Workspace for the persistent TUI coding session."),
    ] = None,

    # --max-attempts：最大尝试次数
    max_attempts: Annotated[
        int,
        typer.Option("--max-attempts", help="Maximum planner/actor/verifier attempts before finalizing."),
    ] = 3,

    # --approval-mode：审批模式
    approval_mode: Annotated[
        Literal["inline", "auto", "deny"],
        typer.Option("--approval-mode", help="Human approval mode for high-risk BashTool commands: inline, auto, or deny."),
    ] = "inline",

    # --checkpoint-mode：断点模式
    checkpoint_mode: Annotated[
        Literal["light", "strict", "off"],
        typer.Option("--checkpoint-mode", help="Checkpoint mode: light, strict, or off."),
    ] = "light",

    # --trace-mode：追踪模式
    trace_mode: Annotated[
        Literal["on", "off"],
        typer.Option("--trace-mode", help="Trace logging mode: on or off."),
    ] = "on",

    # --resume：恢复路径
    resume: Annotated[
        Path | None,
        typer.Option("--resume", help="Resume from an existing MokioClaw workspace."),
    ] = None,
) -> None:
    """Open the Textual terminal interface."""  # 函数文档字符串，会显示在 --help 里

    # 同样先配置终端编码防止乱码
    configure_console()

    # 这里用了延迟导入（在函数内部 import）
    # 好处：只有用户真的输入 mokioclaw tui 时才加载 TUI 相关代码，启动更快
    from mokioclaw.cli.tui import MokioClawTuiApp

    # 创建 TUI 应用实例，把所有配置传进去
    MokioClawTuiApp(
        initial_task=task,          # 初始任务（如果有的话）
        workspace=workspace,        # 工作目录
        max_attempts=max_attempts,  # 最大尝试次数
        approval_mode=approval_mode,  # 审批模式
        checkpoint_mode=checkpoint_mode,  # 断点模式
        trace_mode=trace_mode,      # 追踪模式
        resume=resume,              # 恢复路径
    ).run()  # 启动 TUI 界面（会阻塞，直到用户退出）


# _inline_approval_handler：inline 模式下的审批回调函数
# 当 Agent 要执行危险命令时，会调用这个函数弹出确认面板问用户同不同意
# 下划线开头表示这是"内部函数"，不对外导出
def _inline_approval_handler(request: ApprovalRequest) -> ApprovalDecision:
    # 从 formatter 模块导入 console 对象（Rich 的 Console，用来打印漂亮的面板）
    from mokioclaw.cli.formatter import console

    # 用 Rich 的 Panel 组件打印一个黄色边框的确认面板
    console.print(
        Panel(
            # 面板内容：上面显示命令，下面显示风险原因
            f"Command:\n{request.command}\n\nRisk:\n{request.risk_reason}",
            title=f"Human Approval · {request.tool_name}",  # 面板标题：显示是哪个工具请求审批
            border_style="yellow",  # 边框用黄色（提醒注意）
            box=box.ROUNDED,        # 圆角边框样式
        )
    )

    # 在终端弹出交互式输入，问用户是否批准
    # default="n" 表示默认选 No（不批准）
    # show_default=False 表示不显示默认值提示
    # .strip().lower() 把用户输入去空格并转小写，方便判断
    answer = typer.prompt("Approve? [y/N]", default="n", show_default=False).strip().lower()

    # 打印一个空行，让输出更美观
    console.print()

    # 判断用户是否输入了 y 或 yes
    approved = answer in {"y", "yes"}

    # 返回审批结果对象
    # 如果批准了，reason 留空
    # 如果拒绝了，reason 写 "Rejected by human operator."
    return ApprovalDecision(approved=approved, reason="" if approved else "Rejected by human operator.")
