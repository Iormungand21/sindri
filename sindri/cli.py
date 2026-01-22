"""Sindri CLI - forge code with local LLMs."""

import asyncio
import logging
import click
from rich.console import Console
from rich.panel import Panel
import structlog

from sindri.core.loop import AgentLoop, LoopConfig
from sindri.llm.client import OllamaClient
from sindri.tools.registry import ToolRegistry
from sindri.persistence.state import SessionState

# Configure structlog
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

console = Console()


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Sindri - Local LLM Orchestration"""
    pass


@cli.command()
@click.argument("task")
@click.option("--model", "-m", default="qwen2.5-coder:14b", help="Ollama model to use")
@click.option("--max-iter", default=50, help="Maximum iterations")
@click.option(
    "--work-dir", "-w", type=click.Path(), help="Working directory for file operations"
)
def run(task: str, model: str, max_iter: int, work_dir: str = None):
    """Run a task with Sindri."""

    from pathlib import Path

    console.print(Panel(f"[bold blue]Task:[/] {task}", title="Sindri"))
    if work_dir:
        console.print(f"[dim]Working directory: {work_dir}[/dim]")

    async def execute():
        client = OllamaClient()
        work_path = Path(work_dir).resolve() if work_dir else None
        tools = ToolRegistry.default(work_dir=work_path)
        state = SessionState()
        config = LoopConfig(max_iterations=max_iter)

        loop = AgentLoop(client, tools, state, config)

        with console.status("[bold green]Forging..."):
            result = await loop.run(task, model)

        if result.success:
            console.print(f"[green]✓ Completed in {result.iterations} iterations[/]")
            console.print(f"\n[dim]{result.final_output}[/]")
        else:
            console.print(
                f"[red]✗ {result.reason} after {result.iterations} iterations[/]"
            )

        return result

    asyncio.run(execute())


@cli.command()
@click.argument("task")
@click.option("--max-iter", default=30, help="Maximum iterations per agent")
@click.option("--vram-gb", default=16.0, help="Total VRAM in GB")
@click.option("--no-memory", is_flag=True, help="Disable memory system")
@click.option(
    "--work-dir", "-w", type=click.Path(), help="Working directory for file operations"
)
def orchestrate(
    task: str, max_iter: int, vram_gb: float, no_memory: bool, work_dir: str = None
):
    """Run a task with hierarchical agents (Brokkr → Huginn/Mimir/Ratatoskr)."""

    from pathlib import Path

    console.print(Panel(f"[bold blue]Task:[/] {task}", title="🔨 Sindri Orchestration"))
    if work_dir:
        console.print(f"[dim]Working directory: {work_dir}[/dim]")

    async def execute():
        from sindri.core.orchestrator import Orchestrator
        from sindri.core.loop import LoopConfig

        config = LoopConfig(max_iterations=max_iter)
        work_path = Path(work_dir).resolve() if work_dir else None
        enable_memory = not no_memory

        # Show memory status
        if enable_memory:
            console.print("[dim]📚 Memory system enabled[/dim]")

        orchestrator = Orchestrator(
            config=config,
            total_vram_gb=vram_gb,
            enable_memory=enable_memory,
            work_dir=work_path,
        )

        with console.status("[bold green]Orchestrating..."):
            result = await orchestrator.run(task)

        if result["success"]:
            console.print("[green]✓ Completed successfully[/]")
            console.print(f"Task ID: {result['task_id']}")
            console.print(f"Subtasks: {result.get('subtasks', 0)}")
            if result.get("result"):
                console.print(f"\n[dim]{result['result']}[/]")
        else:
            console.print(f"[red]✗ Failed: {result.get('error', 'Unknown error')}[/]")
            console.print(f"Status: {result.get('status', 'unknown')}")

        return result

    asyncio.run(execute())


@cli.command()
@click.argument("session_id")
@click.option("--max-iter", default=30, help="Maximum iterations per agent")
@click.option("--vram-gb", default=16.0, help="Total VRAM in GB")
def resume(session_id: str, max_iter: int, vram_gb: float):
    """Resume an interrupted session."""

    async def execute_resume():
        from sindri.core.orchestrator import Orchestrator
        from sindri.core.tasks import Task
        from sindri.core.loop import LoopConfig
        from sindri.persistence.state import SessionState

        # Load the session to verify it exists
        state = SessionState()

        # If session_id is short (8 chars), search for matching full ID
        full_session_id = session_id
        if len(session_id) == 8:
            # Search for sessions starting with this prefix
            all_sessions = await state.list_sessions(limit=100)
            matching = [s for s in all_sessions if s["id"].startswith(session_id)]

            if not matching:
                console.print(f"[red]✗ No session found starting with {session_id}[/]")
                console.print(
                    "[dim]Use 'sindri sessions' to list available sessions[/dim]"
                )
                return
            elif len(matching) > 1:
                console.print(f"[yellow]⚠ Multiple sessions match {session_id}:[/]")
                for m in matching:
                    console.print(f"  • {m['id'][:8]} - {m['task'][:50]}")
                console.print("[dim]Use the full session ID to be specific[/dim]")
                return

            full_session_id = matching[0]["id"]
            console.print(f"[dim]Using session: {full_session_id}[/dim]")

        session = await state.load_session(full_session_id)

        if not session:
            console.print(f"[red]✗ Session {full_session_id} not found[/]")
            console.print("[dim]Use 'sindri sessions' to list available sessions[/dim]")
            return

        console.print(
            Panel(
                f"[bold blue]Session:[/] {full_session_id[:8]}\n"
                f"[dim]Task:[/] {session.task[:60]}...\n"
                f"[dim]Model:[/] {session.model}\n"
                f"[dim]Iterations:[/] {session.iterations}",
                title="🔨 Resuming Sindri Session",
            )
        )

        # Create orchestrator
        config = LoopConfig(max_iterations=max_iter)
        orchestrator = Orchestrator(
            config=config, total_vram_gb=vram_gb, enable_memory=True
        )

        # Create a task with the existing session_id to resume
        resume_task = Task(
            description=session.task,
            assigned_agent="brokkr",
            session_id=full_session_id,
            priority=0,
        )

        # Add to scheduler and execute
        orchestrator.scheduler.add_task(resume_task)

        with console.status("[bold green]Resuming..."):
            # Execute task queue (same as orchestrate)
            while orchestrator.scheduler.has_work():
                next_task = orchestrator.scheduler.get_next_task()

                if next_task is None:
                    await asyncio.sleep(0.5)
                    continue

                result = await orchestrator.loop.run_task(next_task)

                if result.success:
                    console.print("[green]✓ Task completed[/]")
                else:
                    console.print(f"[red]✗ Task failed: {result.reason}[/]")
                    break

        # Show final status
        if resume_task.status.value == "complete":
            console.print(
                f"\n[green]✓ Session {full_session_id[:8]} completed successfully[/]"
            )
            if resume_task.result:
                console.print(f"\n[dim]{resume_task.result}[/]")
        else:
            console.print(
                f"\n[yellow]Session {full_session_id[:8]} status: {resume_task.status.value}[/]"
            )

    asyncio.run(execute_resume())


@cli.command()
def agents():
    """List all available agents."""
    from sindri.agents.registry import AGENTS
    from rich.table import Table

    table = Table(
        title="🔨 Sindri Agents", show_header=True, header_style="bold magenta"
    )
    table.add_column("Agent", style="cyan", width=12)
    table.add_column("Role", style="white", width=35)
    table.add_column("Model", style="yellow", width=25)
    table.add_column("VRAM", justify="right", style="green", width=8)
    table.add_column("Can Delegate", justify="center", style="blue", width=12)

    for name, agent in AGENTS.items():
        delegates = "✓" if agent.can_delegate else "✗"
        table.add_row(
            name,
            agent.role,
            agent.model,
            f"{agent.estimated_vram_gb:.1f} GB",
            delegates,
        )

    console.print(table)
    console.print(f"\n[dim]Total agents: {len(AGENTS)}[/dim]")


@cli.command()
@click.option("--cleanup", is_flag=True, help="Mark stale active sessions as failed")
@click.option(
    "--max-age",
    default=1.0,
    help="Max age in hours before session is stale (default: 1.0)",
)
def sessions(cleanup: bool = False, max_age: float = 1.0):
    """List recent sessions.

    Use --cleanup to mark stale sessions (active but old) as failed.
    """

    async def show_sessions():
        state = SessionState()

        if cleanup:
            # Cleanup stale sessions
            cleaned = await state.cleanup_stale_sessions(max_age_hours=max_age)
            if cleaned > 0:
                console.print(
                    f"[green]✓ Marked {cleaned} stale session(s) as failed[/]"
                )
            else:
                console.print("[dim]No stale sessions to clean up[/dim]")
            console.print()

        sessions = await state.list_sessions(limit=20)

        if not sessions:
            console.print("[yellow]No sessions found[/]")
            return

        console.print("[bold]Recent sessions:[/]\n")
        for session in sessions:
            status = session["status"]
            if status == "completed":
                status_color = "green"
                status_icon = "✓"
            elif status == "failed":
                status_color = "red"
                status_icon = "✗"
            elif status == "active":
                status_color = "blue"
                status_icon = "●"
            else:
                status_color = "yellow"
                status_icon = "○"

            console.print(
                f"[{status_color}]{status_icon}[/] {session['id'][:8]} - {session['task'][:50]}"
            )
            console.print(
                f"   Model: {session['model']} | Iterations: {session['iterations']} | {session['created_at']}"
            )
            console.print()

        # Show cleanup hint if there are active sessions
        active_count = sum(1 for s in sessions if s["status"] == "active")
        if active_count > 0 and not cleanup:
            console.print(
                f"[dim]Found {active_count} active session(s). Use --cleanup to mark stale ones as failed.[/dim]"
            )

    asyncio.run(show_sessions())


@cli.command()
@click.argument("session_id", required=False)
@click.option(
    "--aggregate",
    "-a",
    is_flag=True,
    help="Show aggregate statistics across all sessions",
)
@click.option("--tools", "-t", is_flag=True, help="Show tool breakdown")
@click.option("--limit", "-l", default=10, help="Number of sessions to list")
def metrics(
    session_id: str = None,
    aggregate: bool = False,
    tools: bool = False,
    limit: int = 10,
):
    """View performance metrics for sessions.

    Without arguments, lists recent sessions with their metrics.
    With SESSION_ID, shows detailed metrics for that session.

    Examples:

        sindri metrics                  # List recent sessions

        sindri metrics abc12345         # Detailed metrics for session

        sindri metrics -a               # Aggregate stats

        sindri metrics abc12345 -t      # Show tool breakdown
    """
    from rich.table import Table
    from sindri.persistence.metrics import MetricsStore

    async def show_metrics():
        store = MetricsStore()

        if aggregate:
            # Show aggregate statistics
            stats = await store.get_aggregate_stats()

            console.print("[bold]📊 Aggregate Metrics[/]\n")

            if stats["total_sessions"] == 0:
                console.print("[yellow]No metrics recorded yet[/]")
                console.print("[dim]Run some tasks to collect metrics[/dim]")
                return

            table = Table(show_header=False, box=None)
            table.add_column("Stat", style="dim")
            table.add_column("Value", style="bold")

            # Format duration
            total_secs = stats["total_duration_seconds"]
            if total_secs > 3600:
                duration_str = f"{total_secs / 3600:.1f} hours"
            elif total_secs > 60:
                duration_str = f"{total_secs / 60:.1f} minutes"
            else:
                duration_str = f"{total_secs:.1f} seconds"

            avg_secs = stats["avg_duration_seconds"]
            if avg_secs > 60:
                avg_str = f"{avg_secs / 60:.1f} min"
            else:
                avg_str = f"{avg_secs:.1f}s"

            table.add_row("Total Sessions", str(stats["total_sessions"]))
            table.add_row("Total Time", duration_str)
            table.add_row("Avg Session", avg_str)
            table.add_row("Total Iterations", str(stats["total_iterations"]))
            table.add_row("Avg Iterations", f"{stats['avg_iterations']:.1f}")
            table.add_row("Total Tool Calls", str(stats["total_tool_executions"]))

            console.print(table)
            return

        if session_id:
            # Show detailed metrics for a specific session
            # Resolve short session ID
            full_session_id = session_id
            if len(session_id) < 36:
                all_sessions = await store.list_metrics(limit=100)
                matching = [
                    s for s in all_sessions if s["session_id"].startswith(session_id)
                ]

                if not matching:
                    console.print(
                        f"[red]✗ No metrics found for session {session_id}[/]"
                    )
                    console.print(
                        "[dim]Use 'sindri metrics' to list sessions with metrics[/dim]"
                    )
                    return
                elif len(matching) > 1:
                    console.print(f"[yellow]⚠ Multiple sessions match {session_id}:[/]")
                    for m in matching:
                        console.print(f"  • {m['session_id'][:8]} - {m['task'][:50]}")
                    return

                full_session_id = matching[0]["session_id"]

            # Load full metrics
            metrics = await store.load_metrics(full_session_id)

            if not metrics:
                console.print(f"[red]✗ No metrics found for {full_session_id}[/]")
                return

            # Show summary
            summary = metrics.get_summary()
            console.print(f"[bold]📊 Metrics: {full_session_id[:8]}[/]\n")
            console.print(f"[dim]Task:[/] {metrics.task_description[:80]}")
            console.print(f"[dim]Model:[/] {metrics.model_name}")
            console.print(f"[dim]Status:[/] {metrics.status}")
            console.print()

            # Time breakdown
            console.print("[bold]⏱ Time Breakdown:[/]")
            time_table = Table(show_header=False, box=None)
            time_table.add_column("Category", style="dim")
            time_table.add_column("Time", style="bold")

            time_table.add_row("Total Duration", summary["duration_formatted"])
            time_table.add_row(
                "LLM Inference", f"{summary['time_breakdown']['llm_inference']:.2f}s"
            )
            time_table.add_row(
                "Tool Execution", f"{summary['time_breakdown']['tool_execution']:.2f}s"
            )
            time_table.add_row(
                "Model Loading", f"{summary['time_breakdown']['model_loading']:.2f}s"
            )

            console.print(time_table)
            console.print()

            # Iteration summary
            console.print("[bold]🔄 Iterations:[/]")
            console.print(f"  Total: {summary['total_iterations']}")
            console.print(f"  Avg Time: {summary['avg_iteration_time']:.2f}s")
            console.print()

            # Tool summary
            console.print("[bold]🔧 Tools:[/]")
            console.print(f"  Total Calls: {summary['total_tool_executions']}")

            if tools:
                # Show detailed tool breakdown
                console.print()
                breakdown = metrics.get_tool_breakdown()
                if breakdown:
                    tool_table = Table()
                    tool_table.add_column("Tool")
                    tool_table.add_column("Calls", justify="right")
                    tool_table.add_column("Total Time", justify="right")
                    tool_table.add_column("Avg Time", justify="right")
                    tool_table.add_column("Success Rate", justify="right")

                    for tool_name, data in sorted(
                        breakdown.items(), key=lambda x: x[1]["count"], reverse=True
                    ):
                        success_rate = (
                            data["successes"] / data["count"] * 100
                            if data["count"] > 0
                            else 0
                        )
                        success_color = (
                            "green"
                            if success_rate == 100
                            else ("yellow" if success_rate >= 50 else "red")
                        )
                        tool_table.add_row(
                            tool_name,
                            str(data["count"]),
                            f"{data['total_time']:.2f}s",
                            f"{data['avg_time']:.3f}s",
                            f"[{success_color}]{success_rate:.0f}%[/{success_color}]",
                        )

                    console.print(tool_table)
                else:
                    console.print("[dim]  No tools executed[/dim]")

            return

        # List recent sessions with metrics
        sessions = await store.list_metrics(limit=limit)

        if not sessions:
            console.print("[yellow]No metrics found[/]")
            console.print("[dim]Run some tasks to collect metrics[/dim]")
            return

        console.print("[bold]📊 Recent Session Metrics[/]\n")

        table = Table()
        table.add_column("Session")
        table.add_column("Task")
        table.add_column("Duration", justify="right")
        table.add_column("Iterations", justify="right")
        table.add_column("Tools", justify="right")
        table.add_column("Status")

        for s in sessions:
            # Format duration
            secs = s["duration_seconds"]
            if secs > 60:
                duration_str = f"{secs / 60:.1f}m"
            else:
                duration_str = f"{secs:.1f}s"

            status_color = "green" if s["status"] == "completed" else "yellow"
            status_short = "✓" if s["status"] == "completed" else "●"

            table.add_row(
                s["session_id"][:8],
                s["task"][:40] + "..." if len(s["task"]) > 40 else s["task"],
                duration_str,
                str(s["total_iterations"]),
                str(s["total_tool_executions"]),
                f"[{status_color}]{status_short}[/{status_color}]",
            )

        console.print(table)
        console.print("\n[dim]Use 'sindri metrics <session_id>' for details[/dim]")
        console.print("[dim]Use 'sindri metrics -a' for aggregate statistics[/dim]")

    asyncio.run(show_metrics())


@cli.command()
@click.argument("session_id")
@click.argument("output", required=False, type=click.Path())
@click.option("--no-metadata", is_flag=True, help="Exclude metadata section")
@click.option("--no-timestamps", is_flag=True, help="Exclude timestamps from turns")
def export(
    session_id: str,
    output: str = None,
    no_metadata: bool = False,
    no_timestamps: bool = False,
):
    """Export a session to Markdown.

    SESSION_ID can be the full UUID or first 8 characters.
    OUTPUT is the output file path (default: auto-generated filename).

    Examples:

        sindri export abc12345

        sindri export abc12345 my-session.md

        sindri export abc12345 --no-metadata
    """
    from pathlib import Path
    from sindri.persistence.export import MarkdownExporter, generate_export_filename

    async def do_export():
        state = SessionState()

        # Resolve short session ID
        full_session_id = session_id
        if len(session_id) < 36:
            all_sessions = await state.list_sessions(limit=100)
            matching = [s for s in all_sessions if s["id"].startswith(session_id)]

            if not matching:
                console.print(f"[red]✗ No session found starting with {session_id}[/]")
                console.print(
                    "[dim]Use 'sindri sessions' to list available sessions[/dim]"
                )
                return False
            elif len(matching) > 1:
                console.print(f"[yellow]⚠ Multiple sessions match {session_id}:[/]")
                for m in matching:
                    console.print(f"  • {m['id'][:8]} - {m['task'][:50]}")
                console.print("[dim]Use more characters to be specific[/dim]")
                return False

            full_session_id = matching[0]["id"]

        # Load the session
        session = await state.load_session(full_session_id)

        if not session:
            console.print(f"[red]✗ Session {full_session_id} not found[/]")
            return False

        # Create exporter
        exporter = MarkdownExporter(
            include_timestamps=not no_timestamps, include_metadata=not no_metadata
        )

        # Determine output path
        if output:
            output_path = Path(output)
        else:
            filename = generate_export_filename(session)
            output_path = Path.cwd() / filename

        # Export
        exporter.export_to_file(session, output_path)

        # Show success message
        console.print(f"[green]✓ Exported session to {output_path}[/]")
        console.print(f"[dim]Session: {session.task[:60]}...[/dim]")
        console.print(
            f"[dim]Turns: {len(session.turns)} | Model: {session.model}[/dim]"
        )

        return True

    asyncio.run(do_export())


@cli.command()
@click.argument("task", required=False)
@click.option("--no-memory", is_flag=True, help="Disable memory system")
@click.option(
    "--work-dir", "-w", type=click.Path(), help="Working directory for file operations"
)
def tui(task: str = None, no_memory: bool = False, work_dir: str = None):
    """Launch the interactive TUI."""

    from pathlib import Path
    from sindri.tui.app import run_tui
    from sindri.core.orchestrator import Orchestrator
    from sindri.core.events import EventBus

    try:
        # Create shared event bus for TUI and orchestrator
        event_bus = EventBus()
        work_path = Path(work_dir).resolve() if work_dir else None
        orchestrator = Orchestrator(
            enable_memory=not no_memory, event_bus=event_bus, work_dir=work_path
        )
        run_tui(task=task, orchestrator=orchestrator, event_bus=event_bus)
    except Exception as e:
        console.print(f"[red]Error launching TUI: {str(e)}[/]")
        import traceback

        traceback.print_exc()


@cli.command()
@click.option("--session-id", help="Specific session ID to recover")
def recover(session_id: str = None):
    """List and recover interrupted sessions."""

    from sindri.core.recovery import RecoveryManager
    from rich.table import Table
    from pathlib import Path

    # Setup recovery manager
    data_dir = Path.home() / ".sindri"
    recovery = RecoveryManager(str(data_dir / "state"))

    if session_id:
        # Recover specific session
        if not recovery.has_checkpoint(session_id):
            console.print(f"[red]✗ No checkpoint found for session {session_id}[/]")
            return

        console.print(f"[yellow]Recovering session {session_id}...[/]")
        state = recovery.load_checkpoint(session_id)

        if state:
            console.print("[green]✓ Checkpoint loaded[/]")
            console.print(f"Task: {state.get('task', 'Unknown')}")
            console.print(f"Iteration: {state.get('iteration', 0)}")
            console.print(f"Agent: {state.get('agent', 'Unknown')}")
            console.print("\n[yellow]Use 'sindri resume {session_id}' to continue[/]")
        else:
            console.print("[red]✗ Failed to load checkpoint[/]")
    else:
        # List all recoverable sessions
        sessions = recovery.list_recoverable_sessions()

        if not sessions:
            console.print("[yellow]No recoverable sessions found.[/]")
            return

        table = Table(title="💾 Recoverable Sessions", show_header=True)
        table.add_column("Session ID", style="cyan", width=12)
        table.add_column("Task", style="white", width=40)
        table.add_column("Saved At", style="yellow", width=20)

        for s in sessions:
            table.add_row(
                s["session_id"][:8],
                s.get("task", "Unknown")[:40],
                s.get("timestamp", "")[:19],
            )

        console.print(table)
        console.print(
            "\n[dim]Use 'sindri recover --session-id <id>' to load a checkpoint[/]"
        )
        console.print("[dim]Use 'sindri resume <id>' to continue execution[/]")


@cli.command()
@click.option("--config-path", help="Path to config file to validate")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
def doctor(config_path: str = None, verbose: bool = False):
    """Check Sindri installation and configuration."""

    from sindri.core.doctor import get_all_checks

    console.print("[bold cyan]🔨 Sindri Doctor[/bold cyan]\n")
    console.print("[dim]Checking system health...[/dim]\n")

    # Run all health checks
    results = get_all_checks(config_path)
    checks = results["checks"]

    # Display results
    check_num = 1

    # 1. Python Version
    check = checks["python"]
    _print_check(check_num, check)
    check_num += 1

    # 2. Ollama
    check = checks["ollama"]
    _print_check(check_num, check)
    check_num += 1

    # 3. Required Models
    check = checks["models"]
    _print_check(check_num, check)

    if results["models"]["missing"]:
        console.print("\n   [yellow]Missing models:[/yellow]")
        for model in sorted(results["models"]["missing"]):
            console.print(f"     • {model}")

        console.print("\n   [bold]Pull missing models:[/bold]")
        for model in sorted(results["models"]["missing"]):
            console.print(f"     ollama pull {model}")
    elif verbose and results["models"]["available"]:
        console.print("\n   [dim]Available models:[/dim]")
        for model in sorted(results["models"]["available"])[:5]:
            console.print(f"     • {model}")
        if len(results["models"]["available"]) > 5:
            console.print(
                f"     [dim]... and {len(results['models']['available']) - 5} more[/dim]"
            )

    console.print()
    check_num += 1

    # 4. GPU/VRAM
    check = checks["gpu"]
    _print_check(check_num, check)
    check_num += 1

    # 5. Configuration
    check = checks["config"]
    _print_check(check_num, check)
    check_num += 1

    # 6. Database
    check = checks["database"]
    _print_check(check_num, check)
    check_num += 1

    # 7. Dependencies
    check = checks["dependencies"]
    _print_check(check_num, check)

    if verbose:
        console.print()
        for module, description, is_optional, installed in results["dependencies"]:
            status = (
                "[green]✓[/green]"
                if installed
                else ("[yellow]⚠[/yellow]" if is_optional else "[red]✗[/red]")
            )
            optional_tag = " [dim](optional)[/dim]" if is_optional else ""
            console.print(f"     {status} {description} ({module}){optional_tag}")

    # Overall status
    console.print()
    if results["overall"]["all_passed"]:
        console.print("[bold green]✓ All checks passed - Sindri is ready![/bold green]")
    elif results["overall"]["critical_passed"]:
        console.print(
            "[bold yellow]⚠ Some optional checks failed - Sindri should work[/bold yellow]"
        )
    else:
        console.print(
            "[bold red]✗ Critical checks failed - Sindri may not work correctly[/bold red]"
        )
        console.print("[dim]Fix the issues above and run 'sindri doctor' again[/dim]")


def _print_check(num: int, check):
    """Helper to print a health check result."""

    status = "[green]✓[/green]" if check.passed else "[red]✗[/red]"
    console.print(f"[bold]{num}. {check.name}:[/] {status} {check.message}")

    if check.details:
        # Indent details
        for line in check.details.split("\n"):
            console.print(f"   [dim]{line}[/dim]")


@cli.group()
def plugins():
    """Manage Sindri plugins."""
    pass


@plugins.command("list")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
def plugins_list(verbose: bool = False):
    """List installed plugins."""
    from rich.table import Table
    from sindri.plugins import PluginManager, PluginType, PluginState

    manager = PluginManager()

    # Ensure directories exist
    manager.ensure_directories()

    # Discover plugins
    manager.discover()

    # Validate all
    from sindri.agents.registry import AGENTS
    from sindri.tools.registry import ToolRegistry

    existing_tools = set(ToolRegistry.default()._tools.keys())
    existing_agents = set(AGENTS.keys())

    manager.validate_all(existing_tools=existing_tools, existing_agents=existing_agents)

    plugins = manager.get_all_plugins()

    if not plugins:
        console.print("[yellow]No plugins found.[/yellow]")
        console.print(f"\n[dim]Plugin directory: {manager.plugin_dir}[/dim]")
        console.print(f"[dim]Agent config directory: {manager.agent_dir}[/dim]")
        console.print(
            "\n[dim]Create plugins in these directories to extend Sindri.[/dim]"
        )
        return

    # Group by type
    tools = [p for p in plugins if p.info.type == PluginType.TOOL]
    agents = [p for p in plugins if p.info.type == PluginType.AGENT]

    # Tool plugins table
    if tools:
        table = Table(
            title="🔧 Tool Plugins", show_header=True, header_style="bold cyan"
        )
        table.add_column("Name", style="cyan", width=20)
        table.add_column("Status", width=12)
        table.add_column("Description", width=40)
        if verbose:
            table.add_column("Path", style="dim", width=30)

        for p in tools:
            status_color = "green" if p.state == PluginState.VALIDATED else "red"
            status_text = p.state.name.lower()

            row = [
                p.info.name,
                f"[{status_color}]{status_text}[/{status_color}]",
                p.info.description[:40] if p.info.description else "",
            ]
            if verbose:
                row.append(str(p.info.path))

            table.add_row(*row)

        console.print(table)
        console.print()

    # Agent plugins table
    if agents:
        table = Table(
            title="🤖 Agent Plugins", show_header=True, header_style="bold magenta"
        )
        table.add_column("Name", style="magenta", width=15)
        table.add_column("Status", width=12)
        table.add_column("Model", style="yellow", width=25)
        table.add_column("Role", width=35)
        if verbose:
            table.add_column("Path", style="dim", width=30)

        for p in agents:
            status_color = "green" if p.state == PluginState.VALIDATED else "red"
            status_text = p.state.name.lower()

            model = ""
            role = ""
            if p.info.agent_config:
                model = p.info.agent_config.get("model", "")
                role = p.info.agent_config.get("role", "")

            row = [
                p.info.name,
                f"[{status_color}]{status_text}[/{status_color}]",
                model,
                role[:35] if role else "",
            ]
            if verbose:
                row.append(str(p.info.path))

            table.add_row(*row)

        console.print(table)

    # Show failed plugins
    failed = manager.get_failed_plugins()
    if failed:
        console.print("\n[bold red]Failed Plugins:[/bold red]")
        for p in failed:
            console.print(f"  ✗ {p.info.name}: {p.error}")

    # Summary
    counts = manager.get_plugin_count()
    console.print(
        f"\n[dim]Total: {len(plugins)} plugins ({counts.get('VALIDATED', 0)} validated, {counts.get('FAILED', 0)} failed)[/dim]"
    )


@plugins.command("validate")
@click.argument("path", type=click.Path(exists=True))
@click.option("--strict", is_flag=True, help="Treat warnings as errors")
def plugins_validate(path: str, strict: bool = False):
    """Validate a plugin file."""
    from pathlib import Path
    from sindri.plugins.validator import validate_plugin_file
    from sindri.agents.registry import AGENTS
    from sindri.tools.registry import ToolRegistry

    plugin_path = Path(path)
    console.print(f"[bold]Validating plugin: {plugin_path.name}[/bold]\n")

    existing_tools = set(ToolRegistry.default()._tools.keys())
    existing_agents = set(AGENTS.keys())

    result = validate_plugin_file(
        plugin_path,
        existing_tools=existing_tools,
        existing_agents=existing_agents,
        strict=strict,
    )

    # Show errors
    if result.errors:
        console.print("[bold red]Errors:[/bold red]")
        for error_type, message in result.errors:
            console.print(f"  ✗ {message}")
        console.print()

    # Show warnings
    if result.warnings:
        console.print("[bold yellow]Warnings:[/bold yellow]")
        for warning in result.warnings:
            console.print(f"  ⚠ {warning}")
        console.print()

    # Show info
    if result.info:
        console.print("[bold blue]Info:[/bold blue]")
        for info in result.info:
            console.print(f"  ℹ {info}")
        console.print()

    # Overall result
    if result.valid:
        console.print("[bold green]✓ Plugin is valid![/bold green]")
    else:
        console.print("[bold red]✗ Plugin validation failed[/bold red]")


@plugins.command("init")
@click.option("--tool", is_flag=True, help="Create a tool plugin template")
@click.option("--agent", is_flag=True, help="Create an agent config template")
@click.argument("name", required=False)
def plugins_init(tool: bool, agent: bool, name: str = None):
    """Create a plugin template."""
    from sindri.plugins import PluginManager

    manager = PluginManager()
    manager.ensure_directories()

    if not tool and not agent:
        console.print("[yellow]Specify --tool or --agent to create a template[/yellow]")
        console.print("\nExamples:")
        console.print("  sindri plugins init --tool my_tool")
        console.print("  sindri plugins init --agent my_agent")
        return

    if tool:
        plugin_name = name or "example_tool"
        plugin_path = manager.plugin_dir / f"{plugin_name}.py"

        if plugin_path.exists():
            console.print(f"[red]File already exists: {plugin_path}[/red]")
            return

        template = f'''"""Example tool plugin for Sindri.

This is a template for creating custom tools.
"""

__version__ = "0.1.0"
__author__ = "Your Name"

from sindri.tools.base import Tool, ToolResult


class {plugin_name.title().replace("_", "")}Tool(Tool):
    """A custom tool that does something useful."""

    name = "{plugin_name}"
    description = "Description of what this tool does"
    parameters = {{
        "type": "object",
        "properties": {{
            "input": {{
                "type": "string",
                "description": "The input to process"
            }}
        }},
        "required": ["input"]
    }}

    async def execute(self, input: str, **kwargs) -> ToolResult:
        """Execute the tool.

        Args:
            input: The input to process

        Returns:
            ToolResult with success status and output
        """
        try:
            # Your tool logic here
            result = f"Processed: {{input}}"

            return ToolResult(
                success=True,
                output=result
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e)
            )
'''
        plugin_path.write_text(template)
        console.print(f"[green]✓ Created tool template: {plugin_path}[/green]")
        console.print("\n[dim]Edit the file to implement your custom tool.[/dim]")

    if agent:
        agent_name = name or "example_agent"
        agent_path = manager.agent_dir / f"{agent_name}.toml"

        if agent_path.exists():
            console.print(f"[red]File already exists: {agent_path}[/red]")
            return

        template = f'''# Custom agent configuration for Sindri
# See documentation for all available options

[metadata]
version = "0.1.0"
author = "Your Name"

[agent]
name = "{agent_name}"
role = "Description of the agent's role"
model = "qwen2.5-coder:7b"
tools = ["read_file", "write_file", "shell"]
max_iterations = 30
estimated_vram_gb = 5.0
temperature = 0.3

# Optional delegation settings
can_delegate = false
delegate_to = []

# Optional fallback model
# fallback_model = "qwen2.5:3b-instruct-q8_0"
# fallback_vram_gb = 3.0

[prompt]
content = """You are {agent_name}, a specialized agent for Sindri.

Your role is to... (describe the agent's purpose and behavior)

Guidelines:
1. Be concise and focused
2. Use the available tools effectively
3. Report results clearly

When your task is complete, include <sindri:complete/> in your response.
"""
'''
        agent_path.write_text(template)
        console.print(f"[green]✓ Created agent template: {agent_path}[/green]")
        console.print("\n[dim]Edit the file to customize your agent.[/dim]")


@plugins.command("dirs")
def plugins_dirs():
    """Show plugin directories."""
    from sindri.plugins import PluginManager

    manager = PluginManager()

    console.print("[bold]Plugin Directories:[/bold]\n")
    console.print(f"  📂 Tool plugins:  {manager.plugin_dir}")
    console.print(f"  📂 Agent configs: {manager.agent_dir}")

    # Show if directories exist
    tool_exists = manager.plugin_dir.exists()
    agent_exists = manager.agent_dir.exists()

    console.print()
    if tool_exists:
        tool_count = len(list(manager.plugin_dir.glob("*.py")))
        console.print(
            f"  [green]✓[/green] Tool directory exists ({tool_count} .py files)"
        )
    else:
        console.print(
            "  [yellow]⚠[/yellow] Tool directory doesn't exist (run 'sindri plugins init' to create)"
        )

    if agent_exists:
        agent_count = len(list(manager.agent_dir.glob("*.toml")))
        console.print(
            f"  [green]✓[/green] Agent directory exists ({agent_count} .toml files)"
        )
    else:
        console.print(
            "  [yellow]⚠[/yellow] Agent directory doesn't exist (run 'sindri plugins init' to create)"
        )


# ============================================
# Plugin Marketplace Commands
# ============================================


@cli.group()
def marketplace():
    """Plugin marketplace for discovering and installing plugins."""
    pass


@marketplace.command("search")
@click.argument("query", required=False, default="")
@click.option(
    "--type",
    "-t",
    "plugin_type",
    type=click.Choice(["tool", "agent"]),
    help="Filter by type",
)
@click.option("--category", "-c", help="Filter by category")
@click.option("--tags", help="Filter by tags (comma-separated)")
@click.option("--installed", "-i", is_flag=True, help="Only show installed plugins")
def marketplace_search(
    query: str = "",
    plugin_type: str = None,
    category: str = None,
    tags: str = None,
    installed: bool = False,
):
    """Search for plugins by name, description, or tags.

    Examples:
        sindri marketplace search git
        sindri marketplace search --type tool
        sindri marketplace search --category security
        sindri marketplace search --tags "ai,code"
    """
    from rich.table import Table
    from sindri.marketplace import PluginSearcher, PluginCategory

    searcher = PluginSearcher()

    # Parse category
    cat = None
    if category:
        try:
            cat = PluginCategory(category.lower())
        except ValueError:
            console.print(f"[red]Invalid category: {category}[/red]")
            console.print(
                f"[dim]Valid categories: {', '.join(c.value for c in PluginCategory)}[/dim]"
            )
            return

    # Handle tag-based search
    if tags:
        tag_list = [t.strip() for t in tags.split(",")]
        results = searcher.search_by_tags(tag_list, installed_only=installed)
    elif query:
        results = searcher.search(
            query, plugin_type=plugin_type, category=cat, installed_only=installed
        )
    elif plugin_type:
        results = searcher.search_by_type(plugin_type, installed_only=installed)
    elif cat:
        results = searcher.search_by_category(cat, installed_only=installed)
    else:
        results = searcher.list_all(installed_only=installed)

    if not results:
        console.print("[yellow]No plugins found matching your criteria.[/yellow]")
        return

    table = Table(
        title=f"🔍 Plugin Search Results ({len(results)})",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Name", style="cyan", width=20)
    table.add_column("Type", width=8)
    table.add_column("Version", width=10)
    table.add_column("Category", width=15)
    table.add_column("Status", width=12)
    table.add_column("Description", width=35)

    for r in results:
        status = "[green]installed[/green]" if r.installed else "[dim]available[/dim]"
        plugin_type_str = "🔧 tool" if r.plugin_type == "tool" else "🤖 agent"
        desc = r.description[:32] + "..." if len(r.description) > 35 else r.description

        table.add_row(r.name, plugin_type_str, r.version, r.category, status, desc)

    console.print(table)


@marketplace.command("install")
@click.argument("source")
@click.option("--name", "-n", help="Override plugin name")
@click.option("--no-validate", is_flag=True, help="Skip validation")
@click.option("--strict", is_flag=True, help="Treat validation warnings as errors")
def marketplace_install(
    source: str,
    name: str = None,
    no_validate: bool = False,
    strict: bool = False,
):
    """Install a plugin from a local path.

    SOURCE must be a local path to a plugin file or directory.

    Examples:
        sindri marketplace install /path/to/my_tool.py
        sindri marketplace install ./plugins/my_agent.toml
        sindri marketplace install /path/to/plugin_directory/
    """
    import asyncio
    from sindri.marketplace import PluginInstaller

    installer = PluginInstaller(
        validate=not no_validate,
        strict=strict,
    )

    console.print(f"[bold]Installing plugin from: {source}[/bold]\n")

    result = asyncio.run(installer.install(source, name=name))

    if result.success:
        plugin = result.plugin
        console.print(
            f"[green]✓ Successfully installed: {plugin.metadata.name} v{plugin.metadata.version}[/green]"
        )
        console.print(f"  [dim]Type: {plugin.metadata.plugin_type}[/dim]")
        console.print(f"  [dim]Path: {plugin.installed_path}[/dim]")

        if result.warnings:
            console.print("\n[yellow]Warnings:[/yellow]")
            for warning in result.warnings:
                console.print(f"  ⚠ {warning}")
    else:
        console.print(f"[red]✗ Installation failed: {result.error}[/red]")

        if result.validation and result.validation.errors:
            console.print("\n[bold red]Validation errors:[/bold red]")
            for _, msg in result.validation.errors:
                console.print(f"  ✗ {msg}")


@marketplace.command("uninstall")
@click.argument("name")
@click.option(
    "--force", "-f", is_flag=True, help="Force uninstall without confirmation"
)
def marketplace_uninstall(name: str, force: bool = False):
    """Uninstall an installed plugin.

    Example:
        sindri marketplace uninstall my_tool
    """
    import asyncio
    from sindri.marketplace import PluginInstaller, MarketplaceIndex

    index = MarketplaceIndex()
    index.load()

    plugin = index.get(name)
    if not plugin:
        console.print(f"[red]Plugin '{name}' is not installed.[/red]")
        return

    if not force:
        console.print(f"[bold]Uninstalling plugin: {name}[/bold]")
        console.print(f"  Version: {plugin.metadata.version}")
        console.print(f"  Type: {plugin.metadata.plugin_type}")
        console.print(f"  Path: {plugin.installed_path}")
        console.print()

        if not click.confirm("Are you sure you want to uninstall this plugin?"):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    installer = PluginInstaller(index=index)
    result = asyncio.run(installer.uninstall(name))

    if result.success:
        console.print(f"[green]✓ Successfully uninstalled: {name}[/green]")
    else:
        console.print(f"[red]✗ Uninstall failed: {result.error}[/red]")


@marketplace.command("update")
@click.argument("name", required=False)
@click.option("--all", "-a", "update_all", is_flag=True, help="Update all plugins")
def marketplace_update(name: str = None, update_all: bool = False):
    """Re-install plugins from their local source paths.

    This reloads plugins from their original local paths, useful when
    the source files have been modified.

    Examples:
        sindri marketplace update my_tool
        sindri marketplace update --all
    """
    import asyncio
    from sindri.marketplace import PluginInstaller, MarketplaceIndex

    if not name and not update_all:
        console.print(
            "[red]Specify a plugin name or use --all to update all plugins.[/red]"
        )
        return

    index = MarketplaceIndex()
    index.load()

    if name:
        plugin = index.get(name)
        if not plugin:
            console.print(f"[red]Plugin '{name}' is not installed.[/red]")
            return
        if plugin.pinned:
            console.print(
                f"[yellow]Plugin '{name}' is pinned. Use 'sindri marketplace pin --unpin {name}' first.[/yellow]"
            )
            return

    installer = PluginInstaller(index=index)
    console.print("[bold]Updating plugins...[/bold]\n")

    results = asyncio.run(installer.update(name))

    if not results:
        console.print("[yellow]No plugins to update.[/yellow]")
        return

    successes = [r for r in results if r.success]
    failures = [r for r in results if not r.success]

    for r in successes:
        console.print(
            f"[green]✓ Updated: {r.plugin.metadata.name} → v{r.plugin.metadata.version}[/green]"
        )

    for r in failures:
        console.print(f"[red]✗ Failed: {r.error}[/red]")

    console.print(f"\n[dim]Updated: {len(successes)}, Failed: {len(failures)}[/dim]")


@marketplace.command("info")
@click.argument("name")
def marketplace_info(name: str):
    """Show detailed information about a plugin.

    Example:
        sindri marketplace info my_tool
    """
    from sindri.marketplace import PluginSearcher

    searcher = PluginSearcher()
    result = searcher.get_info(name)

    if not result:
        console.print(f"[red]Plugin '{name}' not found.[/red]")
        return

    console.print(f"[bold cyan]Plugin: {result.name}[/bold cyan]\n")

    console.print(f"  [bold]Version:[/bold]     {result.version}")
    console.print(
        f"  [bold]Type:[/bold]        {'🔧 Tool' if result.plugin_type == 'tool' else '🤖 Agent'}"
    )
    console.print(f"  [bold]Category:[/bold]    {result.category}")
    console.print(
        f"  [bold]Status:[/bold]      {'[green]Installed[/green]' if result.installed else '[dim]Not installed[/dim]'}"
    )

    if result.description:
        console.print(f"\n  [bold]Description:[/bold]\n  {result.description}")

    if result.tags:
        console.print(f"\n  [bold]Tags:[/bold]        {', '.join(result.tags)}")

    if result.installed_path:
        console.print(f"\n  [bold]Path:[/bold]        {result.installed_path}")

    if result.source:
        console.print(f"  [bold]Source:[/bold]      {result.source}")


@marketplace.command("pin")
@click.argument("name")
@click.option("--unpin", is_flag=True, help="Unpin the plugin (allow updates)")
def marketplace_pin(name: str, unpin: bool = False):
    """Pin a plugin to prevent automatic updates.

    Example:
        sindri marketplace pin my_tool
        sindri marketplace pin --unpin my_tool
    """
    from sindri.marketplace import MarketplaceIndex

    index = MarketplaceIndex()
    index.load()

    plugin = index.get(name)
    if not plugin:
        console.print(f"[red]Plugin '{name}' is not installed.[/red]")
        return

    if unpin:
        index.set_pinned(name, False)
        index.save()
        console.print(f"[green]✓ Unpinned: {name}[/green]")
        console.print(
            "[dim]This plugin will be included in 'marketplace update --all'[/dim]"
        )
    else:
        index.set_pinned(name, True)
        index.save()
        console.print(f"[green]✓ Pinned: {name}[/green]")
        console.print(
            "[dim]This plugin will not be updated by 'marketplace update --all'[/dim]"
        )


@marketplace.command("enable")
@click.argument("name")
@click.option("--disable", is_flag=True, help="Disable the plugin")
def marketplace_enable(name: str, disable: bool = False):
    """Enable or disable an installed plugin.

    Example:
        sindri marketplace enable my_tool
        sindri marketplace enable --disable my_tool
    """
    from sindri.marketplace import MarketplaceIndex

    index = MarketplaceIndex()
    index.load()

    plugin = index.get(name)
    if not plugin:
        console.print(f"[red]Plugin '{name}' is not installed.[/red]")
        return

    if disable:
        index.set_enabled(name, False)
        index.save()
        console.print(f"[yellow]✓ Disabled: {name}[/yellow]")
        console.print("[dim]The plugin will not be loaded on next start[/dim]")
    else:
        index.set_enabled(name, True)
        index.save()
        console.print(f"[green]✓ Enabled: {name}[/green]")
        console.print("[dim]The plugin will be loaded on next start[/dim]")


@marketplace.command("stats")
def marketplace_stats():
    """Show marketplace statistics."""
    from sindri.marketplace import MarketplaceIndex

    index = MarketplaceIndex()
    index.load()

    stats = index.get_stats()

    if stats["total"] == 0:
        console.print("[yellow]No plugins installed from marketplace.[/yellow]")
        console.print(
            "[dim]Install plugins with: sindri marketplace install <source>[/dim]"
        )
        return

    console.print("[bold]📊 Marketplace Statistics[/bold]\n")

    # Overview
    console.print(f"  [bold]Total plugins:[/bold]  {stats['total']}")
    console.print(f"  [bold]Enabled:[/bold]        {stats['enabled']}")
    console.print(f"  [bold]Pinned:[/bold]         {stats['pinned']}")

    # By type
    console.print("\n[bold]By Type:[/bold]")
    for ptype, count in stats["by_type"].items():
        icon = "🔧" if ptype == "tool" else "🤖"
        console.print(f"  {icon} {ptype}: {count}")

    # By category
    if stats["by_category"]:
        console.print("\n[bold]By Category:[/bold]")
        for cat, count in sorted(stats["by_category"].items(), key=lambda x: -x[1]):
            console.print(f"  {cat}: {count}")

    # By source
    if stats["by_source"]:
        console.print("\n[bold]By Source:[/bold]")
        for src, count in stats["by_source"].items():
            console.print(f"  {src}: {count}")


@marketplace.command("categories")
def marketplace_categories():
    """List available plugin categories."""
    from rich.table import Table
    from sindri.marketplace.search import get_categories

    categories = get_categories()

    table = Table(
        title="📂 Plugin Categories", show_header=True, header_style="bold cyan"
    )
    table.add_column("Category", style="cyan", width=15)
    table.add_column("Description", width=45)

    for value, description in categories:
        table.add_row(value, description)

    console.print(table)


# ============================================
# Phase 8.4: Multi-Project Memory Commands
# ============================================


@cli.group()
def projects():
    """Manage multi-project memory (Phase 8.4)."""
    pass


@projects.command("list")
@click.option("--tags", "-t", help="Filter by tags (comma-separated)")
@click.option("--enabled-only", "-e", is_flag=True, help="Show only enabled projects")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
def projects_list(tags: str = None, enabled_only: bool = False, verbose: bool = False):
    """List all registered projects."""
    from rich.table import Table
    from sindri.memory.projects import ProjectRegistry

    registry = ProjectRegistry()
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    projects = registry.list_projects(enabled_only=enabled_only, tags=tag_list)

    if not projects:
        console.print("[yellow]No projects registered.[/yellow]")
        console.print("\n[dim]Register projects with: sindri projects add <path>[/dim]")
        return

    table = Table(
        title=f"📁 Registered Projects ({len(projects)})",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Name", style="cyan", width=20)
    table.add_column("Status", width=10)
    table.add_column("Indexed", width=10)
    table.add_column("Tags", width=25)
    if verbose:
        table.add_column("Path", style="dim", width=40)

    for p in projects:
        status = "[green]enabled[/green]" if p.enabled else "[yellow]disabled[/yellow]"
        indexed = (
            f"[green]{p.file_count} files[/green]"
            if p.indexed
            else "[dim]not indexed[/dim]"
        )
        tags_str = ", ".join(p.tags[:3]) if p.tags else "[dim]none[/dim]"
        if len(p.tags) > 3:
            tags_str += f" (+{len(p.tags)-3})"

        row = [p.name, status, indexed, tags_str]
        if verbose:
            row.append(p.path)

        table.add_row(*row)

    console.print(table)

    # Summary
    stats = {
        "total": len(projects),
        "enabled": sum(1 for p in projects if p.enabled),
        "indexed": sum(1 for p in projects if p.indexed),
    }
    console.print(
        f"\n[dim]Total: {stats['total']} | Enabled: {stats['enabled']} | Indexed: {stats['indexed']}[/dim]"
    )


@projects.command("add")
@click.argument("path", type=click.Path(exists=True))
@click.option("--name", "-n", help="Project name (default: directory name)")
@click.option("--tags", "-t", help="Tags (comma-separated)")
@click.option("--no-index", is_flag=True, help="Don't index immediately")
def projects_add(path: str, name: str = None, tags: str = None, no_index: bool = False):
    """Add a project to the registry."""
    from sindri.memory.projects import ProjectRegistry
    from sindri.memory.global_memory import GlobalMemoryStore

    registry = ProjectRegistry()
    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    try:
        project = registry.add_project(path, name=name, tags=tag_list)
        console.print(f"[green]✓[/green] Added project: [cyan]{project.name}[/cyan]")
        console.print(f"  Path: {project.path}")
        if project.tags:
            console.print(f"  Tags: {', '.join(project.tags)}")

        # Index unless --no-index
        if not no_index:
            console.print("\n[dim]Indexing project...[/dim]")
            try:
                global_memory = GlobalMemoryStore(registry=registry)
                chunks = global_memory.index_project(project.path)
                console.print(f"[green]✓[/green] Indexed {chunks} chunks")
            except Exception as e:
                console.print(f"[yellow]⚠[/yellow] Indexing failed: {e}")
                console.print(
                    "[dim]You can index later with: sindri projects index <path>[/dim]"
                )
        else:
            console.print("\n[dim]Index with: sindri projects index <path>[/dim]")

    except ValueError as e:
        console.print(f"[red]✗[/red] {e}")


@projects.command("remove")
@click.argument("path", type=click.Path())
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def projects_remove(path: str, yes: bool = False):
    """Remove a project from the registry."""
    from sindri.memory.projects import ProjectRegistry
    from sindri.memory.global_memory import GlobalMemoryStore

    registry = ProjectRegistry()
    project = registry.get_project(path)

    if not project:
        console.print(f"[red]✗[/red] Project not found: {path}")
        return

    if not yes:
        console.print(f"Remove project [cyan]{project.name}[/cyan]?")
        console.print(f"  Path: {project.path}")
        if not click.confirm("Proceed?"):
            console.print("[dim]Cancelled[/dim]")
            return

    # Remove from global memory
    try:
        global_memory = GlobalMemoryStore(registry=registry)
        global_memory.remove_project(project.path)
    except Exception as e:
        console.print(f"[yellow]⚠[/yellow] Failed to remove from global memory: {e}")

    # Remove from registry
    if registry.remove_project(path):
        console.print(f"[green]✓[/green] Removed project: {project.name}")
    else:
        console.print("[red]✗[/red] Failed to remove project")


@projects.command("tag")
@click.argument("path", type=click.Path())
@click.argument("tags")
@click.option("--add", "-a", is_flag=True, help="Add tags instead of replacing")
def projects_tag(path: str, tags: str, add: bool = False):
    """Set or add tags to a project.

    TAGS is a comma-separated list of tags.

    Examples:
        sindri projects tag . "python,fastapi,web"
        sindri projects tag ~/myproject "ml,pytorch" --add
    """
    from sindri.memory.projects import ProjectRegistry

    registry = ProjectRegistry()
    tag_list = [t.strip() for t in tags.split(",")]

    if add:
        project = registry.add_tags(path, tag_list)
    else:
        project = registry.tag_project(path, tag_list)

    if not project:
        console.print(f"[red]✗[/red] Project not found: {path}")
        return

    console.print(f"[green]✓[/green] Updated tags for [cyan]{project.name}[/cyan]")
    console.print(f"  Tags: {', '.join(project.tags)}")


@projects.command("search")
@click.argument("query")
@click.option("--limit", "-n", default=10, help="Maximum results")
@click.option("--tags", "-t", help="Filter by tags (comma-separated)")
@click.option("--exclude", "-e", help="Exclude project path")
def projects_search(query: str, limit: int, tags: str = None, exclude: str = None):
    """Search across all indexed projects.

    Examples:
        sindri projects search "authentication handler"
        sindri projects search "API endpoint" --tags "python,fastapi"
    """
    from sindri.memory.global_memory import GlobalMemoryStore

    console.print(f"[dim]Searching for: {query}[/dim]\n")

    try:
        global_memory = GlobalMemoryStore()
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        results = global_memory.search(
            query, limit=limit, tags=tag_list, exclude_current=exclude
        )

        if not results:
            console.print("[yellow]No results found.[/yellow]")
            stats = global_memory.get_stats()
            console.print(
                f"\n[dim]Indexed: {stats['indexed_projects']} projects, {stats['total_chunks']} chunks[/dim]"
            )
            return

        console.print(f"[green]Found {len(results)} results:[/green]\n")

        for i, result in enumerate(results, 1):
            console.print(
                f"[bold cyan]{i}. [{result.project_name}][/bold cyan] {result.file_path}"
            )
            console.print(
                f"   Lines {result.start_line}-{result.end_line} | Similarity: {result.similarity:.2%}"
            )
            if result.tags:
                console.print(f"   Tags: {', '.join(result.tags)}")

            # Show code preview (truncated)
            preview = (
                result.content[:200] + "..."
                if len(result.content) > 200
                else result.content
            )
            console.print("   [dim]─────[/dim]")
            for line in preview.split("\n")[:5]:
                console.print(f"   [dim]{line}[/dim]")
            console.print()

    except Exception as e:
        console.print(f"[red]✗[/red] Search failed: {e}")
        console.print(
            "[dim]Make sure projects are indexed: sindri projects index --all[/dim]"
        )


@projects.command("index")
@click.argument("path", type=click.Path(), required=False)
@click.option(
    "--all", "-a", "index_all", is_flag=True, help="Index all registered projects"
)
@click.option("--force", "-f", is_flag=True, help="Force re-index")
def projects_index(path: str = None, index_all: bool = False, force: bool = False):
    """Index project(s) for cross-project search.

    Examples:
        sindri projects index .              # Index current directory
        sindri projects index ~/myproject    # Index specific project
        sindri projects index --all          # Index all registered projects
    """
    from sindri.memory.global_memory import GlobalMemoryStore

    if not path and not index_all:
        console.print("[red]✗[/red] Specify a path or use --all")
        return

    global_memory = GlobalMemoryStore()

    if index_all:
        console.print("[dim]Indexing all registered projects...[/dim]\n")
        results = global_memory.index_all_projects(force=force)

        if not results:
            console.print("[yellow]No projects to index.[/yellow]")
            console.print("[dim]Add projects with: sindri projects add <path>[/dim]")
            return

        total_chunks = sum(results.values())
        console.print(
            f"\n[green]✓[/green] Indexed {len(results)} projects, {total_chunks} total chunks"
        )

        for proj_path, chunks in results.items():
            proj_name = global_memory.registry.get_project(proj_path)
            name = proj_name.name if proj_name else proj_path.split("/")[-1]
            console.print(f"  • {name}: {chunks} chunks")
    else:
        console.print(f"[dim]Indexing {path}...[/dim]")
        try:
            chunks = global_memory.index_project(path, force=force)
            console.print(f"[green]✓[/green] Indexed {chunks} chunks")
        except Exception as e:
            console.print(f"[red]✗[/red] Failed: {e}")


@projects.command("enable")
@click.argument("path", type=click.Path())
def projects_enable(path: str):
    """Enable a project for cross-project search."""
    from sindri.memory.projects import ProjectRegistry

    registry = ProjectRegistry()
    project = registry.enable_project(path, enabled=True)

    if not project:
        console.print(f"[red]✗[/red] Project not found: {path}")
        return

    console.print(f"[green]✓[/green] Enabled project: [cyan]{project.name}[/cyan]")


@projects.command("disable")
@click.argument("path", type=click.Path())
def projects_disable(path: str):
    """Disable a project from cross-project search."""
    from sindri.memory.projects import ProjectRegistry

    registry = ProjectRegistry()
    project = registry.enable_project(path, enabled=False)

    if not project:
        console.print(f"[red]✗[/red] Project not found: {path}")
        return

    console.print(f"[yellow]⚠[/yellow] Disabled project: [cyan]{project.name}[/cyan]")


@projects.command("stats")
def projects_stats():
    """Show global memory statistics."""
    from sindri.memory.global_memory import GlobalMemoryStore
    from sindri.memory.projects import ProjectRegistry

    registry = ProjectRegistry()
    global_memory = GlobalMemoryStore(registry=registry)

    stats = global_memory.get_stats()
    all_tags = registry.get_all_tags()

    console.print("[bold]📊 Global Memory Statistics[/bold]\n")

    console.print(f"  Registered projects: {stats['registered_projects']}")
    console.print(f"  Enabled projects:    {stats['enabled_projects']}")
    console.print(f"  Indexed projects:    {stats['indexed_projects']}")
    console.print(f"  Total files:         {stats['total_files']}")
    console.print(f"  Total chunks:        {stats['total_chunks']}")

    if all_tags:
        console.print(f"\n  [dim]Tags in use: {', '.join(all_tags[:10])}")
        if len(all_tags) > 10:
            console.print(f"               (+{len(all_tags)-10} more)[/dim]")


# === Workspace Index Commands (ROADMAP Item 4) ===


@projects.command("activate")
@click.argument("path", type=click.Path())
def projects_activate(path: str):
    """Activate a project for immediate context inclusion.

    Active projects are pinned and their relevant content is automatically
    included in agent prompts for cross-project context.

    Examples:
        sindri projects activate .
        sindri projects activate ~/shared-utils
    """
    from sindri.memory.projects import ProjectRegistry

    registry = ProjectRegistry()
    project = registry.set_active(path, active=True)

    if not project:
        console.print(f"[red]x[/red] Project not found: {path}")
        return

    console.print(f"[green]v[/green] Activated project: [cyan]{project.name}[/cyan]")
    console.print("  [dim]This project's context will be included in agent prompts[/dim]")

    # Show active count
    active_count = registry.get_active_project_count()
    console.print(f"\n  [dim]Active projects: {active_count}[/dim]")


@projects.command("deactivate")
@click.argument("path", type=click.Path())
def projects_deactivate(path: str):
    """Deactivate a project from immediate context inclusion.

    The project will remain indexed but won't be automatically included
    in agent prompts.
    """
    from sindri.memory.projects import ProjectRegistry

    registry = ProjectRegistry()
    project = registry.set_active(path, active=False)

    if not project:
        console.print(f"[red]x[/red] Project not found: {path}")
        return

    console.print(f"[yellow]![/yellow] Deactivated project: [cyan]{project.name}[/cyan]")


@projects.command("settings")
@click.argument("path", type=click.Path())
@click.option("--show", "-s", is_flag=True, help="Show current settings")
@click.option("--chunk-size", "-c", type=int, help="Lines per chunk (default: 50)")
@click.option("--max-chunk-chars", type=int, help="Max chars per chunk (default: 2000)")
@click.option("--max-line-chars", type=int, help="Max line length before truncation (default: 500)")
@click.option("--exclude", "-e", help="Glob patterns to exclude (comma-separated)")
@click.option("--include", "-i", help="Glob patterns to include (comma-separated, priority)")
@click.option("--extensions", help="File extensions to index (comma-separated, e.g. '.py,.js')")
@click.option("--clear", is_flag=True, help="Clear custom settings (use defaults)")
def projects_settings(
    path: str,
    show: bool = False,
    chunk_size: int = None,
    max_chunk_chars: int = None,
    max_line_chars: int = None,
    exclude: str = None,
    include: str = None,
    extensions: str = None,
    clear: bool = False,
):
    """View or update per-project embedder settings.

    Examples:
        sindri projects settings . --show
        sindri projects settings . --chunk-size 100 --exclude "*.min.js,dist/*"
        sindri projects settings . --clear
    """
    from sindri.memory.projects import ProjectRegistry, ProjectEmbedderSettings

    registry = ProjectRegistry()
    project = registry.get_project(path)

    if not project:
        console.print(f"[red]x[/red] Project not found: {path}")
        return

    # Show current settings
    if show or (not clear and chunk_size is None and exclude is None and include is None and extensions is None and max_chunk_chars is None and max_line_chars is None):
        console.print(f"[bold]Settings for [cyan]{project.name}[/cyan][/bold]\n")

        if project.embedder_settings:
            s = project.embedder_settings
            console.print(f"  Chunk size (lines):    {s.chunk_size_lines}")
            console.print(f"  Max chunk chars:       {s.max_chunk_chars}")
            console.print(f"  Max line chars:        {s.max_line_chars}")
            console.print(f"  File extensions:       {', '.join(s.file_extensions) if s.file_extensions else '[default]'}")
            console.print(f"  Exclude patterns:      {', '.join(s.exclude_patterns) if s.exclude_patterns else '[none]'}")
            console.print(f"  Include patterns:      {', '.join(s.include_patterns) if s.include_patterns else '[none]'}")
        else:
            console.print("  [dim]Using default settings[/dim]")
            console.print("  Chunk size (lines):    50")
            console.print("  Max chunk chars:       2000")
            console.print("  Max line chars:        500")

        console.print(f"\n  Active:                {'[green]yes[/green]' if project.active else '[dim]no[/dim]'}")
        console.print(f"  Auto-index:            {'[green]yes[/green]' if project.auto_index else '[dim]no[/dim]'}")
        console.print(f"  Index priority:        {project.index_priority}")
        return

    # Clear settings
    if clear:
        registry.clear_embedder_settings(path)
        console.print(f"[green]v[/green] Cleared settings for [cyan]{project.name}[/cyan]")
        console.print("  [dim]Will use default settings[/dim]")
        return

    # Update settings
    current = project.embedder_settings or ProjectEmbedderSettings()

    new_settings = ProjectEmbedderSettings(
        chunk_size_lines=chunk_size if chunk_size is not None else current.chunk_size_lines,
        max_chunk_chars=max_chunk_chars if max_chunk_chars is not None else current.max_chunk_chars,
        max_line_chars=max_line_chars if max_line_chars is not None else current.max_line_chars,
        file_extensions=[e.strip() for e in extensions.split(",")] if extensions else current.file_extensions,
        exclude_patterns=[p.strip() for p in exclude.split(",")] if exclude else current.exclude_patterns,
        include_patterns=[p.strip() for p in include.split(",")] if include else current.include_patterns,
    )

    registry.set_embedder_settings(path, new_settings)
    console.print(f"[green]v[/green] Updated settings for [cyan]{project.name}[/cyan]")

    # Show what changed
    changes = []
    if chunk_size is not None:
        changes.append(f"chunk_size={chunk_size}")
    if max_chunk_chars is not None:
        changes.append(f"max_chunk_chars={max_chunk_chars}")
    if max_line_chars is not None:
        changes.append(f"max_line_chars={max_line_chars}")
    if exclude:
        changes.append(f"exclude={exclude}")
    if include:
        changes.append(f"include={include}")
    if extensions:
        changes.append(f"extensions={extensions}")

    if changes:
        console.print(f"  [dim]Changed: {', '.join(changes)}[/dim]")

    console.print("\n  [dim]Re-index to apply: sindri projects index <path> --force[/dim]")


@projects.command("active")
def projects_active():
    """List all active (pinned) projects."""
    from rich.table import Table
    from sindri.memory.projects import ProjectRegistry

    registry = ProjectRegistry()
    active_projects = registry.list_active_projects()

    if not active_projects:
        console.print("[yellow]No active projects.[/yellow]")
        console.print("\n[dim]Activate with: sindri projects activate <path>[/dim]")
        return

    table = Table(
        title=f"Active Projects ({len(active_projects)})",
        show_header=True,
        header_style="bold green",
    )
    table.add_column("Name", style="cyan", width=20)
    table.add_column("Priority", width=10)
    table.add_column("Indexed", width=15)
    table.add_column("Path", style="dim", width=40)

    for p in active_projects:
        indexed = (
            f"[green]{p.file_count} files[/green]"
            if p.indexed
            else "[yellow]not indexed[/yellow]"
        )
        table.add_row(p.name, str(p.index_priority), indexed, p.path)

    console.print(table)
    console.print("\n[dim]Active projects provide cross-project context in agent prompts[/dim]")


@projects.command("index-incremental")
@click.argument("path", type=click.Path(), required=False)
@click.option("--all", "-a", "index_all", is_flag=True, help="Index all registered projects")
@click.option("--force", "-f", is_flag=True, help="Force re-index all files (ignore hashes)")
def projects_index_incremental(path: str = None, index_all: bool = False, force: bool = False):
    """Incrementally index project(s), only processing changed files.

    This is faster than full indexing as it uses file hashes to detect changes
    and only re-indexes modified files.

    Examples:
        sindri projects index-incremental .
        sindri projects index-incremental --all
        sindri projects index-incremental . --force
    """
    from sindri.memory.global_memory import GlobalMemoryStore

    if not path and not index_all:
        console.print("[red]x[/red] Specify a path or use --all")
        return

    global_memory = GlobalMemoryStore()

    if index_all:
        console.print("[dim]Incrementally indexing all registered projects...[/dim]\n")

        projects = global_memory.registry.list_projects(enabled_only=True)
        if not projects:
            console.print("[yellow]No projects to index.[/yellow]")
            return

        total_indexed = 0
        total_skipped = 0
        total_removed = 0

        for proj in projects:
            console.print(f"  Indexing [cyan]{proj.name}[/cyan]...", end=" ")
            result = global_memory.index_project_incremental(proj.path, force=force)

            if result.error:
                console.print(f"[red]error: {result.error}[/red]")
            else:
                console.print(
                    f"[green]+{result.files_indexed}[/green] indexed, "
                    f"[dim]{result.files_skipped} skipped[/dim], "
                    f"[yellow]-{result.files_removed}[/yellow] removed "
                    f"({result.duration_seconds:.1f}s)"
                )
                total_indexed += result.files_indexed
                total_skipped += result.files_skipped
                total_removed += result.files_removed

        console.print(
            f"\n[green]v[/green] Done: {total_indexed} files indexed, "
            f"{total_skipped} skipped, {total_removed} removed"
        )
    else:
        console.print(f"[dim]Incrementally indexing {path}...[/dim]")
        result = global_memory.index_project_incremental(path, force=force)

        if result.error:
            console.print(f"[red]x[/red] Error: {result.error}")
        else:
            console.print(f"[green]v[/green] Indexed in {result.duration_seconds:.2f}s:")
            console.print(f"  Files indexed:  {result.files_indexed}")
            console.print(f"  Files skipped:  {result.files_skipped} (unchanged)")
            console.print(f"  Files removed:  {result.files_removed} (deleted)")
            console.print(f"  Chunks added:   {result.chunks_added}")
            console.print(f"  Chunks removed: {result.chunks_removed}")


@cli.command()
@click.argument("session_id")
@click.argument("rating", type=click.IntRange(1, 5))
@click.option("--notes", "-n", help="Optional notes about the session")
@click.option("--tag", "-t", multiple=True, help="Quality tags (can repeat)")
@click.option(
    "--turn", type=int, help="Rate specific turn index instead of whole session"
)
@click.option(
    "--exclude-training", is_flag=True, help="Exclude from training data export"
)
def feedback(
    session_id: str,
    rating: int,
    notes: str = None,
    tag: tuple = None,
    turn: int = None,
    exclude_training: bool = False,
):
    """Add feedback rating to a session (1-5 stars).

    SESSION_ID can be the full UUID or first 8 characters.
    RATING is 1-5 (1=poor, 5=excellent).

    Quality tags: correct, efficient, well_explained, followed_instructions,
    good_tool_use, creative, incorrect, inefficient, poor_explanation,
    ignored_instructions, wrong_tool, verbose, hallucinated, partial, needed_guidance

    Examples:

        sindri feedback abc12345 5 -n "Perfect solution"

        sindri feedback abc12345 4 -t correct -t efficient

        sindri feedback abc12345 2 --turn 3 -t wrong_tool
    """
    from sindri.persistence.feedback import SessionFeedback, FeedbackStore

    async def do_feedback():
        state = SessionState()
        feedback_store = FeedbackStore()

        # Resolve short session ID
        full_session_id = session_id
        if len(session_id) < 36:
            all_sessions = await state.list_sessions(limit=100)
            matching = [s for s in all_sessions if s["id"].startswith(session_id)]

            if not matching:
                console.print(f"[red]✗ No session found starting with {session_id}[/]")
                console.print(
                    "[dim]Use 'sindri sessions' to list available sessions[/dim]"
                )
                return False
            elif len(matching) > 1:
                console.print(f"[yellow]⚠ Multiple sessions match {session_id}:[/]")
                for m in matching:
                    console.print(f"  • {m['id'][:8]} - {m['task'][:50]}")
                console.print("[dim]Use more characters to be specific[/dim]")
                return False

            full_session_id = matching[0]["id"]

        # Verify session exists
        session = await state.load_session(full_session_id)
        if not session:
            console.print(f"[red]✗ Session {full_session_id} not found[/]")
            return False

        # Validate turn index if provided
        if turn is not None:
            if turn < 0 or turn >= len(session.turns):
                console.print(
                    f"[red]✗ Invalid turn index {turn}. Session has {len(session.turns)} turns (0-{len(session.turns)-1})[/]"
                )
                return False

        # Create feedback
        fb = SessionFeedback(
            session_id=full_session_id,
            rating=rating,
            turn_index=turn,
            quality_tags=list(tag) if tag else [],
            notes=notes,
            include_in_training=not exclude_training,
        )

        await feedback_store.add_feedback(fb)

        # Display confirmation
        stars = "⭐" * rating + "☆" * (5 - rating)
        console.print(f"[green]✓ Feedback added for session {full_session_id[:8]}[/]")
        console.print(f"  Rating: {stars} ({rating}/5)")
        if turn is not None:
            console.print(f"  Turn: {turn}")
        if tag:
            console.print(f"  Tags: {', '.join(tag)}")
        if notes:
            console.print(f"  Notes: {notes[:50]}...")
        if exclude_training:
            console.print("  [dim]Excluded from training export[/dim]")

        return True

    asyncio.run(do_feedback())


@cli.command("feedback-stats")
def feedback_stats():
    """Show feedback statistics and training data readiness.

    Displays aggregate statistics about collected feedback including:
    - Total feedback entries
    - Sessions with feedback
    - Rating distribution
    - Training data candidates (4+ star sessions)
    - Most common quality tags
    """
    from sindri.persistence.feedback import FeedbackStore

    async def show_stats():
        store = FeedbackStore()
        stats = await store.get_feedback_stats()

        if stats["total_feedback"] == 0:
            console.print("[yellow]No feedback collected yet[/]")
            console.print(
                "[dim]Use 'sindri feedback <session_id> <rating>' to add feedback[/dim]"
            )
            return

        console.print("[bold]📊 Feedback Statistics[/bold]\n")

        console.print(f"  Total feedback entries: {stats['total_feedback']}")
        console.print(f"  Sessions with feedback: {stats['sessions_with_feedback']}")
        console.print(f"  Average rating: {stats['average_rating']:.1f}/5")
        console.print(
            f"  Training candidates (4+ stars): [green]{stats['training_candidates']}[/green]"
        )

        # Rating distribution
        if stats["rating_distribution"]:
            console.print("\n[bold]Rating Distribution:[/bold]")
            for rating in range(5, 0, -1):
                count = stats["rating_distribution"].get(rating, 0)
                bar = "█" * count + "░" * (10 - min(count, 10))
                stars = "⭐" * rating + "☆" * (5 - rating)
                console.print(f"  {stars} [{bar}] {count}")

        # Top quality tags
        if stats["top_quality_tags"]:
            console.print("\n[bold]Top Quality Tags:[/bold]")
            for tag, count in list(stats["top_quality_tags"].items())[:5]:
                console.print(f"  • {tag}: {count}")

        console.print(
            "\n[dim]Export training data: sindri export-training output.jsonl[/dim]"
        )

    asyncio.run(show_stats())


@cli.command("export-training")
@click.argument("output", type=click.Path())
@click.option(
    "--format",
    "-f",
    type=click.Choice(["jsonl", "chatml", "ollama"]),
    default="jsonl",
    help="Export format",
)
@click.option(
    "--min-rating",
    "-r",
    default=4,
    type=click.IntRange(1, 5),
    help="Minimum rating to include",
)
@click.option(
    "--max-sessions", "-m", default=1000, type=int, help="Maximum sessions to export"
)
@click.option("--no-system-prompt", is_flag=True, help="Exclude system prompts")
@click.option("--no-tools", is_flag=True, help="Exclude tool calls and results")
@click.option("--agent", "-a", help="Export only sessions for specific agent/model")
def export_training(
    output: str,
    format: str,
    min_rating: int,
    max_sessions: int,
    no_system_prompt: bool,
    no_tools: bool,
    agent: str = None,
):
    """Export high-quality sessions for LLM fine-tuning.

    Exports sessions rated 4+ stars in formats suitable for fine-tuning:
    - jsonl: OpenAI fine-tuning format
    - chatml: Chat Markup Language format
    - ollama: Ollama Modelfile MESSAGE format

    Examples:

        sindri export-training training.jsonl

        sindri export-training data.jsonl --min-rating 5

        sindri export-training ollama.txt -f ollama

        sindri export-training huginn.jsonl --agent qwen2.5-coder
    """
    from pathlib import Path
    from sindri.persistence.training_export import TrainingDataExporter, ExportFormat

    async def do_export():
        exporter = TrainingDataExporter()
        output_path = Path(output)

        # Map format string to enum
        format_map = {
            "jsonl": ExportFormat.JSONL,
            "chatml": ExportFormat.CHATML,
            "ollama": ExportFormat.OLLAMA,
        }
        export_format = format_map[format]

        console.print("[bold]📦 Exporting Training Data[/bold]\n")
        console.print(f"  Format: {format}")
        console.print(f"  Min rating: {min_rating}+ stars")
        console.print(f"  Max sessions: {max_sessions}")
        if agent:
            console.print(f"  Agent filter: {agent}")

        # Export
        if agent:
            stats = await exporter.export_for_specific_agent(
                output_path=output_path,
                agent_name=agent,
                format=export_format,
                min_rating=min_rating,
                max_sessions=max_sessions,
            )
        else:
            stats = await exporter.export_training_data(
                output_path=output_path,
                format=export_format,
                min_rating=min_rating,
                include_system_prompt=not no_system_prompt,
                include_tool_calls=not no_tools,
                max_sessions=max_sessions,
            )

        if stats.sessions_exported == 0:
            console.print("\n[yellow]⚠ No sessions exported[/]")
            console.print(
                "[dim]Add feedback with 'sindri feedback <session_id> <rating>'[/dim]"
            )
            console.print(
                f"[dim]Need sessions rated {min_rating}+ stars marked for training[/dim]"
            )
            return

        console.print("\n[green]✓ Export complete![/green]")
        console.print(f"  Sessions: {stats.sessions_exported}")
        console.print(f"  Conversations: {stats.conversations_exported}")
        console.print(f"  Turns: {stats.turns_exported}")
        console.print(f"  Estimated tokens: ~{stats.total_tokens_estimate:,}")
        console.print(f"  Output: {output_path}")

        if format == "ollama":
            console.print(
                f"\n[dim]To create model: ollama create sindri-custom -f {output_path}[/dim]"
            )
        else:
            console.print(
                "\n[dim]Use this file for fine-tuning your preferred model[/dim]"
            )

    asyncio.run(do_export())


@cli.command("feedback-list")
@click.option(
    "--min-rating",
    "-r",
    default=1,
    type=click.IntRange(1, 5),
    help="Minimum rating filter",
)
@click.option(
    "--max-rating",
    "-R",
    default=5,
    type=click.IntRange(1, 5),
    help="Maximum rating filter",
)
@click.option(
    "--training-only", is_flag=True, help="Only show sessions marked for training"
)
@click.option("--limit", "-l", default=20, type=int, help="Maximum sessions to show")
def feedback_list(min_rating: int, max_rating: int, training_only: bool, limit: int):
    """List sessions with feedback.

    Shows sessions that have been rated, sorted by average rating.

    Examples:

        sindri feedback-list

        sindri feedback-list --min-rating 4

        sindri feedback-list --training-only
    """
    from rich.table import Table
    from sindri.persistence.feedback import FeedbackStore

    async def list_feedback():
        store = FeedbackStore()

        sessions = await store.list_rated_sessions(
            min_rating=min_rating,
            max_rating=max_rating,
            include_in_training_only=training_only,
            limit=limit,
        )

        if not sessions:
            console.print("[yellow]No rated sessions found[/]")
            if training_only:
                console.print("[dim]Try without --training-only flag[/dim]")
            return

        table = Table(title="Rated Sessions")
        table.add_column("Session")
        table.add_column("Task")
        table.add_column("Rating", justify="center")
        table.add_column("Count", justify="right")
        table.add_column("Tags")

        for s in sessions:
            rating = s["avg_rating"]
            stars = "⭐" * int(rating) + ("½" if rating % 1 >= 0.5 else "")

            # Color based on rating
            if rating >= 4:
                rating_color = "green"
            elif rating >= 3:
                rating_color = "yellow"
            else:
                rating_color = "red"

            tags_str = ", ".join(s["quality_tags"][:3]) if s["quality_tags"] else ""
            if len(s["quality_tags"]) > 3:
                tags_str += f" +{len(s['quality_tags'])-3}"

            table.add_row(
                s["id"][:8],
                s["task"][:35] + "..." if len(s["task"]) > 35 else s["task"],
                f"[{rating_color}]{stars}[/{rating_color}]",
                str(s["feedback_count"]),
                tags_str[:20],
            )

        console.print(table)
        console.print(
            "\n[dim]Use 'sindri feedback <session_id> <rating>' to add more feedback[/dim]"
        )

    asyncio.run(list_feedback())


# ============================================
# Phase 9.3: Voice Interface Commands
# ============================================


@cli.command()
@click.option(
    "--model",
    "-m",
    type=click.Choice(["tiny", "base", "small", "medium", "large"]),
    default="base",
    help="Whisper model size",
)
@click.option(
    "--mode",
    type=click.Choice(["push_to_talk", "wake_word", "continuous"]),
    default="push_to_talk",
    help="Voice mode",
)
@click.option(
    "--wake-word", "-w", default="sindri", help="Wake word for wake_word mode"
)
@click.option(
    "--tts",
    type=click.Choice(["pyttsx3", "piper", "espeak"]),
    default="pyttsx3",
    help="TTS engine",
)
@click.option(
    "--work-dir", type=click.Path(), help="Working directory for file operations"
)
def voice(model: str, mode: str, wake_word: str, tts: str, work_dir: str = None):
    """Start voice-controlled interface.

    Enables hands-free interaction with Sindri using speech-to-text
    (Whisper) and text-to-speech.

    Modes:
    - push_to_talk: Press Enter to start listening
    - wake_word: Say "Hey Sindri" to activate
    - continuous: Always listening (use with caution)

    Example:
        sindri voice

        sindri voice --mode wake_word --wake-word "hey sindri"

        sindri voice --model small --tts espeak
    """
    try:
        from sindri.voice import (
            VoiceInterface,
            VoiceMode,
            WhisperModel,
            VoiceConfig,
            TTSEngine,
        )
    except ImportError as e:
        console.print("[red]✗ Voice dependencies not installed[/red]")
        console.print(f"[dim]Error: {e}[/dim]")
        console.print("[dim]Install with: pip install sindri[voice][/dim]")
        return

    from pathlib import Path

    # Map string options to enums
    model_map = {
        "tiny": WhisperModel.TINY,
        "base": WhisperModel.BASE,
        "small": WhisperModel.SMALL,
        "medium": WhisperModel.MEDIUM,
        "large": WhisperModel.LARGE,
    }
    mode_map = {
        "push_to_talk": VoiceMode.PUSH_TO_TALK,
        "wake_word": VoiceMode.WAKE_WORD,
        "continuous": VoiceMode.CONTINUOUS,
    }
    tts_map = {
        "pyttsx3": TTSEngine.PYTTSX3,
        "piper": TTSEngine.PIPER,
        "espeak": TTSEngine.ESPEAK,
    }

    whisper_model = model_map[model]
    voice_mode = mode_map[mode]
    tts_engine = tts_map[tts]

    console.print(
        Panel(
            f"[bold blue]Voice Interface[/bold blue]\n\n"
            f"STT Model: Whisper {model}\n"
            f"TTS Engine: {tts}\n"
            f"Mode: {mode}\n"
            f"Wake Word: {wake_word if mode == 'wake_word' else 'N/A'}",
            title="🎤 Starting Voice Mode",
        )
    )

    async def run_voice():
        from sindri.core.orchestrator import Orchestrator
        from sindri.core.loop import LoopConfig

        work_path = Path(work_dir).resolve() if work_dir else None

        # Create orchestrator for executing commands
        config = LoopConfig(max_iterations=30)
        Orchestrator(config=config, work_dir=work_path)

        def handle_command(text: str) -> str:
            """Handle voice command by running through orchestrator."""
            # Check for built-in commands
            text_lower = text.lower().strip()

            if text_lower in ("stop", "quit", "exit"):
                return "Goodbye!"

            if text_lower == "help":
                return (
                    "You can say: run followed by a task, "
                    "list agents, status, or help. "
                    "Say stop to exit."
                )

            if text_lower == "list agents":
                return (
                    "Available agents are: Brokkr the orchestrator, "
                    "Huginn the coder, Mimir the reviewer, "
                    "Ratatoskr the executor, Skald the tester, "
                    "and more."
                )

            if text_lower == "status":
                return "All systems operational. Ready for commands."

            # For other commands, just acknowledge (would run orchestrator in full impl)
            return f"I'll work on: {text}"

        # Create voice interface
        tts_config = VoiceConfig(engine=tts_engine)
        interface = VoiceInterface(
            stt_model=whisper_model,
            tts_config=tts_config,
            mode=voice_mode,
            wake_word=wake_word,
            on_command=handle_command,
        )

        if not await interface.start():
            console.print("[red]✗ Failed to start voice interface[/red]")
            return

        console.print("[green]✓ Voice interface ready[/green]")

        if voice_mode == VoiceMode.PUSH_TO_TALK:
            console.print("[dim]Press Enter to start listening, Ctrl+C to exit[/dim]\n")

            try:
                while True:
                    input()  # Wait for Enter
                    console.print("[yellow]🎤 Listening...[/yellow]")
                    turn = await interface.listen_once()
                    if turn:
                        console.print(f"[blue]You:[/blue] {turn.user_text}")
                        console.print(f"[green]Sindri:[/green] {turn.response_text}")

                        if turn.user_text.lower().strip() in ("stop", "quit", "exit"):
                            break
                    console.print()
            except KeyboardInterrupt:
                pass

        else:
            console.print(f"[dim]Listening in {mode} mode. Ctrl+C to exit[/dim]\n")

            try:
                async for turn in interface.listen():
                    console.print(f"[blue]You:[/blue] {turn.user_text}")
                    console.print(f"[green]Sindri:[/green] {turn.response_text}")

                    if turn.user_text.lower().strip() in ("stop", "quit", "exit"):
                        break
                    console.print()
            except KeyboardInterrupt:
                pass

        await interface.stop()
        console.print("\n[dim]Voice interface stopped[/dim]")

    asyncio.run(run_voice())


@cli.command()
@click.argument("text")
@click.option(
    "--engine",
    "-e",
    type=click.Choice(["pyttsx3", "piper", "espeak"]),
    default="pyttsx3",
    help="TTS engine",
)
@click.option("--rate", "-r", default=175, help="Speech rate (words per minute)")
@click.option(
    "--output", "-o", type=click.Path(), help="Save to WAV file instead of playing"
)
def say(text: str, engine: str, rate: int, output: str = None):
    """Speak text using text-to-speech.

    Uses the configured TTS engine to synthesize and play speech.

    Example:
        sindri say "Hello, I am Sindri"

        sindri say "Task complete" --engine espeak

        sindri say "Save this" --output greeting.wav
    """
    try:
        from sindri.voice import TextToSpeech, VoiceConfig, TTSEngine
    except ImportError as e:
        console.print("[red]✗ Voice dependencies not installed[/red]")
        console.print(f"[dim]Error: {e}[/dim]")
        return

    tts_map = {
        "pyttsx3": TTSEngine.PYTTSX3,
        "piper": TTSEngine.PIPER,
        "espeak": TTSEngine.ESPEAK,
    }

    async def do_speak():
        config = VoiceConfig(engine=tts_map[engine], rate=rate)
        tts = TextToSpeech(config)

        if not await tts.initialize():
            console.print("[red]✗ Failed to initialize TTS[/red]")
            return

        if output:
            # Save to file
            from pathlib import Path

            success = await tts.synthesize_to_file(text, Path(output))
            if success:
                console.print(f"[green]✓ Saved to {output}[/green]")
            else:
                console.print("[red]✗ Failed to save audio[/red]")
        else:
            # Play audio
            success = await tts.speak(text)
            if not success:
                console.print("[red]✗ Failed to speak[/red]")

    asyncio.run(do_speak())


@cli.command()
@click.argument("audio_file", type=click.Path(exists=True))
@click.option(
    "--model",
    "-m",
    type=click.Choice(["tiny", "base", "small", "medium", "large"]),
    default="base",
    help="Whisper model size",
)
@click.option("--translate", is_flag=True, help="Translate to English")
def transcribe(audio_file: str, model: str, translate: bool):
    """Transcribe an audio file to text.

    Uses Whisper for local speech recognition.

    Example:
        sindri transcribe recording.wav

        sindri transcribe audio.mp3 --model small

        sindri transcribe foreign.wav --translate
    """
    try:
        from sindri.voice import SpeechToText, WhisperModel
    except ImportError as e:
        console.print("[red]✗ Voice dependencies not installed[/red]")
        console.print(f"[dim]Error: {e}[/dim]")
        return

    model_map = {
        "tiny": WhisperModel.TINY,
        "base": WhisperModel.BASE,
        "small": WhisperModel.SMALL,
        "medium": WhisperModel.MEDIUM,
        "large": WhisperModel.LARGE,
    }

    async def do_transcribe():
        stt = SpeechToText(model=model_map[model])

        console.print(f"[dim]Loading Whisper {model} model...[/dim]")
        if not await stt.load_model():
            console.print("[red]✗ Failed to load Whisper model[/red]")
            return

        console.print(f"[dim]Transcribing {audio_file}...[/dim]")
        task = "translate" if translate else "transcribe"
        result = await stt.transcribe_file(audio_file, task=task)

        if result.is_empty:
            console.print("[yellow]No speech detected in audio[/yellow]")
            return

        console.print("\n[bold]Transcription:[/bold]")
        console.print(result.text)
        console.print(f"\n[dim]Language: {result.language}[/dim]")
        console.print(f"[dim]Duration: {result.duration_seconds:.1f}s[/dim]")
        console.print(f"[dim]Processing time: {result.processing_time_ms:.0f}ms[/dim]")

        await stt.unload_model()

    asyncio.run(do_transcribe())


@cli.command("voice-status")
def voice_status():
    """Check voice interface dependencies and availability.

    Shows which STT and TTS engines are available on the system.
    """
    import shutil

    console.print("[bold]🎤 Voice Interface Status[/bold]\n")

    # Check STT dependencies
    console.print("[bold]Speech-to-Text (Whisper):[/bold]")
    import importlib.util

    if importlib.util.find_spec("faster_whisper"):
        console.print("  [green]✓ faster-whisper installed[/green]")
    else:
        console.print("  [red]✗ faster-whisper not installed[/red]")
        console.print("    [dim]Install with: pip install faster-whisper[/dim]")

    if importlib.util.find_spec("pyaudio"):
        console.print("  [green]✓ pyaudio installed (microphone support)[/green]")
    else:
        console.print("  [yellow]⚠ pyaudio not installed (no microphone)[/yellow]")
        console.print("    [dim]Install with: pip install pyaudio[/dim]")

    console.print()

    # Check TTS dependencies
    console.print("[bold]Text-to-Speech:[/bold]")

    if importlib.util.find_spec("pyttsx3"):
        console.print("  [green]✓ pyttsx3 installed[/green]")
    else:
        console.print("  [yellow]⚠ pyttsx3 not installed[/yellow]")
        console.print("    [dim]Install with: pip install pyttsx3[/dim]")

    if shutil.which("piper"):
        console.print("  [green]✓ piper-tts available[/green]")
    else:
        console.print("  [dim]○ piper-tts not found[/dim]")

    espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    if espeak:
        console.print(f"  [green]✓ espeak available ({espeak})[/green]")
    else:
        console.print("  [dim]○ espeak not found[/dim]")

    console.print()

    # Check audio playback
    console.print("[bold]Audio Playback:[/bold]")
    players = ["aplay", "paplay", "pw-play", "afplay", "ffplay"]
    found_player = False
    for player in players:
        if shutil.which(player):
            console.print(f"  [green]✓ {player} available[/green]")
            found_player = True
            break

    if not found_player:
        console.print("  [yellow]⚠ No audio player found[/yellow]")

    console.print()
    console.print(
        "[dim]Install all voice dependencies with: pip install sindri[voice][/dim]"
    )


# ============================================
# Phase 9.4: Security Scanning Commands
# ============================================


@cli.command("scan")
@click.option("--path", "-p", type=click.Path(exists=True), help="Project path to scan")
@click.option(
    "--ecosystem",
    "-e",
    type=click.Choice(["python", "node", "rust", "go"]),
    help="Override ecosystem detection",
)
@click.option(
    "--severity",
    "-s",
    type=click.Choice(["low", "medium", "high", "critical"]),
    default="low",
    help="Minimum severity to report",
)
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["text", "json", "sarif"]),
    default="text",
    help="Output format",
)
@click.option(
    "--include-dev/--no-dev", default=True, help="Include development dependencies"
)
@click.option("--outdated", is_flag=True, help="Also check for outdated packages")
@click.option(
    "--fix", is_flag=True, help="Attempt to fix vulnerabilities automatically"
)
def scan_dependencies(
    path: str,
    ecosystem: str,
    severity: str,
    output_format: str,
    include_dev: bool,
    outdated: bool,
    fix: bool,
):
    """Scan project dependencies for security vulnerabilities.

    Automatically detects project type and uses the appropriate scanner:
    - Python: pip-audit (or safety)
    - Node.js: npm audit
    - Rust: cargo audit
    - Go: govulncheck

    Example:
        sindri scan

        sindri scan --path /project --severity high

        sindri scan --format json --outdated

        sindri scan --fix
    """
    from sindri.tools.dependency_scanner import ScanDependenciesTool
    from pathlib import Path as P

    async def do_scan():
        tool = ScanDependenciesTool(work_dir=P(path).resolve() if path else None)

        result = await tool.execute(
            path=path or ".",
            ecosystem=ecosystem,
            min_severity=severity,
            format=output_format,
            include_dev=include_dev,
            check_outdated=outdated,
            fix=fix,
        )

        if result.success:
            console.print(result.output)

            # Show summary
            meta = result.metadata
            if meta.get("vulnerability_count", 0) > 0:
                console.print()
                if meta.get("critical", 0) > 0:
                    console.print(
                        f"[red bold]⚠ {meta['critical']} CRITICAL vulnerabilities found![/red bold]"
                    )
                if meta.get("high", 0) > 0:
                    console.print(
                        f"[red]{meta['high']} high severity vulnerabilities[/red]"
                    )
            else:
                console.print("\n[green]✓ No vulnerabilities found[/green]")
        else:
            console.print(f"[red]✗ Scan failed: {result.error}[/red]")

    asyncio.run(do_scan())


@cli.command("sbom")
@click.option("--path", "-p", type=click.Path(exists=True), help="Project path")
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["cyclonedx", "spdx"]),
    default="cyclonedx",
    help="SBOM format",
)
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option(
    "--include-dev/--no-dev", default=True, help="Include development dependencies"
)
def generate_sbom(path: str, output_format: str, output: str, include_dev: bool):
    """Generate Software Bill of Materials (SBOM).

    Creates a comprehensive list of all project dependencies in
    CycloneDX or SPDX format.

    Example:
        sindri sbom

        sindri sbom --format spdx --output sbom.json

        sindri sbom --no-dev
    """
    from sindri.tools.dependency_scanner import GenerateSBOMTool
    from pathlib import Path as P

    async def do_sbom():
        tool = GenerateSBOMTool(work_dir=P(path).resolve() if path else None)

        result = await tool.execute(
            path=path or ".",
            format=output_format,
            output=output,
            include_dev=include_dev,
        )

        if result.success:
            if output:
                console.print(f"[green]✓ SBOM saved to {output}[/green]")
                console.print(
                    f"[dim]Format: {output_format}, Dependencies: {result.metadata.get('dependency_count', 0)}[/dim]"
                )
            else:
                console.print(result.output)
        else:
            console.print(f"[red]✗ SBOM generation failed: {result.error}[/red]")

    asyncio.run(do_sbom())


@cli.command("outdated")
@click.option("--path", "-p", type=click.Path(exists=True), help="Project path")
@click.option(
    "--include-dev/--no-dev", default=True, help="Include development dependencies"
)
def check_outdated(path: str, include_dev: bool):
    """Check for outdated dependencies.

    Lists all packages that have newer versions available.

    Example:
        sindri outdated

        sindri outdated --path /project --no-dev
    """
    from sindri.tools.dependency_scanner import CheckOutdatedTool
    from pathlib import Path as P

    async def do_check():
        tool = CheckOutdatedTool(work_dir=P(path).resolve() if path else None)

        result = await tool.execute(
            path=path or ".",
            include_dev=include_dev,
        )

        if result.success:
            console.print(result.output)

            meta = result.metadata
            if meta.get("outdated_count", 0) > 0:
                console.print(
                    f"\n[yellow]⚠ {meta['outdated_count']} packages have updates available[/yellow]"
                )
        else:
            console.print(f"[red]✗ Check failed: {result.error}[/red]")

    asyncio.run(do_check())


@cli.command("security-status")
def security_status():
    """Check security scanning tool availability.

    Shows which vulnerability scanners are available on the system.
    """
    import shutil

    console.print("[bold]🔒 Security Scanner Status[/bold]\n")

    # Python scanners
    console.print("[bold]Python:[/bold]")
    if shutil.which("pip-audit"):
        console.print("  [green]✓ pip-audit installed (recommended)[/green]")
    else:
        console.print("  [yellow]⚠ pip-audit not installed[/yellow]")
        console.print("    [dim]Install with: pip install pip-audit[/dim]")

    if shutil.which("safety"):
        console.print("  [green]✓ safety installed (alternative)[/green]")
    else:
        console.print("  [dim]○ safety not installed (optional)[/dim]")

    console.print()

    # Node.js scanners
    console.print("[bold]Node.js:[/bold]")
    if shutil.which("npm"):
        console.print("  [green]✓ npm available (npm audit)[/green]")
    else:
        console.print("  [red]✗ npm not found[/red]")
        console.print("    [dim]Install Node.js to enable npm audit[/dim]")

    console.print()

    # Rust scanners
    console.print("[bold]Rust:[/bold]")
    if shutil.which("cargo"):
        console.print("  [green]✓ cargo available[/green]")

        # Check cargo-audit
        import subprocess

        try:
            result = subprocess.run(
                ["cargo", "audit", "--version"], capture_output=True, timeout=5
            )
            if result.returncode == 0:
                console.print("  [green]✓ cargo-audit installed[/green]")
            else:
                console.print("  [yellow]⚠ cargo-audit not installed[/yellow]")
                console.print("    [dim]Install with: cargo install cargo-audit[/dim]")
        except Exception:
            console.print("  [yellow]⚠ cargo-audit not installed[/yellow]")
            console.print("    [dim]Install with: cargo install cargo-audit[/dim]")
    else:
        console.print("  [dim]○ cargo not found (Rust not installed)[/dim]")

    console.print()

    # Go scanners
    console.print("[bold]Go:[/bold]")
    if shutil.which("go"):
        console.print("  [green]✓ go available[/green]")

        if shutil.which("govulncheck"):
            console.print("  [green]✓ govulncheck installed[/green]")
        else:
            console.print("  [yellow]⚠ govulncheck not installed[/yellow]")
            console.print(
                "    [dim]Install with: go install golang.org/x/vuln/cmd/govulncheck@latest[/dim]"
            )
    else:
        console.print("  [dim]○ go not found (Go not installed)[/dim]")

    console.print()
    console.print("[dim]Use 'sindri scan' to scan for vulnerabilities[/dim]")


# ============================================
# Phase 9.5: API Spec Generation Commands
# ============================================


@cli.command("api-spec")
@click.option(
    "--path", "-p", type=click.Path(exists=True), help="Project path to scan for routes"
)
@click.option(
    "--output", "-o", type=click.Path(), help="Output file path (default: openapi.json)"
)
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["json", "yaml"]),
    default="json",
    help="Output format",
)
@click.option("--title", "-t", help="API title (auto-detected if not provided)")
@click.option("--version", "-v", "api_version", default="1.0.0", help="API version")
@click.option("--description", "-d", help="API description")
@click.option(
    "--server", "-s", "servers", multiple=True, help="Server URL (can specify multiple)"
)
@click.option(
    "--framework",
    type=click.Choice(["flask", "fastapi", "express", "django", "gin", "echo"]),
    help="Override framework detection",
)
@click.option("--dry-run", is_flag=True, help="Preview spec without creating file")
def api_spec(
    path: str,
    output: str,
    output_format: str,
    title: str,
    api_version: str,
    description: str,
    servers: tuple,
    framework: str,
    dry_run: bool,
):
    """Generate OpenAPI specification from route definitions.

    Automatically detects the web framework and extracts route information
    to generate an OpenAPI 3.0 specification.

    Supported frameworks:
    - Python: Flask, FastAPI, Django
    - JavaScript/TypeScript: Express.js
    - Go: Gin, Echo

    Example:
        sindri api-spec

        sindri api-spec --path src/api --output docs/openapi.yaml --format yaml

        sindri api-spec --title "My API" --version 2.0.0 --server https://api.example.com

        sindri api-spec --framework flask --dry-run
    """
    from sindri.tools.api_spec import GenerateApiSpecTool
    from pathlib import Path as P

    async def do_generate():
        tool = GenerateApiSpecTool(work_dir=P(path).resolve() if path else None)

        result = await tool.execute(
            path=path or ".",
            output=output,
            format=output_format,
            title=title,
            version=api_version,
            description=description,
            servers=list(servers) if servers else None,
            framework=framework,
            dry_run=dry_run,
        )

        if result.success:
            meta = result.metadata
            if dry_run:
                console.print("[bold]OpenAPI Spec Preview[/bold] (dry run)\n")
                console.print(f"Framework: {meta.get('framework', 'unknown')}")
                console.print(f"Routes: {meta.get('routes_count', 0)}")
                console.print(
                    f"Would write to: {meta.get('output_file', 'openapi.json')}\n"
                )
                # Print a truncated preview
                output_text = result.output
                if len(output_text) > 2000:
                    console.print(output_text[:2000])
                    console.print("\n[dim]... (truncated)[/dim]")
                else:
                    console.print(output_text)
            else:
                console.print(
                    f"[green]✓ OpenAPI spec generated: {meta.get('output_file')}[/green]"
                )
                console.print(
                    f"[dim]Framework: {meta.get('framework')}, Routes: {meta.get('routes_count')}[/dim]"
                )
        else:
            console.print(f"[red]✗ Generation failed: {result.error}[/red]")
            if result.metadata.get("framework"):
                console.print(
                    f"[dim]Detected framework: {result.metadata.get('framework')}[/dim]"
                )

    asyncio.run(do_generate())


@cli.command("validate-api-spec")
@click.argument("file_path", type=click.Path(exists=True))
def validate_api_spec(file_path: str):
    """Validate an OpenAPI specification file.

    Checks for:
    - Valid JSON/YAML syntax
    - Required OpenAPI fields
    - Valid HTTP methods and status codes
    - Path parameter definitions

    Example:
        sindri validate-api-spec openapi.json

        sindri validate-api-spec docs/api.yaml
    """
    from sindri.tools.api_spec import ValidateApiSpecTool
    from pathlib import Path as P

    async def do_validate():
        tool = ValidateApiSpecTool(work_dir=P(file_path).parent)

        result = await tool.execute(file_path=file_path)

        if result.success:
            console.print(f"[green]✓ OpenAPI spec is valid: {file_path}[/green]")
            if result.metadata.get("warnings"):
                console.print("\n[yellow]Warnings:[/yellow]")
                for warning in result.metadata["warnings"]:
                    console.print(f"  ⚠ {warning}")
        else:
            console.print(f"[red]✗ Validation failed: {file_path}[/red]")
            console.print(result.output)

    asyncio.run(do_validate())


@cli.command()
@click.option("--host", "-h", default="0.0.0.0", help="Host to bind to")
@click.option("--port", "-p", default=8000, help="Port to listen on")
@click.option("--vram-gb", default=16.0, help="Total VRAM in GB")
@click.option(
    "--work-dir", "-w", type=click.Path(), help="Working directory for file operations"
)
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def web(
    host: str, port: int, vram_gb: float, work_dir: str = None, reload: bool = False
):
    """Start the Sindri Web API server.

    The Web API provides:
    - REST endpoints for agents, sessions, tasks, metrics
    - WebSocket for real-time event streaming
    - CORS support for frontend access

    Example:
        sindri web --port 8080

    Then visit http://localhost:8080/docs for API documentation.
    """
    try:
        import uvicorn
        import fastapi  # noqa: F401 - Check if fastapi is available
    except ImportError:
        console.print("[red]✗ Web dependencies not installed[/red]")
        console.print("[dim]Install with: pip install sindri[web][/dim]")
        return

    from pathlib import Path

    console.print(
        Panel(
            f"[bold blue]Sindri Web API[/bold blue]\n\n"
            f"Host: {host}\n"
            f"Port: {port}\n"
            f"VRAM: {vram_gb}GB",
            title="🌐 Starting Server",
        )
    )

    work_path = Path(work_dir).resolve() if work_dir else None

    console.print(f"\n[dim]API docs: http://{host}:{port}/docs[/dim]")
    console.print(f"[dim]WebSocket: ws://{host}:{port}/ws[/dim]\n")

    # Run server
    from sindri.web import create_app

    if reload:
        # Development mode with auto-reload
        uvicorn.run(
            "sindri.web:create_app",
            host=host,
            port=port,
            reload=True,
            factory=True,
            log_level="info",
        )
    else:
        # Production mode
        app = create_app(vram_gb=vram_gb, work_dir=work_path)
        uvicorn.run(app, host=host, port=port, log_level="info")


# ============================================
# Infrastructure as Code Generation Commands
# ============================================


@cli.command("terraform")
@click.option(
    "--path", "-p", type=click.Path(exists=True), help="Project path (default: current)"
)
@click.option(
    "--output", "-o", type=click.Path(), help="Output directory (default: terraform/)"
)
@click.option(
    "--provider",
    type=click.Choice(["aws", "gcp", "azure"]),
    default="aws",
    help="Cloud provider",
)
@click.option("--region", "-r", help="Cloud region (auto-detected from provider)")
@click.option(
    "--environment",
    "-e",
    type=click.Choice(["dev", "staging", "prod"]),
    default="dev",
    help="Environment",
)
@click.option(
    "--compute",
    type=click.Choice(["container", "vm", "serverless", "kubernetes"]),
    default="container",
    help="Compute type",
)
@click.option("--database", "-d", help="Database type: postgres, mysql, mongodb, dynamodb")
@click.option("--cache", "-c", help="Cache type: redis, memcached")
@click.option("--queue", "-q", help="Queue type: sqs, pubsub, servicebus, rabbitmq")
@click.option("--storage", is_flag=True, help="Include object storage (S3/GCS/Blob)")
@click.option("--cdn", is_flag=True, help="Include CDN (CloudFront/Cloud CDN)")
@click.option("--load-balancer", is_flag=True, help="Include load balancer")
@click.option("--project-name", help="Project name (default: directory name)")
@click.option("--dry-run", is_flag=True, help="Preview without creating files")
def terraform(
    path: str,
    output: str,
    provider: str,
    region: str,
    environment: str,
    compute: str,
    database: str,
    cache: str,
    queue: str,
    storage: bool,
    cdn: bool,
    load_balancer: bool,
    project_name: str,
    dry_run: bool,
):
    """Generate Terraform configuration for cloud infrastructure.

    Automatically detects project type and generates appropriate Terraform HCL
    with support for AWS, GCP, and Azure.

    Examples:
        sindri terraform

        sindri terraform --provider gcp --region us-central1

        sindri terraform --provider aws --database postgres --cache redis

        sindri terraform --compute serverless --dry-run

        sindri terraform --provider azure --environment prod --load-balancer
    """
    from sindri.tools.iac import GenerateTerraformTool
    from pathlib import Path

    async def execute():
        work_path = Path(path).resolve() if path else Path.cwd()
        tool = GenerateTerraformTool(work_dir=work_path)

        result = await tool.execute(
            path=str(work_path),
            output_dir=output,
            provider=provider,
            region=region,
            environment=environment,
            compute_type=compute,
            database=database,
            cache=cache,
            queue=queue,
            storage=storage,
            cdn=cdn,
            load_balancer=load_balancer,
            project_name=project_name,
            dry_run=dry_run,
        )

        if result.success:
            console.print(f"[green]✓[/green] {result.output}")
        else:
            console.print(f"[red]✗[/red] {result.error}")

    asyncio.run(execute())


@cli.command("pulumi")
@click.option(
    "--path", "-p", type=click.Path(exists=True), help="Project path (default: current)"
)
@click.option(
    "--output", "-o", type=click.Path(), help="Output directory (default: infra/)"
)
@click.option(
    "--language",
    "-l",
    type=click.Choice(["python", "typescript"]),
    default="python",
    help="Pulumi language",
)
@click.option(
    "--provider",
    type=click.Choice(["aws", "gcp", "azure"]),
    default="aws",
    help="Cloud provider",
)
@click.option("--project-name", help="Project name (default: directory name)")
@click.option("--dry-run", is_flag=True, help="Preview without creating files")
def pulumi(
    path: str,
    output: str,
    language: str,
    provider: str,
    project_name: str,
    dry_run: bool,
):
    """Generate Pulumi infrastructure code.

    Creates Pulumi Python or TypeScript code for cloud infrastructure.

    Examples:
        sindri pulumi

        sindri pulumi --language typescript --provider aws

        sindri pulumi --provider gcp --dry-run

        sindri pulumi --project-name my-infra --output infrastructure/
    """
    from sindri.tools.iac import GeneratePulumiTool
    from pathlib import Path

    async def execute():
        work_path = Path(path).resolve() if path else Path.cwd()
        tool = GeneratePulumiTool(work_dir=work_path)

        result = await tool.execute(
            path=str(work_path),
            output_dir=output,
            language=language,
            provider=provider,
            project_name=project_name,
            dry_run=dry_run,
        )

        if result.success:
            console.print(f"[green]✓[/green] {result.output}")
        else:
            console.print(f"[red]✗[/red] {result.error}")

    asyncio.run(execute())


@cli.command("validate-terraform")
@click.option(
    "--path",
    "-p",
    type=click.Path(exists=True),
    help="Terraform directory (default: current)",
)
@click.option("--check-formatting", is_flag=True, help="Also check terraform fmt")
def validate_terraform(path: str, check_formatting: bool):
    """Validate Terraform configuration files.

    Checks for syntax errors, missing required fields, and best practices.

    Examples:
        sindri validate-terraform

        sindri validate-terraform --path terraform/

        sindri validate-terraform --check-formatting
    """
    from sindri.tools.iac import ValidateTerraformTool
    from pathlib import Path

    async def execute():
        work_path = Path(path).resolve() if path else Path.cwd()
        tool = ValidateTerraformTool(work_dir=work_path)

        result = await tool.execute(
            path=str(work_path),
            check_formatting=check_formatting,
        )

        if result.success:
            console.print(f"[green]✓[/green] {result.output}")
        else:
            console.print(f"[red]✗[/red] {result.output}")

    asyncio.run(execute())


# ============================================
# Phase 10+: Database Migration Commands
# ============================================


@cli.command("migrate")
@click.option(
    "--path", "-p", type=click.Path(exists=True), help="Project path (default: current)"
)
@click.option(
    "--framework",
    "-f",
    type=click.Choice([
        "alembic", "django", "prisma", "knex", "sequelize",
        "goose", "diesel", "seaorm", "atlas"
    ]),
    help="Override detected framework",
)
@click.option("--target", "-t", help="Target revision (default: latest)")
@click.option("--dry-run", is_flag=True, help="Preview SQL without applying")
def migrate(path: str, framework: str, target: str, dry_run: bool):
    """Run pending database migrations.

    Automatically detects the migration framework and applies pending migrations.

    Examples:
        sindri migrate

        sindri migrate --framework alembic --target head

        sindri migrate --dry-run

        sindri migrate --path /app --framework prisma
    """
    from sindri.tools.migrations import RunMigrationsTool
    from pathlib import Path

    async def execute():
        work_path = Path(path).resolve() if path else Path.cwd()
        tool = RunMigrationsTool(work_dir=work_path)

        result = await tool.execute(
            path=str(work_path),
            framework=framework,
            target=target,
            dry_run=dry_run,
        )

        if result.success:
            console.print(f"[green]✓[/green] {result.output}")
        else:
            console.print(f"[red]✗[/red] {result.error or result.output}")

    asyncio.run(execute())


@cli.command("migrate-status")
@click.option(
    "--path", "-p", type=click.Path(exists=True), help="Project path (default: current)"
)
@click.option(
    "--framework",
    "-f",
    type=click.Choice([
        "alembic", "django", "prisma", "knex", "sequelize",
        "goose", "diesel", "seaorm", "atlas"
    ]),
    help="Override detected framework",
)
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
def migrate_status(path: str, framework: str, verbose: bool):
    """Check status of database migrations.

    Shows which migrations have been applied and which are pending.

    Examples:
        sindri migrate-status

        sindri migrate-status --verbose

        sindri migrate-status --framework django
    """
    from sindri.tools.migrations import MigrationStatusTool
    from pathlib import Path

    async def execute():
        work_path = Path(path).resolve() if path else Path.cwd()
        tool = MigrationStatusTool(work_dir=work_path)

        result = await tool.execute(
            path=str(work_path),
            framework=framework,
            verbose=verbose,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]✗[/red] {result.error}")

    asyncio.run(execute())


@cli.command("migrate-generate")
@click.argument("name")
@click.option(
    "--path", "-p", type=click.Path(exists=True), help="Project path (default: current)"
)
@click.option(
    "--framework",
    "-f",
    type=click.Choice([
        "alembic", "django", "prisma", "knex", "sequelize",
        "goose", "diesel", "seaorm", "atlas"
    ]),
    help="Override detected framework",
)
@click.option("--message", "-m", help="Migration description/message")
@click.option("--auto", is_flag=True, help="Auto-generate from model changes (Alembic, Prisma, Django)")
@click.option("--sql", help="SQL content for the migration")
@click.option("--sql-down", help="SQL content for rollback")
@click.option("--dry-run", is_flag=True, help="Preview without creating file")
def migrate_generate(
    name: str,
    path: str,
    framework: str,
    message: str,
    auto: bool,
    sql: str,
    sql_down: str,
    dry_run: bool,
):
    """Generate a new database migration.

    Creates a new migration file based on the detected framework.

    Examples:
        sindri migrate-generate add_users_table

        sindri migrate-generate create_posts --message "Add posts table"

        sindri migrate-generate add_index --auto

        sindri migrate-generate add_column --sql "ALTER TABLE users ADD email TEXT;"

        sindri migrate-generate --dry-run test_migration
    """
    from sindri.tools.migrations import GenerateMigrationTool
    from pathlib import Path

    async def execute():
        work_path = Path(path).resolve() if path else Path.cwd()
        tool = GenerateMigrationTool(work_dir=work_path)

        result = await tool.execute(
            name=name,
            path=str(work_path),
            framework=framework,
            message=message,
            auto=auto,
            sql=sql,
            sql_down=sql_down,
            dry_run=dry_run,
        )

        if result.success:
            console.print(f"[green]✓[/green] {result.output}")
        else:
            console.print(f"[red]✗[/red] {result.error}")

    asyncio.run(execute())


@cli.command("migrate-rollback")
@click.option(
    "--path", "-p", type=click.Path(exists=True), help="Project path (default: current)"
)
@click.option(
    "--framework",
    "-f",
    type=click.Choice([
        "alembic", "django", "prisma", "knex", "sequelize",
        "goose", "diesel", "seaorm", "atlas"
    ]),
    help="Override detected framework",
)
@click.option("--steps", "-n", type=int, default=1, help="Number of migrations to rollback (default: 1)")
@click.option("--target", "-t", help="Target revision to rollback to")
@click.option("--dry-run", is_flag=True, help="Preview SQL without rolling back")
def migrate_rollback(path: str, framework: str, steps: int, target: str, dry_run: bool):
    """Rollback database migrations.

    Reverts migrations to a previous state.

    Examples:
        sindri migrate-rollback

        sindri migrate-rollback --steps 3

        sindri migrate-rollback --target abc123

        sindri migrate-rollback --dry-run
    """
    from sindri.tools.migrations import RollbackMigrationTool
    from pathlib import Path

    async def execute():
        work_path = Path(path).resolve() if path else Path.cwd()
        tool = RollbackMigrationTool(work_dir=work_path)

        result = await tool.execute(
            path=str(work_path),
            framework=framework,
            steps=steps,
            target=target,
            dry_run=dry_run,
        )

        if result.success:
            console.print(f"[green]✓[/green] {result.output}")
        else:
            console.print(f"[red]✗[/red] {result.error}")

    asyncio.run(execute())


@cli.command("migrate-validate")
@click.option(
    "--path", "-p", type=click.Path(exists=True), help="Project path (default: current)"
)
@click.option(
    "--framework",
    "-f",
    type=click.Choice([
        "alembic", "django", "prisma", "knex", "sequelize",
        "goose", "diesel", "seaorm", "atlas"
    ]),
    help="Override detected framework",
)
@click.option("--check-down/--no-check-down", default=True, help="Verify down migrations exist")
def migrate_validate(path: str, framework: str, check_down: bool):
    """Validate database migrations for consistency.

    Checks for issues like missing down migrations, syntax errors, and consistency problems.

    Examples:
        sindri migrate-validate

        sindri migrate-validate --framework alembic

        sindri migrate-validate --no-check-down
    """
    from sindri.tools.migrations import ValidateMigrationsTool
    from pathlib import Path

    async def execute():
        work_path = Path(path).resolve() if path else Path.cwd()
        tool = ValidateMigrationsTool(work_dir=work_path)

        result = await tool.execute(
            path=str(work_path),
            framework=framework,
            check_down=check_down,
        )

        if result.success:
            console.print(f"[green]✓[/green] {result.output}")
        else:
            console.print(f"[yellow]![/yellow] {result.output}")

    asyncio.run(execute())


# Fine-tuning Pipeline Commands
@cli.group()
def finetune():
    """Fine-tune local LLMs based on session feedback.

    Commands for the complete fine-tuning pipeline:
    - prepare: Curate and prepare training data
    - train: Start model training
    - models: List fine-tuned models
    - evaluate: Benchmark model performance
    - compare: Compare two models
    - deploy: Set a model as active
    """
    pass


@finetune.command("prepare")
@click.option("--min-rating", default=4, help="Minimum feedback rating (1-5)")
@click.option("--max-sessions", default=500, help="Maximum sessions to include")
@click.option("--deduplicate/--no-deduplicate", default=True, help="Enable deduplication")
@click.option("--balance/--no-balance", default=False, help="Balance across categories")
def finetune_prepare(
    min_rating: int,
    max_sessions: int,
    deduplicate: bool,
    balance: bool,
):
    """Prepare and curate training data.

    Analyzes sessions with positive feedback and prepares them
    for fine-tuning. Shows statistics about available training data.

    Examples:

        sindri finetune prepare

        sindri finetune prepare --min-rating 5

        sindri finetune prepare --balance --max-sessions 200
    """
    from sindri.finetuning.curator import DataCurator, CurationConfig

    async def run():
        curator = DataCurator()

        config = CurationConfig(
            min_rating=min_rating,
            deduplicate=deduplicate,
            balance_categories=balance,
        )

        # Get curation stats first
        console.print("[bold]Training Data Analysis[/bold]\n")

        stats = await curator.get_curation_stats()
        console.print(f"Total rated sessions: {stats['total_rated_sessions']}")
        console.print(f"Training candidates (4+ stars): {stats['training_candidates']}")

        if stats['category_distribution']:
            console.print("\n[bold]Task Categories:[/bold]")
            for cat, count in sorted(
                stats['category_distribution'].items(), key=lambda x: x[1], reverse=True
            ):
                console.print(f"  {cat}: {count}")

        # Curate the dataset
        console.print("\n[bold]Curating dataset...[/bold]")
        dataset = await curator.curate(config)

        if not dataset.sessions:
            console.print("[yellow]No sessions meet the criteria[/yellow]")
            console.print("Try lowering --min-rating or collecting more feedback")
            return

        # Limit to max_sessions
        if len(dataset.sessions) > max_sessions:
            dataset.sessions = dataset.sessions[:max_sessions]

        console.print(f"\n[green]✓ Curated {len(dataset.sessions)} sessions[/green]")
        console.print(f"Total turns: {dataset.total_turns}")
        console.print(f"Avg quality score: {dataset.avg_quality_score:.3f}")

        if dataset.category_distribution:
            console.print("\n[bold]Curated Categories:[/bold]")
            for cat, count in sorted(
                dataset.category_distribution.items(), key=lambda x: x[1], reverse=True
            ):
                console.print(f"  {cat}: {count}")

        console.print(
            "\n[dim]Run 'sindri finetune train' to start training[/dim]"
        )

    asyncio.run(run())


@finetune.command("train")
@click.option(
    "--base-model",
    "-b",
    default="qwen2.5-coder:7b",
    help="Base Ollama model for fine-tuning",
)
@click.option("--name", "-n", help="Name for the fine-tuned model")
@click.option("--description", "-d", default="", help="Model description")
@click.option("--min-rating", default=4, help="Minimum feedback rating (1-5)")
@click.option("--max-sessions", default=500, help="Maximum sessions to include")
@click.option("--context-length", default=4096, help="Context window size")
@click.option("--temperature", default=0.7, help="Default temperature")
@click.option("--dry-run", is_flag=True, help="Prepare data without training")
@click.option("--tag", multiple=True, help="Tags for the model")
def finetune_train(
    base_model: str,
    name: str,
    description: str,
    min_rating: int,
    max_sessions: int,
    context_length: int,
    temperature: float,
    dry_run: bool,
    tag: tuple,
):
    """Start fine-tuning a model.

    Curates training data from rated sessions and creates a
    fine-tuned model via Ollama.

    Examples:

        sindri finetune train --base-model qwen2.5-coder:7b

        sindri finetune train --name my-coder --min-rating 5

        sindri finetune train --dry-run
    """
    from datetime import datetime
    from pathlib import Path
    from sindri.finetuning.trainer import TrainingOrchestrator, TrainingConfig

    # Generate model name if not provided
    if not name:
        base_name = base_model.split(":")[0].replace(".", "-")
        timestamp = datetime.now().strftime("%Y%m%d")
        name = f"sindri-{base_name}-{timestamp}"

    config = TrainingConfig(
        base_model=base_model,
        model_name=name,
        description=description,
        min_rating=min_rating,
        max_sessions=max_sessions,
        context_length=context_length,
        temperature=temperature,
        tags=list(tag),
    )

    async def run():
        orchestrator = TrainingOrchestrator()

        console.print(f"[bold]Fine-tuning Configuration[/bold]")
        console.print(f"  Base model: {base_model}")
        console.print(f"  Model name: {name}")
        console.print(f"  Min rating: {min_rating}")
        console.print(f"  Max sessions: {max_sessions}")

        if dry_run:
            console.print("[yellow]  Dry run mode - will not train[/yellow]")

        console.print()

        def on_progress(job):
            status = job.status.value
            progress = job.progress
            console.print(f"[dim]Progress: {status} ({progress:.0f}%)[/dim]")

        orchestrator.on_progress(on_progress)

        with console.status("[bold green]Training..."):
            job = await orchestrator.start_training(config, dry_run=dry_run)

        if job.status.value == "completed":
            console.print(f"\n[green]✓ Training completed![/green]")
            console.print(f"  Model ID: {job.model_id}")
            console.print(f"  Sessions used: {len(job.dataset.sessions) if job.dataset else 0}")
            if job.training_data_path:
                console.print(f"  Training data: {job.training_data_path}")
            if job.modelfile_path:
                console.print(f"  Modelfile: {job.modelfile_path}")

            if not dry_run:
                console.print(f"\n[dim]Run with: ollama run {name}[/dim]")
                console.print(f"[dim]Or deploy: sindri finetune deploy {job.model_id}[/dim]")
        else:
            console.print(f"\n[red]✗ Training failed: {job.error}[/red]")

    asyncio.run(run())


@finetune.command("models")
@click.option(
    "--status",
    "-s",
    type=click.Choice(["training", "ready", "active", "archived", "failed"]),
    help="Filter by status",
)
@click.option("--limit", default=20, help="Maximum number of models to show")
def finetune_models(status: str, limit: int):
    """List fine-tuned models.

    Shows all registered fine-tuned models with their status,
    training metrics, and version information.

    Examples:

        sindri finetune models

        sindri finetune models --status ready

        sindri finetune models --limit 50
    """
    from rich.table import Table
    from sindri.finetuning.registry import ModelRegistry, ModelStatus

    async def run():
        registry = ModelRegistry()

        status_filter = ModelStatus(status) if status else None
        models = await registry.list_models(status=status_filter, limit=limit)

        if not models:
            console.print("[yellow]No fine-tuned models found[/yellow]")
            console.print("[dim]Run 'sindri finetune train' to create one[/dim]")
            return

        table = Table(title="Fine-tuned Models")
        table.add_column("ID", style="dim")
        table.add_column("Name")
        table.add_column("Version")
        table.add_column("Status")
        table.add_column("Base Model")
        table.add_column("Sessions")
        table.add_column("Created")

        for model in models:
            status_style = {
                "training": "yellow",
                "ready": "green",
                "active": "bold green",
                "archived": "dim",
                "failed": "red",
            }.get(model.status.value, "")

            table.add_row(
                str(model.id),
                model.name,
                f"v{model.version}",
                f"[{status_style}]{model.status.value}[/{status_style}]",
                model.params.base_model,
                str(model.metrics.sessions_used),
                model.created_at.strftime("%Y-%m-%d"),
            )

        console.print(table)

        # Show active model
        active = await registry.get_active()
        if active:
            console.print(f"\n[bold]Active model:[/bold] {active.name} (ID: {active.id})")

    asyncio.run(run())


@finetune.command("evaluate")
@click.argument("model_name")
@click.option("--quick", is_flag=True, help="Quick evaluation with fewer prompts")
@click.option("--timeout", default=60.0, help="Timeout per prompt in seconds")
def finetune_evaluate(model_name: str, quick: bool, timeout: float):
    """Evaluate a model's performance.

    Runs benchmark prompts against the model and measures
    quality metrics.

    Examples:

        sindri finetune evaluate sindri-coder-v1

        sindri finetune evaluate qwen2.5-coder:7b --quick
    """
    from rich.table import Table
    from sindri.finetuning.evaluator import ModelEvaluator, BenchmarkSuite

    async def run():
        evaluator = ModelEvaluator()

        console.print(f"[bold]Evaluating model: {model_name}[/bold]\n")

        if quick:
            with console.status("[bold green]Running quick evaluation..."):
                result = await evaluator.quick_evaluate(model_name)

            console.print(f"Prompts tested: {result['prompts_tested']}")
            console.print(f"Average score: {result['avg_score']:.3f}")
            console.print(f"Average response time: {result['avg_response_time_ms']:.0f}ms")
            status = "[green]PASSED[/green]" if result['all_passed'] else "[yellow]MIXED[/yellow]"
            console.print(f"Status: {status}")
        else:
            suite = BenchmarkSuite.default_coding_suite()

            with console.status(
                f"[bold green]Running {len(suite.prompts)} benchmarks..."
            ):
                results = await evaluator.evaluate_model(
                    model_name, suite, timeout=timeout
                )

            # Show results table
            table = Table(title="Evaluation Results")
            table.add_column("Prompt")
            table.add_column("Category")
            table.add_column("Score")
            table.add_column("Patterns")
            table.add_column("Time")

            for r in results:
                score_style = "green" if r.score >= 0.7 else "yellow" if r.score >= 0.4 else "red"
                table.add_row(
                    r.prompt_id,
                    suite.prompts[[p.id for p in suite.prompts].index(r.prompt_id)].category
                    if r.prompt_id in [p.id for p in suite.prompts]
                    else "-",
                    f"[{score_style}]{r.score:.2f}[/{score_style}]",
                    f"{r.passed_patterns}/{r.passed_patterns + r.failed_patterns}",
                    f"{r.response_time_ms:.0f}ms",
                )

            console.print(table)

            # Summary
            avg_score = sum(r.score for r in results) / len(results)
            avg_time = sum(r.response_time_ms for r in results) / len(results)

            console.print(f"\n[bold]Summary:[/bold]")
            console.print(f"  Average score: {avg_score:.3f}")
            console.print(f"  Average time: {avg_time:.0f}ms")
            console.print(f"  Passed (≥0.5): {sum(1 for r in results if r.score >= 0.5)}/{len(results)}")

    asyncio.run(run())


@finetune.command("compare")
@click.argument("model_a")
@click.argument("model_b")
@click.option("--quick", is_flag=True, help="Quick comparison with fewer prompts")
def finetune_compare(model_a: str, model_b: str, quick: bool):
    """Compare two models head-to-head.

    Runs the same benchmarks against both models and shows
    which performs better.

    Examples:

        sindri finetune compare qwen2.5-coder:7b sindri-coder-v1

        sindri finetune compare base-model finetuned-model --quick
    """
    from sindri.finetuning.evaluator import ModelEvaluator, BenchmarkSuite

    async def run():
        evaluator = ModelEvaluator()

        console.print(f"[bold]Comparing models:[/bold]")
        console.print(f"  Model A: {model_a}")
        console.print(f"  Model B: {model_b}\n")

        suite = BenchmarkSuite.quick_suite() if quick else BenchmarkSuite.default_coding_suite()

        with console.status(f"[bold green]Running comparison ({len(suite.prompts)} prompts)..."):
            comparison = await evaluator.compare_models(model_a, model_b, suite)

        # Show results
        summary = comparison.summary

        console.print(f"\n[bold]Results:[/bold]")
        console.print(f"\n  {model_a}:")
        console.print(f"    Score: {summary['model_a']['avg_score']:.3f}")
        console.print(f"    Response time: {summary['model_a']['avg_response_time_ms']:.0f}ms")
        console.print(f"    Wins: {summary['model_a']['prompt_wins']}")

        console.print(f"\n  {model_b}:")
        console.print(f"    Score: {summary['model_b']['avg_score']:.3f}")
        console.print(f"    Response time: {summary['model_b']['avg_response_time_ms']:.0f}ms")
        console.print(f"    Wins: {summary['model_b']['prompt_wins']}")

        console.print(f"\n  Ties: {summary['ties']}")

        # Winner
        if comparison.winner:
            style = "green" if comparison.winner == model_b else "blue"
            console.print(f"\n[bold {style}]Winner: {comparison.winner}[/bold {style}]")
            console.print(f"  Score difference: {abs(summary['score_diff']):.3f}")
        else:
            console.print(f"\n[yellow]Result: Too close to call[/yellow]")

    asyncio.run(run())


@finetune.command("deploy")
@click.argument("model_id", type=int)
def finetune_deploy(model_id: int):
    """Deploy a fine-tuned model as the active model.

    Sets the specified model as the active/default model for
    Sindri operations.

    Examples:

        sindri finetune deploy 1

        sindri finetune deploy 5
    """
    from sindri.finetuning.registry import ModelRegistry

    async def run():
        registry = ModelRegistry()

        model = await registry.get_by_id(model_id)
        if not model:
            console.print(f"[red]Model ID {model_id} not found[/red]")
            return

        if model.status.value not in ("ready", "active"):
            console.print(f"[red]Model is not ready (status: {model.status.value})[/red]")
            return

        success = await registry.set_active(model_id)

        if success:
            console.print(f"[green]✓ Model '{model.name}' is now active[/green]")
            console.print(f"  Ollama name: {model.ollama_name}")
            console.print(f"\n[dim]Use with: ollama run {model.ollama_name}[/dim]")
        else:
            console.print(f"[red]Failed to activate model[/red]")

    asyncio.run(run())


@finetune.command("stats")
def finetune_stats():
    """Show fine-tuning pipeline statistics.

    Displays information about training data, registered models,
    and training jobs.
    """
    from sindri.finetuning.trainer import TrainingOrchestrator

    async def run():
        orchestrator = TrainingOrchestrator()

        stats = await orchestrator.get_training_stats()

        console.print("[bold]Fine-tuning Pipeline Statistics[/bold]\n")

        # Curation stats
        curation = stats['curation']
        console.print("[bold]Training Data:[/bold]")
        console.print(f"  Total rated sessions: {curation['total_rated_sessions']}")
        console.print(f"  Training candidates (4+): {curation['training_candidates']}")

        if curation['rating_distribution']:
            console.print("  Rating distribution:")
            for rating, count in sorted(curation['rating_distribution'].items()):
                console.print(f"    {rating}★: {count}")

        # Registry stats
        registry = stats['registry']
        console.print("\n[bold]Model Registry:[/bold]")
        console.print(f"  Total models: {registry['total_models']}")
        if registry['active_model']:
            console.print(f"  Active model: {registry['active_model']}")

        if registry['status_distribution']:
            console.print("  By status:")
            for status, count in registry['status_distribution'].items():
                console.print(f"    {status}: {count}")

        # Jobs stats
        jobs = stats['jobs']
        console.print("\n[bold]Training Jobs:[/bold]")
        console.print(f"  Total jobs: {jobs['total']}")
        if jobs['by_status']:
            for status, count in jobs['by_status'].items():
                console.print(f"    {status}: {count}")

    asyncio.run(run())


@finetune.command("info")
@click.argument("model_id", type=int)
def finetune_info(model_id: int):
    """Show detailed information about a fine-tuned model.

    Examples:

        sindri finetune info 1
    """
    from rich.panel import Panel
    from sindri.finetuning.registry import ModelRegistry

    async def run():
        registry = ModelRegistry()

        model = await registry.get_by_id(model_id)
        if not model:
            console.print(f"[red]Model ID {model_id} not found[/red]")
            return

        console.print(Panel(f"[bold]{model.name}[/bold] v{model.version}", title="Model Info"))

        console.print(f"[bold]General:[/bold]")
        console.print(f"  ID: {model.id}")
        console.print(f"  Status: {model.status.value}")
        console.print(f"  Description: {model.description or '(none)'}")
        console.print(f"  Created: {model.created_at.strftime('%Y-%m-%d %H:%M')}")
        console.print(f"  Tags: {', '.join(model.tags) if model.tags else '(none)'}")

        console.print(f"\n[bold]Training Parameters:[/bold]")
        console.print(f"  Base model: {model.params.base_model}")
        console.print(f"  Context length: {model.params.context_length}")
        console.print(f"  Temperature: {model.params.temperature}")
        if model.params.quantization:
            console.print(f"  Quantization: {model.params.quantization}")

        console.print(f"\n[bold]Training Metrics:[/bold]")
        console.print(f"  Sessions used: {model.metrics.sessions_used}")
        console.print(f"  Tokens trained: {model.metrics.tokens_trained}")
        if model.metrics.training_time_seconds:
            console.print(f"  Training time: {model.metrics.training_time_seconds:.1f}s")
        if model.metrics.training_loss:
            console.print(f"  Training loss: {model.metrics.training_loss:.4f}")

        console.print(f"\n[bold]Paths:[/bold]")
        console.print(f"  Ollama name: {model.ollama_name or '(not created)'}")
        console.print(f"  Training data: {model.training_data_path or '(none)'}")
        console.print(f"  Modelfile: {model.modelfile_path or '(none)'}")

    asyncio.run(run())


@finetune.command("delete")
@click.argument("model_id", type=int)
@click.option("--force", "-f", is_flag=True, help="Delete without confirmation")
def finetune_delete(model_id: int, force: bool):
    """Delete a fine-tuned model from the registry.

    Note: This removes the registry entry but does not delete
    the Ollama model. Use 'ollama rm' to remove the actual model.

    Examples:

        sindri finetune delete 1

        sindri finetune delete 1 --force
    """
    from sindri.finetuning.registry import ModelRegistry

    async def run():
        registry = ModelRegistry()

        model = await registry.get_by_id(model_id)
        if not model:
            console.print(f"[red]Model ID {model_id} not found[/red]")
            return

        if not force:
            console.print(f"Delete model '{model.name}' (ID: {model_id})?")
            confirm = click.confirm("Are you sure?")
            if not confirm:
                console.print("[dim]Cancelled[/dim]")
                return

        # Archive instead of hard delete
        success = await registry.archive(model_id)

        if success:
            console.print(f"[green]✓ Model archived (ID: {model_id})[/green]")
            if model.ollama_name:
                console.print(f"[dim]To remove Ollama model: ollama rm {model.ollama_name}[/dim]")
        else:
            console.print(f"[red]Failed to archive model[/red]")

    asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════════════
# Diagram Generation Commands (Phase 11)
# ═══════════════════════════════════════════════════════════════════════════════


@cli.group()
def diagram():
    """Generate technical diagrams (Mermaid, PlantUML, D2)."""
    pass


@diagram.command("mermaid")
@click.argument("diagram_type", type=click.Choice(["sequence", "class", "flowchart", "er", "state", "gantt", "mindmap"]))
@click.option("--title", "-t", help="Diagram title")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--direction", "-d", type=click.Choice(["TB", "LR", "BT", "RL"]), default="TB", help="Flowchart direction")
def diagram_mermaid(diagram_type: str, title: str, output: str, direction: str):
    """Generate a Mermaid diagram.

    Examples:

        sindri diagram mermaid sequence --title "Login Flow"

        sindri diagram mermaid flowchart -d LR -o diagram.md

        sindri diagram mermaid er --title "Database Schema"
    """
    from sindri.tools.diagrams import GenerateMermaidTool

    async def run():
        tool = GenerateMermaidTool()
        result = await tool.execute(
            diagram_type=diagram_type,
            title=title,
            output_file=output,
            direction=direction,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@diagram.command("plantuml")
@click.argument("diagram_type", type=click.Choice(["sequence", "class", "activity", "component", "usecase", "deployment"]))
@click.option("--title", "-t", help="Diagram title")
@click.option("--theme", help="PlantUML theme")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def diagram_plantuml(diagram_type: str, title: str, theme: str, output: str):
    """Generate a PlantUML diagram.

    Examples:

        sindri diagram plantuml sequence --title "API Flow"

        sindri diagram plantuml class --theme blueprint

        sindri diagram plantuml component -o architecture.puml
    """
    from sindri.tools.diagrams import GeneratePlantUMLTool

    async def run():
        tool = GeneratePlantUMLTool()
        result = await tool.execute(
            diagram_type=diagram_type,
            title=title,
            theme=theme,
            output_file=output,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@diagram.command("d2")
@click.option("--title", "-t", help="Diagram title")
@click.option("--direction", "-d", type=click.Choice(["right", "down", "left", "up"]), default="right", help="Layout direction")
@click.option("--theme", help="D2 theme ID (0-100)")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def diagram_d2(title: str, direction: str, theme: str, output: str):
    """Generate a D2 diagram.

    Examples:

        sindri diagram d2 --title "System Architecture"

        sindri diagram d2 -d down --theme 1

        sindri diagram d2 -o architecture.d2
    """
    from sindri.tools.diagrams import GenerateD2Tool

    async def run():
        tool = GenerateD2Tool()
        result = await tool.execute(
            title=title,
            direction=direction,
            theme=theme,
            output_file=output,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@diagram.command("from-code")
@click.argument("path", type=click.Path(exists=True))
@click.option("--type", "diagram_type", type=click.Choice(["class", "dependencies", "architecture", "call_graph"]), default="class", help="Diagram type")
@click.option("--format", "fmt", type=click.Choice(["mermaid", "plantuml", "d2"]), default="mermaid", help="Output format")
@click.option("--include-private", is_flag=True, help="Include private methods/attributes")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def diagram_from_code(path: str, diagram_type: str, fmt: str, include_private: bool, output: str):
    """Generate diagram from source code.

    Analyzes Python, JavaScript, TypeScript, Go, and Rust code.

    Examples:

        sindri diagram from-code src/models.py --type class

        sindri diagram from-code . --type architecture --format d2

        sindri diagram from-code lib/ --type dependencies -o deps.md
    """
    from pathlib import Path
    from sindri.tools.diagrams import DiagramFromCodeTool

    async def run():
        tool = DiagramFromCodeTool()

        path_obj = Path(path)
        if path_obj.is_file():
            result = await tool.execute(
                diagram_type=diagram_type,
                file_path=path,
                format=fmt,
                include_private=include_private,
                output_file=output,
            )
        else:
            result = await tool.execute(
                diagram_type=diagram_type,
                path=path,
                format=fmt,
                include_private=include_private,
                output_file=output,
            )

        if result.success:
            console.print(result.output)
            if result.metadata:
                console.print(f"\n[dim]Files analyzed: {result.metadata.get('files_analyzed', 0)}[/dim]")
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@diagram.command("sequence")
@click.option("--participants", "-p", multiple=True, help="Participant names (can specify multiple)")
@click.option("--format", "fmt", type=click.Choice(["mermaid", "plantuml"]), default="mermaid", help="Output format")
@click.option("--title", "-t", help="Diagram title")
@click.option("--autonumber", is_flag=True, help="Add step numbers")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def diagram_sequence(participants: tuple, fmt: str, title: str, autonumber: bool, output: str):
    """Generate a sequence diagram interactively.

    Examples:

        sindri diagram sequence -p User -p API -p Database

        sindri diagram sequence -p Client -p Server --title "Auth Flow" --autonumber

        sindri diagram sequence -p A -p B -p C --format plantuml -o flow.puml
    """
    from sindri.tools.diagrams import GenerateSequenceDiagramTool

    async def run():
        tool = GenerateSequenceDiagramTool()
        result = await tool.execute(
            participants=list(participants) if participants else None,
            format=fmt,
            title=title,
            autonumber=autonumber,
            output_file=output,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@diagram.command("er")
@click.argument("source", type=click.Path(exists=True), required=False)
@click.option("--format", "fmt", type=click.Choice(["mermaid", "plantuml", "d2"]), default="mermaid", help="Output format")
@click.option("--title", "-t", help="Diagram title")
@click.option("--show-types/--no-types", default=True, help="Show column types")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def diagram_er(source: str, fmt: str, title: str, show_types: bool, output: str):
    """Generate an ER diagram from database schema.

    SOURCE can be a Python file with SQLAlchemy models or a SQL file.

    Examples:

        sindri diagram er models.py

        sindri diagram er schema.sql --format plantuml

        sindri diagram er app/db/models.py --title "User DB" -o schema.md
    """
    from sindri.tools.diagrams import GenerateERDiagramTool

    async def run():
        tool = GenerateERDiagramTool()

        kwargs = {
            "format": fmt,
            "title": title,
            "show_types": show_types,
            "output_file": output,
        }

        if source:
            if source.endswith(".sql"):
                kwargs["sql_file"] = source
            else:
                kwargs["file_path"] = source

        result = await tool.execute(**kwargs)

        if result.success:
            console.print(result.output)
            if result.metadata:
                console.print(f"\n[dim]Tables found: {result.metadata.get('tables_count', 0)}[/dim]")
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════════════
# LaTeX Commands
# ═══════════════════════════════════════════════════════════════════════════════


@cli.group()
def latex():
    """Generate LaTeX documents, equations, and presentations."""
    pass


@latex.command("document")
@click.argument("title")
@click.option("--author", "-a", help="Author name")
@click.option("--class", "doc_class", type=click.Choice(["article", "report", "book"]), default="article", help="Document class")
@click.option("--style", "-s", type=click.Choice(["ieee", "acm", "apa", "plain"]), help="Academic paper style")
@click.option("--sections", "-S", multiple=True, help="Section titles")
@click.option("--abstract", help="Document abstract")
@click.option("--two-column", is_flag=True, help="Use two-column layout")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def latex_document(title: str, author: str, doc_class: str, style: str, sections: tuple, abstract: str, two_column: bool, output: str):
    """Generate a LaTeX document.

    Examples:

        sindri latex document "My Paper" --author "J. Smith"

        sindri latex document "Research" --style ieee --sections Introduction --sections Methods

        sindri latex document "Thesis" --class report -o thesis.tex
    """
    from sindri.tools.latex import GenerateLatexTool

    async def run():
        tool = GenerateLatexTool()
        result = await tool.execute(
            title=title,
            author=author,
            document_class=doc_class,
            style=style,
            sections=list(sections) if sections else None,
            abstract=abstract,
            two_column=two_column,
            output_file=output,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@latex.command("equation")
@click.argument("expression")
@click.option("--display", "-d", is_flag=True, help="Use display math mode")
@click.option("--numbered", "-n", is_flag=True, help="Add equation number")
@click.option("--label", "-l", help="LaTeX label for cross-referencing")
@click.option("--align", is_flag=True, help="Use align environment for multi-line")
def latex_equation(expression: str, display: bool, numbered: bool, label: str, align: bool):
    """Convert mathematical notation to LaTeX.

    Examples:

        sindri latex equation "x^2 + 2x + 1"

        sindri latex equation "integral from 0 to infinity of e^(-x) dx" --display

        sindri latex equation "alpha + beta = gamma" -d -n --label eq:greek
    """
    from sindri.tools.latex import FormatEquationsTool

    async def run():
        tool = FormatEquationsTool()
        result = await tool.execute(
            expression=expression,
            display=display,
            numbered=numbered,
            label=label,
            align=align,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@latex.command("tikz")
@click.argument("diagram_type", type=click.Choice(["graph", "neural_network", "flowchart", "tree", "plot", "timeline", "venn"]))
@click.option("--title", "-t", help="Diagram title")
@click.option("--scale", type=float, default=1.0, help="Scale factor")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def latex_tikz(diagram_type: str, title: str, scale: float, output: str):
    """Generate TikZ diagrams.

    Examples:

        sindri latex tikz neural_network

        sindri latex tikz graph --title "System Architecture"

        sindri latex tikz flowchart --scale 1.5 -o flow.tex
    """
    from sindri.tools.latex import GenerateTikzTool

    async def run():
        tool = GenerateTikzTool()
        result = await tool.execute(
            diagram_type=diagram_type,
            title=title,
            scale=scale,
            output_file=output,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@latex.command("beamer")
@click.argument("title")
@click.option("--author", "-a", help="Presenter name")
@click.option("--theme", "-t", type=click.Choice(["default", "Madrid", "Berlin", "Copenhagen", "Warsaw"]), default="Madrid", help="Beamer theme")
@click.option("--slides", "-s", multiple=True, help="Slide titles")
@click.option("--subtitle", help="Presentation subtitle")
@click.option("--institute", help="Institution/organization")
@click.option("--no-toc", is_flag=True, help="Skip table of contents")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def latex_beamer(title: str, author: str, theme: str, slides: tuple, subtitle: str, institute: str, no_toc: bool, output: str):
    """Generate a Beamer presentation.

    Examples:

        sindri latex beamer "My Talk" --author "J. Smith"

        sindri latex beamer "Workshop" --theme Berlin --slides Setup --slides Demo

        sindri latex beamer "Conference" -t Madrid --subtitle "A Great Talk" -o slides.tex
    """
    from sindri.tools.latex import CreateBeamerTool

    async def run():
        tool = CreateBeamerTool()
        result = await tool.execute(
            title=title,
            author=author,
            theme=theme,
            slides=list(slides) if slides else None,
            subtitle=subtitle,
            institute=institute,
            toc=not no_toc,
            output_file=output,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@latex.command("bib")
@click.argument("action", type=click.Choice(["create", "add", "list", "validate", "format"]))
@click.option("--file", "-f", "bib_file", type=click.Path(), help="Bibliography file path")
@click.option("--type", "entry_type", type=click.Choice(["article", "book", "inproceedings", "misc"]), help="Entry type (for add)")
@click.option("--key", "-k", help="Citation key")
@click.option("--author", "-a", help="Author(s)")
@click.option("--title", "-t", help="Title")
@click.option("--year", "-y", help="Year")
@click.option("--journal", "-j", help="Journal name")
@click.option("--doi", help="DOI")
def latex_bib(action: str, bib_file: str, entry_type: str, key: str, author: str, title: str, year: str, journal: str, doi: str):
    """Manage BibTeX bibliographies.

    Examples:

        sindri latex bib create -f refs.bib

        sindri latex bib add -f refs.bib --type article -a "Smith, J." -t "Great Paper" -y 2024

        sindri latex bib list -f refs.bib

        sindri latex bib validate -f refs.bib
    """
    from sindri.tools.latex import ManageBibliographyTool

    async def run():
        tool = ManageBibliographyTool()
        result = await tool.execute(
            action=action,
            bib_file=bib_file,
            output_file=bib_file if action == "create" else None,
            entry_type=entry_type,
            key=key,
            author=author,
            title=title,
            year=year,
            journal=journal,
            doi=doi,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@latex.command("compile")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output-dir", "-o", type=click.Path(), help="Output directory for PDF")
@click.option("--engine", "-e", type=click.Choice(["pdflatex", "xelatex", "lualatex"]), default="pdflatex", help="LaTeX engine")
@click.option("--bibtex", "-b", is_flag=True, help="Run BibTeX for bibliography")
@click.option("--passes", "-p", type=int, default=2, help="Number of compilation passes")
def latex_compile(input_file: str, output_dir: str, engine: str, bibtex: bool, passes: int):
    """Compile LaTeX document to PDF.

    Requires a LaTeX distribution (texlive, miktex) to be installed.

    Examples:

        sindri latex compile document.tex

        sindri latex compile paper.tex -b -o build/

        sindri latex compile thesis.tex --engine xelatex --passes 3
    """
    from sindri.tools.latex import LatexToPdfTool

    async def run():
        tool = LatexToPdfTool()
        result = await tool.execute(
            input_file=input_file,
            output_dir=output_dir,
            engine=engine,
            bibtex=bibtex,
            passes=passes,
        )

        if result.success:
            console.print(f"[green]{result.output}[/green]")
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════════════
# OpenSCAD 3D Modeling Commands (Phase 11)
# ═══════════════════════════════════════════════════════════════════════════════


@cli.group()
def scad():
    """Generate parametric 3D models for 3D printing using OpenSCAD."""
    pass


@scad.command("generate")
@click.argument("description")
@click.option("--width", "-w", type=float, help="Width/X dimension in mm")
@click.option("--height", "-h", type=float, help="Height/Z dimension in mm")
@click.option("--depth", "-d", type=float, help="Depth/Y dimension in mm")
@click.option("--wall", type=float, default=2.0, help="Wall thickness in mm (default: 2)")
@click.option("--units", type=click.Choice(["mm", "cm", "inch"]), default="mm", help="Measurement units")
@click.option("--output", "-o", type=click.Path(), help="Output .scad file path")
def scad_generate(description: str, width: float, height: float, depth: float, wall: float, units: str, output: str):
    """Generate OpenSCAD code from a text description.

    Examples:

        sindri scad generate "A box with lid" -w 50 -h 30 -d 40

        sindri scad generate "Phone stand with 60 degree angle"

        sindri scad generate "Gear with 24 teeth" -o gear.scad

        sindri scad generate "Enclosure for Raspberry Pi" --wall 2.5
    """
    from sindri.tools.openscad import GenerateSCADTool

    async def run():
        tool = GenerateSCADTool()
        result = await tool.execute(
            description=description,
            width=width,
            height=height,
            depth=depth,
            wall_thickness=wall,
            units=units,
            output_file=output,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@scad.command("preview")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--format", "-f", type=click.Choice(["png", "stl"]), default="png", help="Output format")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--size", "-s", default="800,600", help="Image size as width,height (for PNG)")
@click.option("--colorscheme", "-c", type=click.Choice(["Cornfield", "Metallic", "Sunset", "Starnight", "Nature"]), default="Cornfield", help="Color scheme")
def scad_preview(input_file: str, format: str, output: str, size: str, colorscheme: str):
    """Render an OpenSCAD model to PNG or STL preview.

    Requires OpenSCAD to be installed.

    Examples:

        sindri scad preview model.scad

        sindri scad preview model.scad -f stl -o preview.stl

        sindri scad preview model.scad --size 1920,1080 -c Metallic
    """
    from sindri.tools.openscad import RenderPreviewTool

    async def run():
        tool = RenderPreviewTool()
        result = await tool.execute(
            input_file=input_file,
            format=format,
            output_file=output,
            image_size=size,
            colorscheme=colorscheme,
        )

        if result.success:
            console.print(f"[green]{result.output}[/green]")
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@scad.command("export")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output STL file path")
@click.option("--quality", "-q", type=click.Choice(["draft", "normal", "high", "ultra"]), default="normal", help="Render quality")
def scad_export(input_file: str, output: str, quality: str):
    """Export an OpenSCAD model to STL for 3D printing.

    Requires OpenSCAD to be installed.

    Examples:

        sindri scad export model.scad

        sindri scad export model.scad -o print.stl

        sindri scad export model.scad --quality high
    """
    from sindri.tools.openscad import ExportSTLTool

    async def run():
        tool = ExportSTLTool()
        result = await tool.execute(
            input_file=input_file,
            output_file=output,
            quality=quality,
        )

        if result.success:
            console.print(f"[green]{result.output}[/green]")
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@scad.command("validate")
@click.argument("input_file", type=click.Path(exists=True))
def scad_validate(input_file: str):
    """Validate OpenSCAD code for syntax and geometry issues.

    Checks for common problems that cause print failures.

    Examples:

        sindri scad validate model.scad
    """
    from sindri.tools.openscad import ValidateSCADTool

    async def run():
        tool = ValidateSCADTool()
        result = await tool.execute(input_file=input_file)

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Validation errors found:[/red]")
            console.print(result.output)
            if result.error:
                console.print(f"[red]{result.error}[/red]")

    asyncio.run(run())


@scad.command("parametrize")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output file (default: overwrite input)")
@click.option("--prefix", "-p", default="", help="Prefix for generated parameter names")
def scad_parametrize(input_file: str, output: str, prefix: str):
    """Convert hardcoded values to parameters in an OpenSCAD file.

    Makes models more customizable.

    Examples:

        sindri scad parametrize model.scad

        sindri scad parametrize model.scad -o parametric.scad

        sindri scad parametrize model.scad --prefix box_
    """
    from sindri.tools.openscad import ParametrizeTool

    async def run():
        tool = ParametrizeTool()
        result = await tool.execute(
            input_file=input_file,
            output_file=output,
            prefix=prefix,
        )

        if result.success:
            console.print(f"[green]{result.output}[/green]")
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@scad.command("optimize")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--nozzle", type=float, default=0.4, help="Nozzle diameter in mm (default: 0.4)")
@click.option("--layer", type=float, default=0.2, help="Layer height in mm (default: 0.2)")
@click.option("--printer", type=click.Choice(["fdm", "sla", "sls"]), default="fdm", help="Printer type")
def scad_optimize(input_file: str, nozzle: float, layer: float, printer: str):
    """Analyze model and suggest optimizations for 3D printing.

    Checks wall thickness, overhangs, tolerances, etc.

    Examples:

        sindri scad optimize model.scad

        sindri scad optimize model.scad --nozzle 0.6 --layer 0.3

        sindri scad optimize model.scad --printer sla
    """
    from sindri.tools.openscad import OptimizePrintabilityTool

    async def run():
        tool = OptimizePrintabilityTool()
        result = await tool.execute(
            input_file=input_file,
            nozzle_diameter=nozzle,
            layer_height=layer,
            printer_type=printer,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════════════
# Data Visualization Commands (Phase 11)
# ═══════════════════════════════════════════════════════════════════════════════


@cli.group()
def viz():
    """Data visualization commands - analyze data and generate charts.

    Generate visualizations using D3.js, matplotlib, or Plotly.
    """
    pass


@viz.command("analyze")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--columns", "-c", multiple=True, help="Specific columns to analyze")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json"]), default="table")
def viz_analyze(file_path: str, columns: tuple, output_format: str):
    """Analyze a data file and show statistics.

    Supports CSV and JSON files. Shows column types, statistics, and correlations.

    Examples:

        sindri viz analyze sales.csv

        sindri viz analyze data.json -c revenue -c date

        sindri viz analyze data.csv --format json
    """
    from sindri.tools.dataviz import AnalyzeDataTool

    async def run():
        tool = AnalyzeDataTool()
        result = await tool.execute(
            file_path=file_path,
            columns=list(columns) if columns else None,
        )

        if result.success:
            if output_format == "json":
                # Extract metadata as JSON
                import json
                console.print(json.dumps(result.metadata, indent=2))
            else:
                console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@viz.command("suggest")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--goal", "-g", type=click.Choice(["comparison", "distribution", "relationship", "trend", "composition"]),
              help="Visualization goal to focus recommendations")
@click.option("--max", "-m", "max_suggestions", type=int, default=5, help="Maximum suggestions (default: 5)")
def viz_suggest(file_path: str, goal: str, max_suggestions: int):
    """Suggest appropriate visualizations for a dataset.

    Analyzes data structure and recommends chart types with rationale.

    Examples:

        sindri viz suggest sales.csv

        sindri viz suggest data.json --goal trend

        sindri viz suggest data.csv -g comparison -m 3
    """
    from sindri.tools.dataviz import SuggestVisualizationTool

    async def run():
        tool = SuggestVisualizationTool()
        result = await tool.execute(
            file_path=file_path,
            goal=goal,
            max_suggestions=max_suggestions,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@viz.command("d3")
@click.argument("chart_type", type=click.Choice(["bar", "line", "scatter", "pie", "heatmap", "histogram", "area"]))
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--x", "-x", required=True, help="Column for x-axis")
@click.option("--y", "-y", help="Column for y-axis")
@click.option("--color", "-c", help="Column for color grouping")
@click.option("--title", "-t", help="Chart title")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--width", "-w", type=int, default=800, help="Chart width (default: 800)")
@click.option("--height", "-h", "chart_height", type=int, default=500, help="Chart height (default: 500)")
def viz_d3(chart_type: str, file_path: str, x: str, y: str, color: str, title: str, output: str, width: int, chart_height: int):
    """Generate a D3.js interactive visualization.

    Creates JavaScript code for interactive charts with tooltips and animations.

    Examples:

        sindri viz d3 bar sales.csv -x category -y revenue

        sindri viz d3 line data.csv -x date -y value -t "Sales Trend"

        sindri viz d3 scatter data.csv -x x -y y -c category -o chart.js
    """
    from sindri.tools.dataviz import GenerateD3Tool

    async def run():
        tool = GenerateD3Tool()
        result = await tool.execute(
            chart_type=chart_type,
            file_path=file_path,
            x=x,
            y=y,
            color=color,
            title=title,
            output_file=output,
            width=width,
            height=chart_height,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@viz.command("matplotlib")
@click.argument("chart_type", type=click.Choice(["bar", "line", "scatter", "pie", "heatmap", "histogram", "box", "violin"]))
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--x", "-x", required=True, help="Column for x-axis")
@click.option("--y", "-y", help="Column for y-axis")
@click.option("--hue", help="Column for color grouping")
@click.option("--title", "-t", help="Chart title")
@click.option("--style", "-s", default="seaborn-v0_8-whitegrid", help="Matplotlib style")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def viz_matplotlib(chart_type: str, file_path: str, x: str, y: str, hue: str, title: str, style: str, output: str):
    """Generate Python matplotlib visualization code.

    Creates static chart code using matplotlib.pyplot.

    Examples:

        sindri viz matplotlib bar sales.csv -x category -y revenue

        sindri viz matplotlib histogram data.csv -x value

        sindri viz matplotlib scatter data.csv -x x -y y --hue category
    """
    from sindri.tools.dataviz import GenerateMatplotlibTool

    async def run():
        tool = GenerateMatplotlibTool()
        result = await tool.execute(
            chart_type=chart_type,
            file_path=file_path,
            x=x,
            y=y,
            hue=hue,
            title=title,
            style=style,
            output_file=output,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@viz.command("plotly")
@click.argument("chart_type", type=click.Choice([
    "bar", "line", "scatter", "pie", "heatmap", "histogram", "box", "violin", "scatter_3d", "surface", "sunburst", "treemap"
]))
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--x", "-x", required=True, help="Column for x-axis")
@click.option("--y", "-y", help="Column for y-axis")
@click.option("--z", "-z", help="Column for z-axis (3D charts)")
@click.option("--color", "-c", help="Column for color grouping")
@click.option("--title", "-t", help="Chart title")
@click.option("--language", "-l", type=click.Choice(["python", "javascript"]), default="python", help="Output language")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def viz_plotly(chart_type: str, file_path: str, x: str, y: str, z: str, color: str, title: str, language: str, output: str):
    """Generate Plotly interactive visualization code.

    Creates interactive charts using plotly.express (Python) or Plotly.js (JavaScript).

    Examples:

        sindri viz plotly scatter data.csv -x x -y y -c category

        sindri viz plotly scatter_3d data.csv -x x -y y -z z

        sindri viz plotly bar sales.csv -x category -y revenue -l javascript
    """
    from sindri.tools.dataviz import GeneratePlotlyTool

    async def run():
        tool = GeneratePlotlyTool()
        result = await tool.execute(
            chart_type=chart_type,
            file_path=file_path,
            x=x,
            y=y,
            z=z,
            color=color,
            title=title,
            language=language,
            output_file=output,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@viz.command("dashboard")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--config", "-c", type=click.Path(exists=True), help="Dashboard config JSON file")
@click.option("--output", "-o", required=True, type=click.Path(), help="Output file path")
@click.option("--title", "-t", help="Dashboard title")
@click.option("--format", "-f", "output_format", type=click.Choice(["html", "python"]), default="html", help="Output format")
@click.option("--rows", "-r", type=int, default=2, help="Grid rows (default: 2)")
@click.option("--cols", type=int, default=2, help="Grid columns (default: 2)")
def viz_dashboard(file_path: str, config: str, output: str, title: str, output_format: str, rows: int, cols: int):
    """Create a multi-chart dashboard.

    Arranges multiple charts in a grid layout.

    Config JSON format:
    {"charts": [{"type": "bar", "x": "col1", "y": "col2", "position": [0, 0]}]}

    Examples:

        sindri viz dashboard data.csv -c config.json -o dashboard.html

        sindri viz dashboard data.csv -o dash.py --format python -t "Sales Dashboard"
    """
    import json as json_module
    from sindri.tools.dataviz import CreateDashboardTool

    charts = []
    if config:
        with open(config) as f:
            charts = json_module.load(f).get("charts", [])

    async def run():
        tool = CreateDashboardTool()
        result = await tool.execute(
            file_path=file_path,
            charts=charts,
            title=title,
            output_format=output_format,
            output_file=output,
            rows=rows,
            cols=cols,
        )

        if result.success:
            console.print(f"[green]Dashboard created: {output}[/green]")
            if output_format == "python":
                console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@viz.command("export")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", required=True, type=click.Path(), help="Output HTML file path")
@click.option("--library", "-l", type=click.Choice(["d3", "plotly"]), default="d3", help="JS library")
@click.option("--title", "-t", help="Page title")
@click.option("--responsive/--no-responsive", default=True, help="Make chart responsive")
@click.option("--export-button/--no-export-button", default=True, help="Add PNG/SVG export button")
def viz_export(input_file: str, output: str, library: str, title: str, responsive: bool, export_button: bool):
    """Export visualization as standalone HTML.

    Creates a self-contained HTML file with embedded JavaScript.

    Examples:

        sindri viz export chart.js -o visualization.html

        sindri viz export chart.js -o viz.html -l plotly -t "My Chart"

        sindri viz export chart.js -o viz.html --no-export-button
    """
    from sindri.tools.dataviz import ExportInteractiveTool

    async def run():
        tool = ExportInteractiveTool()
        result = await tool.execute(
            file_path=input_file,
            library=library,
            title=title,
            responsive=responsive,
            include_export_button=export_button,
            output_file=output,
        )

        if result.success:
            console.print(f"[green]Exported: {output}[/green]")
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


# =============================================================================
# Archive and Compression Commands
# =============================================================================


@cli.group()
def archive():
    """Archive and compression commands.

    Create, extract, and manage archives (zip, tar) and compressed files (gzip, bz2, xz).
    """
    pass


@archive.command("create")
@click.argument("output", type=click.Path())
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--exclude", "-e", multiple=True, help="Patterns to exclude (e.g., '*.pyc')")
@click.option("--level", "-l", type=int, default=6, help="Compression level 0-9 (default: 6)")
def archive_create(output: str, paths: tuple, exclude: tuple, level: int):
    """Create an archive from files and directories.

    Format is determined by output extension: .zip, .tar, .tar.gz, .tar.bz2, .tar.xz

    Examples:

        sindri archive create backup.zip file1.txt file2.txt dir/

        sindri archive create data.tar.gz src/ -e '*.pyc' -e '__pycache__'

        sindri archive create release.zip dist/ -l 9
    """
    from sindri.tools.compression import ArchiveCreateTool

    async def run():
        tool = ArchiveCreateTool()
        result = await tool.execute(
            output=output,
            paths=list(paths),
            exclude=list(exclude) if exclude else None,
            compression_level=level,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@archive.command("extract")
@click.argument("archive_path", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output directory (default: current)")
@click.option("--files", "-f", multiple=True, help="Specific files to extract")
@click.option("--no-overwrite", is_flag=True, help="Don't overwrite existing files")
def archive_extract(archive_path: str, output: str, files: tuple, no_overwrite: bool):
    """Extract an archive to a directory.

    Auto-detects format from extension or file magic bytes.

    Examples:

        sindri archive extract backup.zip

        sindri archive extract data.tar.gz -o ./extracted/

        sindri archive extract archive.zip -f config.json -f data/
    """
    from sindri.tools.compression import ArchiveExtractTool

    async def run():
        tool = ArchiveExtractTool()
        result = await tool.execute(
            archive=archive_path,
            output_dir=output,
            files=list(files) if files else None,
            overwrite=not no_overwrite,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@archive.command("list")
@click.argument("archive_path", type=click.Path(exists=True))
@click.option("--detailed", "-d", is_flag=True, help="Show detailed info (size, date)")
def archive_list(archive_path: str, detailed: bool):
    """List contents of an archive.

    Examples:

        sindri archive list backup.zip

        sindri archive list data.tar.gz -d
    """
    from sindri.tools.compression import ArchiveListTool

    async def run():
        tool = ArchiveListTool()
        result = await tool.execute(
            archive=archive_path,
            detailed=detailed,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@archive.command("compress")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--format", "-f", "fmt", type=click.Choice(["gzip", "bz2", "xz", "brotli"]), required=True,
              help="Compression format")
@click.option("--output", "-o", type=click.Path(), help="Output path (default: input + extension)")
@click.option("--level", "-l", type=int, default=6, help="Compression level 1-9 (default: 6)")
def archive_compress(input_file: str, fmt: str, output: str, level: int):
    """Compress a single file.

    Examples:

        sindri archive compress data.json -f gzip

        sindri archive compress large.txt -f xz -l 9

        sindri archive compress file.txt -f bz2 -o compressed.bz2
    """
    from sindri.tools.compression import CompressFileTool

    async def run():
        tool = CompressFileTool()
        result = await tool.execute(
            input=input_file,
            format=fmt,
            output=output,
            level=level,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@archive.command("decompress")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output path (default: input without extension)")
@click.option("--format", "-f", "fmt", type=click.Choice(["gzip", "bz2", "xz", "brotli", "auto"]), default="auto",
              help="Compression format (default: auto-detect)")
def archive_decompress(input_file: str, output: str, fmt: str):
    """Decompress a compressed file.

    Auto-detects format from extension or magic bytes.

    Examples:

        sindri archive decompress data.json.gz

        sindri archive decompress file.xz -o restored.txt

        sindri archive decompress file.compressed -f bz2
    """
    from sindri.tools.compression import DecompressFileTool

    async def run():
        tool = DecompressFileTool()
        result = await tool.execute(
            input=input_file,
            output=output,
            format=fmt,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


# =============================================================================
# Image Manipulation Commands
# =============================================================================


@cli.group()
def image():
    """Image manipulation commands.

    Resize, crop, convert, rotate, and process images (JPEG, PNG, GIF, WebP, etc).
    """
    pass


@image.command("resize")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--width", "-w", type=int, help="Target width in pixels")
@click.option("--height", "-h", type=int, help="Target height in pixels")
@click.option("--scale", "-s", type=int, help="Scale percentage (e.g., 50 for half size)")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--maintain-aspect", "-m", is_flag=True, default=True, help="Maintain aspect ratio (default: true)")
@click.option("--quality", "-q", type=int, default=85, help="Output quality 1-100 for JPEG/WebP (default: 85)")
@click.option("--resample", "-r", type=click.Choice(["nearest", "bilinear", "bicubic", "lanczos"]),
              default="lanczos", help="Resampling method (default: lanczos)")
def image_resize(input_file: str, width: int, height: int, scale: int, output: str,
                 maintain_aspect: bool, quality: int, resample: str):
    """Resize an image to specified dimensions or scale.

    Examples:

        sindri image resize photo.jpg --width 800

        sindri image resize photo.jpg -w 640 -h 480

        sindri image resize photo.jpg --scale 50

        sindri image resize photo.jpg -w 1024 -m -o resized.jpg
    """
    from sindri.tools.images import ImageResizeTool

    if width is None and height is None and scale is None:
        console.print("[red]Error: Must specify --width, --height, or --scale[/red]")
        return

    async def run():
        tool = ImageResizeTool()
        result = await tool.execute(
            input=input_file,
            output=output,
            width=width,
            height=height,
            scale=scale,
            maintain_aspect=maintain_aspect,
            quality=quality,
            resample=resample,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@image.command("crop")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--x", type=int, required=True, help="X coordinate of top-left corner")
@click.option("--y", type=int, required=True, help="Y coordinate of top-left corner")
@click.option("--width", "-w", type=int, required=True, help="Crop width in pixels")
@click.option("--height", "-h", type=int, required=True, help="Crop height in pixels")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--quality", "-q", type=int, default=85, help="Output quality 1-100 for JPEG/WebP")
def image_crop(input_file: str, x: int, y: int, width: int, height: int, output: str, quality: int):
    """Crop an image to a specified region.

    Examples:

        sindri image crop photo.jpg --x 0 --y 0 --width 640 --height 480

        sindri image crop image.png --x 100 --y 100 -w 200 -h 200 -o cropped.png
    """
    from sindri.tools.images import ImageCropTool

    async def run():
        tool = ImageCropTool()
        result = await tool.execute(
            input=input_file,
            x=x,
            y=y,
            width=width,
            height=height,
            output=output,
            quality=quality,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@image.command("convert")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--format", "-f", "fmt", type=click.Choice(["jpeg", "png", "gif", "webp", "bmp", "tiff"]),
              required=True, help="Target format")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--quality", "-q", type=int, default=85, help="Output quality 1-100 for JPEG/WebP")
def image_convert(input_file: str, fmt: str, output: str, quality: int):
    """Convert an image to a different format.

    Examples:

        sindri image convert photo.jpg --format png

        sindri image convert image.png -f webp -q 90 -o compressed.webp

        sindri image convert old.bmp --format jpeg -o modern.jpg
    """
    from sindri.tools.images import ImageConvertTool

    async def run():
        tool = ImageConvertTool()
        result = await tool.execute(
            input=input_file,
            format=fmt,
            output=output,
            quality=quality,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@image.command("rotate")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--angle", "-a", type=float, required=True, help="Rotation angle in degrees (positive = counter-clockwise)")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--expand", "-e", is_flag=True, help="Expand image to fit rotated content")
@click.option("--fill", type=str, help="Fill color for areas outside rotated image (e.g., 'white', '#FF0000')")
@click.option("--quality", "-q", type=int, default=85, help="Output quality 1-100 for JPEG/WebP")
def image_rotate(input_file: str, angle: float, output: str, expand: bool, fill: str, quality: int):
    """Rotate an image by specified degrees.

    Examples:

        sindri image rotate photo.jpg --angle 90

        sindri image rotate photo.jpg -a 45 --expand

        sindri image rotate photo.png -a 30 --fill white -o rotated.png
    """
    from sindri.tools.images import ImageRotateTool

    async def run():
        tool = ImageRotateTool()
        result = await tool.execute(
            input=input_file,
            angle=angle,
            output=output,
            expand=expand,
            fill_color=fill,
            quality=quality,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@image.command("thumbnail")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--size", "-s", type=int, default=128, help="Maximum size for both dimensions (default: 128)")
@click.option("--max-width", type=int, help="Maximum width (use with --max-height for different aspect)")
@click.option("--max-height", type=int, help="Maximum height (use with --max-width for different aspect)")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--quality", "-q", type=int, default=85, help="Output quality 1-100 for JPEG/WebP")
def image_thumbnail(input_file: str, size: int, max_width: int, max_height: int, output: str, quality: int):
    """Generate a thumbnail from an image.

    Preserves aspect ratio while fitting within the specified dimensions.

    Examples:

        sindri image thumbnail photo.jpg

        sindri image thumbnail photo.jpg --size 256

        sindri image thumbnail photo.jpg --max-width 200 --max-height 150 -o thumb.jpg
    """
    from sindri.tools.images import ImageThumbnailTool

    async def run():
        tool = ImageThumbnailTool()
        result = await tool.execute(
            input=input_file,
            max_size=size if max_width is None and max_height is None else None,
            max_width=max_width,
            max_height=max_height,
            output=output,
            quality=quality,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@image.command("info")
@click.argument("input_file", type=click.Path(exists=True))
def image_info(input_file: str):
    """Get information and metadata from an image.

    Shows dimensions, format, mode, file size, and EXIF data if available.

    Examples:

        sindri image info photo.jpg

        sindri image info screenshot.png
    """
    from sindri.tools.images import ImageInfoTool

    async def run():
        tool = ImageInfoTool()
        result = await tool.execute(input=input_file)

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


# =============================================================================
# Document Processing Commands
# =============================================================================


@cli.group()
def doc():
    """Document processing commands - PDFs, spreadsheets, and OCR.

    Extract text from PDFs, convert to Markdown, merge/split PDFs,
    perform OCR on images, and read/write spreadsheet files.
    """
    pass


@doc.command("extract")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("-o", "--output", help="Output file path for extracted text")
@click.option("--start-page", type=int, default=1, help="Starting page (1-indexed)")
@click.option("--end-page", type=int, help="Ending page (1-indexed)")
@click.option("--ocr", is_flag=True, help="Use OCR for scanned documents")
@click.option("--ocr-lang", default="eng", help="OCR language code (default: eng)")
def doc_extract(input_file: str, output: str, start_page: int, end_page: int, ocr: bool, ocr_lang: str):
    """Extract text from a PDF file.

    Examples:

        sindri doc extract document.pdf

        sindri doc extract scanned.pdf --ocr

        sindri doc extract book.pdf --start-page 10 --end-page 20 -o chapter.txt
    """
    from sindri.tools.documents import PdfExtractTextTool

    async def run():
        tool = PdfExtractTextTool()
        result = await tool.execute(
            input=input_file,
            output=output,
            start_page=start_page,
            end_page=end_page,
            use_ocr=ocr,
            ocr_language=ocr_lang,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@doc.command("to-markdown")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("-o", "--output", help="Output Markdown file path")
@click.option("--start-page", type=int, default=1, help="Starting page (1-indexed)")
@click.option("--end-page", type=int, help="Ending page (1-indexed)")
@click.option("--images/--no-images", default=False, help="Include images")
def doc_to_markdown(input_file: str, output: str, start_page: int, end_page: int, images: bool):
    """Convert a PDF file to Markdown format.

    Attempts to preserve document structure including headers, paragraphs, and lists.

    Examples:

        sindri doc to-markdown document.pdf

        sindri doc to-markdown paper.pdf -o paper.md

        sindri doc to-markdown book.pdf --start-page 1 --end-page 50
    """
    from sindri.tools.documents import PdfToMarkdownTool

    async def run():
        tool = PdfToMarkdownTool()
        result = await tool.execute(
            input=input_file,
            output=output,
            start_page=start_page,
            end_page=end_page,
            include_images=images,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@doc.command("merge")
@click.option("-o", "--output", required=True, help="Output PDF file path")
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True))
def doc_merge(output: str, files: tuple):
    """Merge multiple PDF files into one.

    Files are merged in the order provided.

    Examples:

        sindri doc merge -o combined.pdf file1.pdf file2.pdf file3.pdf

        sindri doc merge -o book.pdf chapter*.pdf
    """
    from sindri.tools.documents import PdfMergeTool

    if len(files) < 2:
        console.print("[red]Error: At least 2 PDF files are required for merging[/red]")
        return

    async def run():
        tool = PdfMergeTool()
        result = await tool.execute(
            output=output,
            inputs=list(files),
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@doc.command("split")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("-o", "--output", help="Output file path (for single range)")
@click.option("-d", "--output-dir", help="Output directory for split files")
@click.option("--start-page", type=int, help="Starting page (1-indexed)")
@click.option("--end-page", type=int, help="Ending page (1-indexed)")
@click.option("--ranges", help="Comma-separated page ranges (e.g., '1-5,6-10')")
@click.option("--single-pages", is_flag=True, help="Split into individual pages")
def doc_split(input_file: str, output: str, output_dir: str, start_page: int, end_page: int, ranges: str, single_pages: bool):
    """Split a PDF file by page ranges.

    Examples:

        sindri doc split document.pdf --single-pages

        sindri doc split book.pdf --start-page 1 --end-page 10 -o chapter1.pdf

        sindri doc split book.pdf --ranges "1-10,11-20,21-30" -d ./chapters/
    """
    from sindri.tools.documents import PdfSplitTool

    async def run():
        tool = PdfSplitTool()
        result = await tool.execute(
            input=input_file,
            output=output,
            output_dir=output_dir,
            start_page=start_page,
            end_page=end_page,
            ranges=ranges,
            single_pages=single_pages,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@doc.command("ocr")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("-o", "--output", help="Output file path for extracted text")
@click.option("-l", "--language", default="eng", help="OCR language code (default: eng)")
@click.option("--config", default="", help="Additional tesseract config options")
def doc_ocr(input_file: str, output: str, language: str, config: str):
    """Extract text from an image using OCR.

    Requires tesseract-ocr to be installed on the system.

    Examples:

        sindri doc ocr scan.png

        sindri doc ocr document.jpg -o extracted.txt

        sindri doc ocr german.png -l deu
    """
    from sindri.tools.documents import OcrImageTool

    async def run():
        tool = OcrImageTool()
        result = await tool.execute(
            input=input_file,
            output=output,
            language=language,
            config=config,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@doc.command("read")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("-s", "--sheet", help="Sheet name for Excel files")
@click.option("-c", "--columns", multiple=True, help="Columns to include")
@click.option("-n", "--limit", type=int, help="Maximum number of rows")
@click.option("--skip", type=int, default=0, help="Number of rows to skip")
@click.option("-f", "--format", "output_format", type=click.Choice(["table", "json", "csv"]), default="table", help="Output format")
def doc_read(input_file: str, sheet: str, columns: tuple, limit: int, skip: int, output_format: str):
    """Read data from a spreadsheet file (CSV, Excel).

    Examples:

        sindri doc read data.csv

        sindri doc read report.xlsx -s "Sales"

        sindri doc read large.csv -n 100 -f json

        sindri doc read data.xlsx -c name -c email -c phone
    """
    from sindri.tools.documents import SpreadsheetReadTool

    async def run():
        tool = SpreadsheetReadTool()
        result = await tool.execute(
            input=input_file,
            sheet=sheet,
            columns=list(columns) if columns else None,
            limit=limit,
            skip_rows=skip,
            output_format=output_format,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@doc.command("write")
@click.argument("output_file", type=click.Path())
@click.option("-d", "--data", required=True, help="JSON data to write")
@click.option("-s", "--sheet", default="Sheet1", help="Sheet name for Excel files")
@click.option("--index/--no-index", default=False, help="Include row index")
def doc_write(output_file: str, data: str, sheet: str, index: bool):
    """Write data to a spreadsheet file (CSV, Excel).

    Data should be provided as a JSON array of objects.

    Examples:

        sindri doc write output.csv -d '[{"name": "John", "age": 30}]'

        sindri doc write report.xlsx -d '[{"col1": 1, "col2": 2}]' -s "Data"
    """
    from sindri.tools.documents import SpreadsheetWriteTool

    async def run():
        tool = SpreadsheetWriteTool()
        result = await tool.execute(
            output=output_file,
            data=data,
            sheet=sheet,
            include_index=index,
        )

        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


# =============================================================================
# System Access Configuration (Milestone 5)
# =============================================================================


@cli.group()
def access():
    """Manage system access level and permissions.

    Sindri supports three access levels:

    \b
    - RESTRICTED: Read-only system info, no modifications
    - SUPERVISED: Modifications require user confirmation
    - FULL: Full autonomous access (for dedicated research machines)
    """
    pass


@access.command("show")
def access_show():
    """Show current system access configuration."""
    from rich.panel import Panel

    from sindri.config import SindriConfig, SystemAccessLevel

    config = SindriConfig.load()

    console.print(Panel("[bold]System Access Configuration[/bold]", expand=False))
    console.print()

    # Access level with color coding
    level_colors = {
        "restricted": "red",
        "supervised": "yellow",
        "full": "green",
    }
    level = config.system_access.value
    color = level_colors.get(level, "white")
    console.print(f"  [bold]Access Level:[/bold] [{color}]{level.upper()}[/{color}]")

    # Allowed services
    services_str = ", ".join(config.allowed_services) if config.allowed_services else "(none)"
    console.print(f"  [bold]Allowed Services:[/bold] {services_str}")

    # Self-modification
    self_mod = "[green]Yes[/green]" if config.allow_self_modification else "[red]No[/red]"
    console.print(f"  [bold]Self-Modification:[/bold] {self_mod}")

    # Level descriptions
    console.print()
    console.print("[dim]Access Level Descriptions:[/dim]")
    console.print("  [red]RESTRICTED[/red] - Read-only system info, no modifications")
    console.print("  [yellow]SUPERVISED[/yellow] - Modifications require confirmation prompts")
    console.print("  [green]FULL[/green] - Full autonomous access (dedicated machine only)")


@access.command("set")
@click.argument("level", type=click.Choice(["restricted", "supervised", "full"]))
@click.option("--force", "-f", is_flag=True, help="Skip confirmation for FULL access")
def access_set(level: str, force: bool = False):
    """Set the system access level.

    \b
    Examples:
        sindri access set restricted
        sindri access set supervised
        sindri access set full --force
    """
    from pathlib import Path

    from sindri.config import SindriConfig, SystemAccessLevel

    config = SindriConfig.load()
    old_level = config.system_access.value

    if old_level == level:
        console.print(f"[dim]Access level already set to {level.upper()}[/dim]")
        return

    # Warn about FULL access
    if level == "full" and not force:
        console.print()
        console.print("[yellow]Warning:[/yellow] FULL access grants autonomous system control.")
        console.print("This should only be used on a dedicated research machine.")
        console.print()
        if not click.confirm("Set access level to FULL?", default=False):
            console.print("[dim]Cancelled[/dim]")
            return

    config.system_access = SystemAccessLevel(level)

    # Save to default config location
    config_path = Path.home() / ".sindri" / "config.toml"
    config.save(str(config_path))

    console.print(f"[green]Access level changed: {old_level.upper()} -> {level.upper()}[/green]")
    console.print(f"[dim]Saved to: {config_path}[/dim]")


@access.command("services")
@click.option("--add", "-a", multiple=True, help="Add service to allowed list")
@click.option("--remove", "-r", multiple=True, help="Remove service from allowed list")
@click.option("--list", "-l", "list_only", is_flag=True, help="List allowed services only")
def access_services(add: tuple, remove: tuple, list_only: bool = False):
    """Manage the list of allowed services.

    Services in this list can be managed (started, stopped, restarted) when
    access level is SUPERVISED or FULL.

    \b
    Examples:
        sindri access services --list
        sindri access services --add docker --add nginx
        sindri access services --remove nginx
    """
    from pathlib import Path

    from sindri.config import SindriConfig

    config = SindriConfig.load()

    if list_only or (not add and not remove):
        console.print("[bold]Allowed Services:[/bold]")
        if config.allowed_services:
            for service in sorted(config.allowed_services):
                console.print(f"  - {service}")
        else:
            console.print("  [dim](none)[/dim]")
        return

    services = set(config.allowed_services)
    modified = False

    for service in add:
        if service not in services:
            services.add(service)
            console.print(f"[green]+ Added: {service}[/green]")
            modified = True
        else:
            console.print(f"[dim]Already present: {service}[/dim]")

    for service in remove:
        if service in services:
            services.remove(service)
            console.print(f"[red]- Removed: {service}[/red]")
            modified = True
        else:
            console.print(f"[yellow]Not found: {service}[/yellow]")

    if modified:
        config.allowed_services = sorted(services)
        config_path = Path.home() / ".sindri" / "config.toml"
        config.save(str(config_path))
        console.print(f"\n[dim]Saved to: {config_path}[/dim]")


@access.command("self-modify")
@click.option("--enable", is_flag=True, help="Enable self-modification")
@click.option("--disable", is_flag=True, help="Disable self-modification")
def access_self_modify(enable: bool = False, disable: bool = False):
    """Enable or disable self-modification capability.

    When enabled, Sindri can modify its own configuration file.
    This is useful for autonomous operation on a dedicated machine.

    \b
    Examples:
        sindri access self-modify --enable
        sindri access self-modify --disable
    """
    from pathlib import Path

    from sindri.config import SindriConfig

    config = SindriConfig.load()

    if not enable and not disable:
        status = "[green]Enabled[/green]" if config.allow_self_modification else "[red]Disabled[/red]"
        console.print(f"[bold]Self-Modification:[/bold] {status}")
        return

    if enable and disable:
        console.print("[red]Cannot use both --enable and --disable[/red]")
        return

    new_value = enable
    if config.allow_self_modification == new_value:
        status = "enabled" if new_value else "disabled"
        console.print(f"[dim]Self-modification already {status}[/dim]")
        return

    config.allow_self_modification = new_value
    config_path = Path.home() / ".sindri" / "config.toml"
    config.save(str(config_path))

    status = "[green]enabled[/green]" if new_value else "[red]disabled[/red]"
    console.print(f"Self-modification {status}")
    console.print(f"[dim]Saved to: {config_path}[/dim]")


# =============================================================================
# Service Management (Milestone 6)
# =============================================================================


@cli.group()
def service():
    """Manage systemd services.

    Check status, start/stop, view logs, and manage services.
    Operations are gated by your access level configuration.
    """
    pass


@service.command("status")
@click.argument("name")
@click.option("--user", "-u", is_flag=True, help="User service (systemctl --user)")
def service_status_cmd(name: str, user: bool = False):
    """Check status of a service.

    \b
    Examples:
        sindri service status ollama
        sindri service status syncthing --user
    """
    from sindri.tools.services import ServiceStatusTool

    async def run():
        tool = ServiceStatusTool()
        result = await tool.execute(service=name, user=user)
        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@service.command("start")
@click.argument("name")
@click.option("--user", "-u", is_flag=True, help="User service (systemctl --user)")
def service_start_cmd(name: str, user: bool = False):
    """Start a service.

    \b
    Examples:
        sindri service start ollama
    """
    from sindri.tools.services import ServiceStartTool

    async def run():
        tool = ServiceStartTool()
        result = await tool.execute(service=name, user=user)
        if result.success:
            console.print(f"[green]{result.output}[/green]")
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@service.command("stop")
@click.argument("name")
@click.option("--user", "-u", is_flag=True, help="User service (systemctl --user)")
def service_stop_cmd(name: str, user: bool = False):
    """Stop a service.

    \b
    Examples:
        sindri service stop ollama
    """
    from sindri.tools.services import ServiceStopTool

    async def run():
        tool = ServiceStopTool()
        result = await tool.execute(service=name, user=user)
        if result.success:
            console.print(f"[green]{result.output}[/green]")
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@service.command("restart")
@click.argument("name")
@click.option("--user", "-u", is_flag=True, help="User service (systemctl --user)")
def service_restart_cmd(name: str, user: bool = False):
    """Restart a service.

    \b
    Examples:
        sindri service restart ollama
    """
    from sindri.tools.services import ServiceRestartTool

    async def run():
        tool = ServiceRestartTool()
        result = await tool.execute(service=name, user=user)
        if result.success:
            console.print(f"[green]{result.output}[/green]")
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@service.command("logs")
@click.argument("name")
@click.option("--lines", "-n", default=50, help="Number of log lines to show")
@click.option("--user", "-u", is_flag=True, help="User service (journalctl --user)")
def service_logs_cmd(name: str, lines: int = 50, user: bool = False):
    """View service logs.

    \b
    Examples:
        sindri service logs ollama
        sindri service logs ollama -n 100
    """
    from sindri.tools.services import ServiceLogsTool

    async def run():
        tool = ServiceLogsTool()
        result = await tool.execute(service=name, lines=lines, user=user)
        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@service.command("list")
@click.option("--state", "-s", default="running", help="Filter by state (running, failed, all)")
@click.option("--user", "-u", is_flag=True, help="User services only")
def service_list_cmd(state: str = "running", user: bool = False):
    """List services.

    \b
    Examples:
        sindri service list
        sindri service list --state failed
        sindri service list --user
    """
    from sindri.tools.services import ServiceListTool

    async def run():
        tool = ServiceListTool()
        result = await tool.execute(state=state, user=user)
        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


# =============================================================================
# Scheduling (Milestone 6)
# =============================================================================


@cli.group()
def schedule():
    """Manage scheduled tasks (cron, systemd timers, at).

    List, add, and remove scheduled tasks.
    Operations are gated by your access level configuration.
    """
    pass


@schedule.command("list")
@click.option("--type", "-t", "sched_type", type=click.Choice(["cron", "timer", "at", "all"]),
              default="all", help="Type of schedules to list")
def schedule_list_cmd(sched_type: str = "all"):
    """List scheduled tasks.

    \b
    Examples:
        sindri schedule list
        sindri schedule list --type cron
        sindri schedule list --type timer
    """
    from sindri.tools.scheduling import CronListTool, TimerListTool, AtListTool

    async def run():
        if sched_type in ("cron", "all"):
            console.print("[bold]Cron Jobs:[/bold]")
            tool = CronListTool()
            result = await tool.execute()
            if result.success:
                console.print(result.output)
            else:
                console.print(f"[red]Error: {result.error}[/red]")
            console.print()

        if sched_type in ("timer", "all"):
            console.print("[bold]Systemd User Timers:[/bold]")
            tool = TimerListTool()
            result = await tool.execute(all=True)
            if result.success:
                console.print(result.output)
            else:
                console.print(f"[red]Error: {result.error}[/red]")
            console.print()

        if sched_type in ("at", "all"):
            console.print("[bold]At Jobs:[/bold]")
            tool = AtListTool()
            result = await tool.execute()
            if result.success:
                console.print(result.output)
            else:
                console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@schedule.command("cron-add")
@click.argument("schedule")
@click.argument("command")
@click.option("--comment", "-c", help="Comment to identify this job")
def schedule_cron_add(schedule: str, command: str, comment: str = None):
    """Add a cron job.

    \b
    Examples:
        sindri schedule cron-add "0 * * * *" "/usr/bin/backup.sh"
        sindri schedule cron-add "0 2 * * *" "sindri doctor --fix" -c "Daily health"
    """
    from sindri.tools.scheduling import CronAddTool

    async def run():
        tool = CronAddTool()
        result = await tool.execute(schedule=schedule, command=command, comment=comment)
        if result.success:
            console.print(f"[green]{result.output}[/green]")
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@schedule.command("cron-remove")
@click.option("--line", "-l", type=int, help="Line number to remove")
@click.option("--pattern", "-p", help="Pattern to match and remove")
def schedule_cron_remove(line: int = None, pattern: str = None):
    """Remove a cron job by line number or pattern.

    \b
    Examples:
        sindri schedule cron-remove --line 3
        sindri schedule cron-remove --pattern "backup.sh"
    """
    from sindri.tools.scheduling import CronRemoveTool

    if line is None and pattern is None:
        console.print("[red]Must specify --line or --pattern[/red]")
        return

    async def run():
        tool = CronRemoveTool()
        result = await tool.execute(line_number=line, pattern=pattern)
        if result.success:
            console.print(f"[green]{result.output}[/green]")
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@schedule.command("timer-create")
@click.argument("name")
@click.argument("command")
@click.option("--calendar", "-c", help="OnCalendar schedule (e.g., 'daily', '*:0/15')")
@click.option("--on-boot", "-b", help="OnBootSec time (e.g., '5min')")
@click.option("--description", "-d", help="Timer description")
def schedule_timer_create(name: str, command: str, calendar: str = None,
                          on_boot: str = None, description: str = None):
    """Create a systemd user timer.

    \b
    Examples:
        sindri schedule timer-create health "sindri doctor" --calendar daily
        sindri schedule timer-create startup "notify-send 'Ready'" --on-boot 30s
    """
    from sindri.tools.scheduling import TimerCreateTool

    if calendar is None and on_boot is None:
        console.print("[red]Must specify --calendar or --on-boot[/red]")
        return

    async def run():
        tool = TimerCreateTool()
        result = await tool.execute(
            name=name,
            command=command,
            on_calendar=calendar,
            on_boot_sec=on_boot,
            description=description or f"Timer for {name}",
        )
        if result.success:
            console.print(f"[green]{result.output}[/green]")
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@schedule.command("timer-remove")
@click.argument("name")
def schedule_timer_remove(name: str):
    """Remove a systemd user timer.

    \b
    Examples:
        sindri schedule timer-remove health
    """
    from sindri.tools.scheduling import TimerRemoveTool

    async def run():
        tool = TimerRemoveTool()
        result = await tool.execute(name=name)
        if result.success:
            console.print(f"[green]{result.output}[/green]")
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@schedule.command("at")
@click.argument("time")
@click.argument("command")
def schedule_at_cmd(time: str, command: str):
    """Schedule a one-time task with at.

    \b
    Examples:
        sindri schedule at "now + 1 hour" "echo hello"
        sindri schedule at "10:30" "/usr/bin/task.sh"
        sindri schedule at "tomorrow" "sindri doctor"
    """
    from sindri.tools.scheduling import AtScheduleTool

    async def run():
        tool = AtScheduleTool()
        result = await tool.execute(time=time, command=command)
        if result.success:
            console.print(f"[green]{result.output}[/green]")
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@schedule.command("at-remove")
@click.argument("job_id", type=int)
def schedule_at_remove(job_id: int):
    """Remove a scheduled at job.

    \b
    Examples:
        sindri schedule at-remove 42
    """
    from sindri.tools.scheduling import AtRemoveTool

    async def run():
        tool = AtRemoveTool()
        result = await tool.execute(job_id=job_id)
        if result.success:
            console.print(f"[green]{result.output}[/green]")
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


# =============================================================================
# Self-Management (Milestone 6)
# =============================================================================


@cli.group("self")
def self_mgmt():
    """Self-management commands for Sindri.

    Version info, updates, model management, and VRAM status.
    """
    pass


@self_mgmt.command("version")
def self_version_cmd():
    """Show Sindri version and status."""
    from sindri.tools.self_management import SindriVersionTool

    async def run():
        tool = SindriVersionTool()
        result = await tool.execute()
        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@self_mgmt.command("update")
def self_update_cmd():
    """Update Sindri from the local repository."""
    from sindri.tools.self_management import SindriUpdateTool

    async def run():
        tool = SindriUpdateTool()
        result = await tool.execute()
        if result.success:
            console.print(f"[green]{result.output}[/green]")
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@self_mgmt.command("models")
def self_models_cmd():
    """List installed Ollama models."""
    from sindri.tools.self_management import OllamaListTool

    async def run():
        tool = OllamaListTool()
        result = await tool.execute()
        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@self_mgmt.command("pull")
@click.argument("model")
def self_pull_cmd(model: str):
    """Pull (download) an Ollama model.

    \b
    Examples:
        sindri self pull qwen2.5-coder:7b
        sindri self pull llama3.1:8b
    """
    from sindri.tools.self_management import OllamaPullTool

    async def run():
        console.print(f"[dim]Pulling {model}... (this may take a while)[/dim]")
        tool = OllamaPullTool()
        result = await tool.execute(model=model)
        if result.success:
            console.print(f"[green]{result.output}[/green]")
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@self_mgmt.command("remove")
@click.argument("model")
def self_remove_cmd(model: str):
    """Remove an Ollama model.

    \b
    Examples:
        sindri self remove old-model:latest
    """
    from sindri.tools.self_management import OllamaRemoveTool

    async def run():
        tool = OllamaRemoveTool()
        result = await tool.execute(model=model)
        if result.success:
            console.print(f"[green]{result.output}[/green]")
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@self_mgmt.command("vram")
def self_vram_cmd():
    """Show GPU VRAM usage."""
    from sindri.tools.self_management import VramStatusTool

    async def run():
        tool = VramStatusTool()
        result = await tool.execute()
        if result.success:
            console.print(result.output)
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


@self_mgmt.command("ollama-status")
def self_ollama_status_cmd():
    """Check Ollama server status."""
    from sindri.tools.self_management import OllamaStatusTool

    async def run():
        tool = OllamaStatusTool()
        result = await tool.execute()
        if result.success:
            console.print(f"[green]{result.output}[/green]")
        else:
            console.print(f"[red]Error: {result.error}[/red]")

    asyncio.run(run())


# ============================================
# Tool Audit Commands (Granular Tool Permissions)
# ============================================


@cli.group()
def audit():
    """View tool execution audit log."""
    pass


@audit.command("list")
@click.option("--limit", "-n", default=50, help="Maximum entries to show")
@click.option("--tool", "-t", help="Filter by tool name")
@click.option("--session", "-s", help="Filter by session ID")
@click.option("--success-only", is_flag=True, help="Only show successful executions")
@click.option("--failed-only", is_flag=True, help="Only show failed executions")
def audit_list(limit: int, tool: str, session: str, success_only: bool, failed_only: bool):
    """List recent tool executions.

    Examples:
        sindri audit list

        sindri audit list --limit 100 --tool shell

        sindri audit list --failed-only
    """
    from rich.table import Table
    from sindri.persistence.audit import AuditStore

    async def run():
        store = AuditStore()
        entries = await store.list_entries(
            limit=limit,
            tool_name=tool,
            session_id=session,
            success_only=success_only,
            failed_only=failed_only,
        )

        if not entries:
            console.print("[yellow]No audit entries found.[/yellow]")
            return

        table = Table(
            title=f"Tool Audit Log (last {len(entries)} entries)",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("ID", style="dim", width=6)
        table.add_column("Time", width=19)
        table.add_column("Tool", style="cyan", width=20)
        table.add_column("Status", width=8)
        table.add_column("Duration", width=10)
        table.add_column("Error", style="red", width=30)

        for entry in entries:
            status = "[green]✓[/green]" if entry.success else "[red]✗[/red]"
            if entry.dry_run:
                status = "[yellow]DRY[/yellow]"

            duration = f"{entry.duration_ms}ms" if entry.duration_ms else "-"
            error = (entry.error[:30] + "...") if entry.error and len(entry.error) > 30 else (entry.error or "")
            time_str = entry.created_at.strftime("%Y-%m-%d %H:%M:%S")

            table.add_row(
                str(entry.id),
                time_str,
                entry.tool_name,
                status,
                duration,
                error,
            )

        console.print(table)

    asyncio.run(run())


@audit.command("stats")
@click.option("--days", "-d", default=7, help="Number of days to analyze")
def audit_stats(days: int):
    """Show tool usage statistics.

    Examples:
        sindri audit stats

        sindri audit stats --days 30
    """
    from rich.table import Table
    from datetime import datetime, timedelta
    from sindri.persistence.audit import AuditStore

    async def run():
        store = AuditStore()
        start_date = datetime.now() - timedelta(days=days)
        stats = await store.get_tool_stats(start_date=start_date)

        if not stats:
            console.print("[yellow]No audit data found for the specified period.[/yellow]")
            return

        table = Table(
            title=f"Tool Usage Statistics (last {days} days)",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Tool", style="cyan", width=25)
        table.add_column("Total", width=8)
        table.add_column("Success", style="green", width=8)
        table.add_column("Failed", style="red", width=8)
        table.add_column("Success Rate", width=12)
        table.add_column("Avg Duration", width=12)

        for tool_name, tool_stats in stats.items():
            success_rate = f"{tool_stats['success_rate']:.1f}%"
            avg_duration = f"{tool_stats['avg_duration_ms']:.0f}ms" if tool_stats['avg_duration_ms'] else "-"

            table.add_row(
                tool_name,
                str(tool_stats["total"]),
                str(tool_stats["successes"]),
                str(tool_stats["failures"]),
                success_rate,
                avg_duration,
            )

        console.print(table)

    asyncio.run(run())


@audit.command("export")
@click.option("--format", "-f", type=click.Choice(["json", "csv"]), default="json", help="Export format")
@click.option("--output", "-o", help="Output file (default: stdout)")
@click.option("--limit", "-n", default=1000, help="Maximum entries to export")
@click.option("--tool", "-t", help="Filter by tool name")
def audit_export(format: str, output: str, limit: int, tool: str):
    """Export audit log to JSON or CSV.

    Examples:
        sindri audit export --format json -o audit.json

        sindri audit export --format csv --tool shell

        sindri audit export --limit 5000 -o full_audit.json
    """
    from sindri.persistence.audit import AuditStore

    async def run():
        store = AuditStore()
        data = await store.export_entries(
            format=format,
            limit=limit,
            tool_name=tool,
        )

        if output:
            with open(output, "w") as f:
                f.write(data)
            console.print(f"[green]✓[/green] Exported to {output}")
        else:
            print(data)

    asyncio.run(run())


@audit.command("clear")
@click.option("--days", "-d", default=30, help="Delete entries older than this many days")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def audit_clear(days: int, yes: bool):
    """Clear old audit entries.

    Examples:
        sindri audit clear --days 90

        sindri audit clear --days 7 --yes
    """
    from sindri.persistence.audit import AuditStore

    if not yes:
        if not click.confirm(f"Delete audit entries older than {days} days?"):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    async def run():
        store = AuditStore()
        deleted = await store.clear_old_entries(days=days)
        console.print(f"[green]✓[/green] Deleted {deleted} old audit entries")

    asyncio.run(run())


# ============================================
# Policy + Guardrails Commands
# ============================================


@cli.group()
def policy():
    """Manage agent policy and guardrails.

    Configure limits on tool calls, files touched, runtime, and file scope
    for each agent or globally.
    """
    pass


@policy.command("show")
@click.option("--agent", "-a", help="Show policy for specific agent")
def policy_show(agent: str = None):
    """Show current policy configuration.

    Examples:
        sindri policy show

        sindri policy show --agent ratatoskr
    """
    from sindri.config import SindriConfig
    from sindri.agents.registry import AGENTS

    config = SindriConfig.load()

    console.print("[bold]Global Policy Defaults[/bold]")
    console.print(f"  Max Tool Calls: {config.default_max_tool_calls or 'unlimited'}")
    console.print(f"  Max Files: {config.default_max_files_touched or 'unlimited'}")
    console.print(f"  Max Runtime: {config.default_max_runtime_seconds or 'unlimited'}s")
    console.print(f"  File Scope: {config.default_file_scope or '(all files)'}")
    console.print(f"  Escalation Mode: {config.default_escalation_mode}")
    console.print(f"  Audit Enabled: {config.policy_audit_enabled}")
    console.print()

    if agent:
        if agent not in AGENTS:
            console.print(f"[red]Unknown agent: {agent}[/red]")
            return
        agent_def = AGENTS[agent]
        console.print(f"[bold]Agent: {agent}[/bold]")
        console.print(f"  Role: {agent_def.role}")
        console.print(f"  Max Tool Calls: {agent_def.max_tool_calls or 'default'}")
        console.print(f"  Max Files: {agent_def.max_files_touched or 'default'}")
        console.print(f"  Max Runtime: {agent_def.max_runtime_seconds or 'default'}s")
        console.print(f"  File Scope: {agent_def.file_scope or 'default'}")
        console.print(f"  Escalation: {agent_def.escalation_mode}")
    else:
        # Show agents with custom policy overrides
        overrides = []
        for name, agent_def in AGENTS.items():
            has_override = any([
                agent_def.max_tool_calls is not None,
                agent_def.max_files_touched is not None,
                agent_def.max_runtime_seconds is not None,
                agent_def.file_scope,
            ])
            if has_override:
                overrides.append((name, agent_def))

        if overrides:
            console.print("[bold]Agent Policy Overrides[/bold]")
            for name, agent_def in overrides:
                parts = []
                if agent_def.max_tool_calls is not None:
                    parts.append(f"max_tools={agent_def.max_tool_calls}")
                if agent_def.max_files_touched is not None:
                    parts.append(f"max_files={agent_def.max_files_touched}")
                if agent_def.max_runtime_seconds is not None:
                    parts.append(f"max_runtime={agent_def.max_runtime_seconds}s")
                console.print(f"  [cyan]{name}[/cyan]: {', '.join(parts)}")
        else:
            console.print("[dim]No agent-specific policy overrides configured.[/dim]")


@policy.command("set-default")
@click.option("--max-tool-calls", type=int, help="Max tool calls per task (0 for unlimited)")
@click.option("--max-files", type=int, help="Max files touched per task (0 for unlimited)")
@click.option("--max-runtime", type=float, help="Max runtime in seconds (0 for unlimited)")
@click.option("--escalation", type=click.Choice(["deny", "warn", "escalate"]), help="Escalation mode")
@click.option("--audit/--no-audit", default=None, help="Enable/disable policy audit logging")
def policy_set_default(
    max_tool_calls: int = None,
    max_files: int = None,
    max_runtime: float = None,
    escalation: str = None,
    audit: bool = None,
):
    """Set global policy defaults.

    Examples:
        sindri policy set-default --max-tool-calls 100

        sindri policy set-default --max-runtime 300 --escalation warn

        sindri policy set-default --no-audit
    """
    from pathlib import Path
    from sindri.config import SindriConfig

    config = SindriConfig.load()
    modified = False

    if max_tool_calls is not None:
        config.default_max_tool_calls = max_tool_calls if max_tool_calls > 0 else None
        console.print(f"[green]Set max tool calls: {max_tool_calls or 'unlimited'}[/green]")
        modified = True

    if max_files is not None:
        config.default_max_files_touched = max_files if max_files > 0 else None
        console.print(f"[green]Set max files: {max_files or 'unlimited'}[/green]")
        modified = True

    if max_runtime is not None:
        config.default_max_runtime_seconds = max_runtime if max_runtime > 0 else None
        console.print(f"[green]Set max runtime: {max_runtime or 'unlimited'}s[/green]")
        modified = True

    if escalation:
        config.default_escalation_mode = escalation
        console.print(f"[green]Set escalation mode: {escalation}[/green]")
        modified = True

    if audit is not None:
        config.policy_audit_enabled = audit
        console.print(f"[green]Set policy audit: {'enabled' if audit else 'disabled'}[/green]")
        modified = True

    if modified:
        config_path = Path.home() / ".sindri" / "config.toml"
        try:
            config.save(str(config_path))
            console.print(f"[dim]Saved to: {config_path}[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not save config: {e}[/yellow]")
    else:
        console.print("[yellow]No changes specified. Use --help to see options.[/yellow]")


@policy.command("violations")
@click.option("--limit", "-n", default=20, help="Number of violations to show")
@click.option("--agent", "-a", help="Filter by agent name")
def policy_violations(limit: int, agent: str = None):
    """Show recent policy violations from audit log.

    Examples:
        sindri policy violations

        sindri policy violations --limit 50 --agent ratatoskr
    """
    from rich.table import Table
    from sindri.persistence.audit import AuditStore

    async def fetch():
        store = AuditStore()
        # Policy violations are logged with tool_name starting with "policy_violation:"
        entries = await store.list_entries(limit=limit * 3)  # Fetch extra, filter in Python
        violations = [e for e in entries if e.tool_name.startswith("policy_violation:")]

        if agent:
            # Filter by agent (stored in task_id context)
            violations = [e for e in violations if agent in (e.task_id or "")]

        return violations[:limit]

    violations = asyncio.run(fetch())

    if not violations:
        console.print("[dim]No recent policy violations found.[/dim]")
        return

    table = Table(
        title=f"Recent Policy Violations ({len(violations)})",
        show_header=True,
        header_style="bold yellow",
    )
    table.add_column("Time", width=19)
    table.add_column("Type", style="yellow", width=20)
    table.add_column("Task ID", width=12)
    table.add_column("Reason", width=40)

    for v in violations:
        violation_type = v.tool_name.replace("policy_violation:", "")
        task_id = (v.task_id or "")[:12]
        table.add_row(
            v.created_at.strftime("%Y-%m-%d %H:%M:%S") if v.created_at else "-",
            violation_type,
            task_id,
            v.error or "-",
        )

    console.print(table)


# ==============================================================================
# Telemetry Commands (ROADMAP Item 7: Performance Telemetry Stream)
# ==============================================================================


@cli.group()
def telemetry():
    """Performance telemetry and trace export commands.

    Stream live telemetry from a running Sindri server, export session traces
    for profiling, and compare traces for regression checking.

    Examples:
        sindri telemetry stream --url http://localhost:8000

        sindri telemetry snapshot --url http://localhost:8000

        sindri telemetry export <session_id> -o trace.json

        sindri telemetry compare baseline.json current.json
    """
    pass


@telemetry.command("stream")
@click.option("--url", default="http://localhost:8000", help="Sindri API URL")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"]),
    default="table",
    help="Output format",
)
def telemetry_stream(url: str, output_format: str):
    """Stream live telemetry from a running Sindri server.

    Connects to the SSE endpoint and displays real-time metrics including
    VRAM usage, loaded models, task concurrency, and session progress.

    Press Ctrl+C to stop streaming.
    """
    import httpx
    from rich.live import Live
    from rich.table import Table

    def build_table(data: dict) -> Table:
        table = Table(title="Live Telemetry", show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        # VRAM
        vram = data.get("vram", {})
        table.add_row(
            "VRAM Used",
            f"{vram.get('used_gb', 0):.1f} / {vram.get('total_gb', 16):.1f} GB",
        )
        table.add_row(
            "Loaded Models", ", ".join(vram.get("loaded_models", [])) or "None"
        )
        table.add_row("Cache Hit Rate", f"{vram.get('cache_hit_rate', 0) * 100:.1f}%")

        # Concurrency
        conc = data.get("concurrency", {})
        table.add_row("Running Tasks", str(conc.get("running_tasks", 0)))
        table.add_row("Pending Tasks", str(conc.get("pending_tasks", 0)))

        # Session
        table.add_row(
            "Session Duration", f"{data.get('session_duration_seconds', 0):.1f}s"
        )
        table.add_row("Current Agent", data.get("current_agent") or "None")
        table.add_row("Iteration", str(data.get("current_iteration", 0)))

        return table

    console.print(f"[dim]Connecting to {url}/api/metrics/live...[/dim]")

    try:
        with httpx.stream(
            "GET", f"{url}/api/metrics/live", timeout=None
        ) as response:
            if output_format == "table":
                with Live(console=console, refresh_per_second=1) as live:
                    for line in response.iter_lines():
                        if not line:
                            continue
                        if line.startswith("data:"):
                            try:
                                data = json.loads(line[5:].strip())
                                live.update(build_table(data))
                            except json.JSONDecodeError:
                                pass
            else:
                for line in response.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        try:
                            data = json.loads(line[5:].strip())
                            console.print(json.dumps(data, indent=2))
                        except json.JSONDecodeError:
                            pass
    except httpx.ConnectError:
        console.print(f"[red]Could not connect to {url}. Is the server running?[/]")
    except KeyboardInterrupt:
        console.print("\n[dim]Stream stopped[/dim]")


@telemetry.command("snapshot")
@click.option("--url", default="http://localhost:8000", help="Sindri API URL")
def telemetry_snapshot_cmd(url: str):
    """Get current telemetry snapshot from running server.

    Returns full telemetry data including agent and tool statistics.
    """
    import httpx

    try:
        response = httpx.get(f"{url}/api/metrics/telemetry/snapshot")
        if response.status_code == 200:
            data = response.json()
            console.print(json.dumps(data, indent=2))
        else:
            console.print(f"[red]Error: {response.text}[/]")
    except httpx.ConnectError:
        console.print(f"[red]Could not connect to {url}. Is the server running?[/]")


@telemetry.command("export")
@click.argument("session_id")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option(
    "--include-outputs", is_flag=True, help="Include full tool outputs (can be large)"
)
def telemetry_export(session_id: str, output: str, include_outputs: bool):
    """Export session trace for profiling.

    Creates a JSON file containing all timing data, environment info,
    and tool audit logs for the specified session.

    Example:
        sindri telemetry export abc12345 -o trace.json
    """
    from pathlib import Path
    from sindri.telemetry.exporter import TraceExporter
    from sindri.persistence.state import SessionState

    async def do_export():
        state = SessionState()

        # Resolve short session ID
        full_id = session_id
        if len(session_id) < 36:
            sessions = await state.list_sessions(limit=100)
            matching = [s for s in sessions if s["id"].startswith(session_id)]
            if not matching:
                console.print(f"[red]No session found starting with {session_id}[/]")
                return
            if len(matching) > 1:
                console.print(f"[yellow]Multiple sessions match {session_id}:[/]")
                for m in matching:
                    console.print(f"  - {m['id'][:8]}")
                return
            full_id = matching[0]["id"]

        # Determine output path
        output_path = Path(output) if output else Path(f"trace_{full_id[:8]}.json")

        exporter = TraceExporter()
        with console.status("[bold green]Exporting trace..."):
            trace = await exporter.export_session_trace(
                full_id,
                output_path=output_path,
                include_tool_outputs=include_outputs,
            )

        console.print(f"[green]Trace exported to {output_path}[/]")
        console.print(f"[dim]Session: {full_id[:8]}[/]")

        # Summary
        summary = TraceExporter.get_trace_summary(trace)
        if summary.get("duration_seconds"):
            console.print(f"[dim]Duration: {summary['duration_seconds']:.1f}s[/]")
        if summary.get("total_iterations"):
            console.print(f"[dim]Iterations: {summary['total_iterations']}[/]")
        if summary.get("total_tool_calls"):
            console.print(f"[dim]Tool calls: {summary['total_tool_calls']}[/]")

    asyncio.run(do_export())


@telemetry.command("compare")
@click.argument("baseline", type=click.Path(exists=True))
@click.argument("current", type=click.Path(exists=True))
def telemetry_compare(baseline: str, current: str):
    """Compare two session traces for regression checking.

    Compares timing, iterations, and tool calls between two trace files
    and reports regressions (>20% slower) and improvements (>10% faster).

    Example:
        sindri telemetry compare baseline.json current.json
    """
    from pathlib import Path
    from sindri.telemetry.exporter import TraceExporter

    async def do_compare():
        exporter = TraceExporter()
        result = await exporter.compare_traces(Path(baseline), Path(current))

        console.print("[bold]Trace Comparison[/]\n")

        console.print(f"Baseline: {result['baseline_session'][:8] if result.get('baseline_session') else 'unknown'}")
        console.print(f"Current:  {result['current_session'][:8] if result.get('current_session') else 'unknown'}")
        console.print()

        # Duration
        if result.get("duration_delta"):
            d = result["duration_delta"]
            change = d.get("change_percent", 0)
            color = "red" if change > 10 else "green" if change < -10 else "yellow"
            console.print(
                f"Duration: {d['baseline']:.1f}s -> {d['current']:.1f}s [{color}]{change:+.1f}%[/]"
            )

        # Iterations
        if result.get("iteration_delta"):
            i = result["iteration_delta"]
            console.print(
                f"Iterations: {i['baseline']} -> {i['current']} ({i['change']:+d})"
            )

        # Tool calls
        if result.get("tool_call_delta"):
            t = result["tool_call_delta"]
            console.print(
                f"Tool calls: {t['baseline']} -> {t['current']} ({t['change']:+d})"
            )

        # Regressions
        if result.get("regressions"):
            console.print("\n[red bold]Regressions:[/]")
            for r in result["regressions"]:
                console.print(f"  - {r['message']}")

        # Improvements
        if result.get("improvements"):
            console.print("\n[green bold]Improvements:[/]")
            for i in result["improvements"]:
                console.print(f"  - {i['message']}")

        if not result.get("regressions") and not result.get("improvements"):
            console.print("\n[dim]No significant changes detected[/]")

    asyncio.run(do_compare())


# ==============================================================================
# Replay Commands (Reproducible Sessions)
# ==============================================================================


@cli.group()
def replay():
    """Replay and compare past sessions.

    The replay command group provides tools for reproducing and comparing
    sessions. Sessions can be replayed using recorded tool outputs for
    deterministic execution.

    Examples:
        sindri replay info <session_id>

        sindri replay list

        sindri replay run <session_id> --mode tool-only

        sindri replay compare <session1> <session2>
    """
    pass


@replay.command("info")
@click.argument("session_id")
@click.option("--show-config", is_flag=True, help="Include full config snapshot")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def replay_info(session_id: str, show_config: bool = False, as_json: bool = False):
    """Show environment snapshot for a session.

    Displays the captured environment information including Sindri version,
    Python version, Ollama version, model metadata, and inference parameters.

    Examples:
        sindri replay info abc12345

        sindri replay info abc12345 --show-config

        sindri replay info abc12345 --json
    """
    import json
    from rich.table import Table

    from sindri.persistence.snapshots import SnapshotStore
    from sindri.persistence.state import SessionState

    async def fetch():
        state = SessionState()
        snapshots = SnapshotStore()

        # Resolve short session ID
        full_session_id = session_id
        if len(session_id) < 36:
            all_sessions = await state.list_sessions(limit=100)
            matching = [s for s in all_sessions if s["id"].startswith(session_id)]

            if not matching:
                return None, None, f"No session found starting with {session_id}"
            elif len(matching) > 1:
                return (
                    None,
                    None,
                    f"Multiple sessions match {session_id}, use full ID",
                )

            full_session_id = matching[0]["id"]

        session = await state.load_session(full_session_id)
        if not session:
            return None, None, f"Session {full_session_id} not found"

        snapshot = await snapshots.load_snapshot(full_session_id)
        return session, snapshot, None

    session, snapshot, error = asyncio.run(fetch())

    if error:
        console.print(f"[red]✗ {error}[/]")
        return

    if not snapshot:
        console.print(f"[yellow]⚠ No snapshot found for session {session.id[:8]}[/]")
        console.print("[dim]Snapshots are only captured for new sessions[/]")
        return

    if as_json:
        output = snapshot.to_dict()
        if not show_config:
            output.pop("config_snapshot", None)
        console.print(json.dumps(output, indent=2, default=str))
        return

    # Display as formatted table
    console.print(
        Panel(
            f"[bold blue]Session:[/] {session.id[:8]}\n"
            f"[dim]Task:[/] {session.task[:60]}...",
            title="Session Snapshot",
        )
    )

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Property", style="cyan", width=25)
    table.add_column("Value", width=50)

    table.add_row("Sindri Version", snapshot.sindri_version)
    if snapshot.sindri_git_commit:
        table.add_row("Git Commit", snapshot.sindri_git_commit)
    table.add_row("Python Version", snapshot.python_version)
    table.add_row("Ollama Version", snapshot.ollama_version or "unknown")
    table.add_row("Ollama Host", snapshot.ollama_host)

    console.print(table)

    # Model metadata
    console.print("\n[bold]Model Metadata[/]")
    model_table = Table(show_header=True, header_style="bold green")
    model_table.add_column("Property", style="green", width=25)
    model_table.add_column("Value", width=50)

    model = snapshot.model_metadata
    model_table.add_row("Name", model.name)
    model_table.add_row("Family", model.family)
    model_table.add_row("Parameter Size", model.parameter_size)
    model_table.add_row("Quantization", model.quantization_level)
    if model.digest:
        model_table.add_row("Digest", model.digest[:24] + "...")

    console.print(model_table)

    # Inference params
    if snapshot.inference_params:
        console.print("\n[bold]Inference Parameters[/]")
        params_table = Table(show_header=True, header_style="bold yellow")
        params_table.add_column("Property", style="yellow", width=25)
        params_table.add_column("Value", width=50)

        params = snapshot.inference_params
        params_table.add_row("Temperature", str(params.temperature))
        params_table.add_row("Top P", str(params.top_p))
        params_table.add_row("Top K", str(params.top_k))
        params_table.add_row("Repeat Penalty", str(params.repeat_penalty))
        params_table.add_row("Context Length", str(params.num_ctx))
        if params.seed is not None:
            params_table.add_row("Seed", str(params.seed))

        console.print(params_table)

    if show_config:
        console.print("\n[bold]Config Snapshot[/]")
        console.print(json.dumps(snapshot.config_snapshot, indent=2))


@replay.command("list")
@click.option("--limit", "-n", default=20, help="Number of sessions to show")
def replay_list(limit: int):
    """List sessions with replay snapshots.

    Shows sessions that have captured environment snapshots and are
    eligible for replay.

    Examples:
        sindri replay list

        sindri replay list --limit 50
    """
    from rich.table import Table

    from sindri.persistence.snapshots import SnapshotStore, ToolOutputStore

    async def fetch():
        snapshots = SnapshotStore()
        tool_outputs = ToolOutputStore()

        sessions = await snapshots.list_sessions_with_snapshots(limit=limit)

        # Add tool output counts
        for session in sessions:
            count = await tool_outputs.get_output_count(session["session_id"])
            session["tool_outputs"] = count

        return sessions

    sessions = asyncio.run(fetch())

    if not sessions:
        console.print("[dim]No sessions with snapshots found.[/]")
        console.print(
            "[dim]Snapshots are captured automatically for new sessions.[/]"
        )
        return

    table = Table(
        title=f"Sessions with Snapshots ({len(sessions)})",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Session ID", style="cyan", width=10)
    table.add_column("Task", width=35)
    table.add_column("Model", width=20)
    table.add_column("Version", width=10)
    table.add_column("Outputs", width=8)
    table.add_column("Created", width=19)

    for s in sessions:
        outputs_str = str(s["tool_outputs"]) if s["tool_outputs"] > 0 else "-"
        table.add_row(
            s["session_id"][:8],
            (s["task"][:32] + "...") if len(s["task"]) > 35 else s["task"],
            s["model"],
            s["sindri_version"],
            outputs_str,
            s["created_at"][:19] if s["created_at"] else "-",
        )

    console.print(table)
    console.print(
        "\n[dim]Use 'sindri replay info <session_id>' to see full snapshot[/]"
    )


@replay.command("run")
@click.argument("session_id")
@click.option(
    "--mode",
    type=click.Choice(["full", "tool-only"]),
    default="tool-only",
    help="Replay mode",
)
def replay_run(session_id: str, mode: str):
    """Replay a session.

    In tool-only mode (default), replays using recorded tool outputs
    for deterministic execution without running the LLM.

    In full mode, re-runs with the LLM and compares outputs to the
    original session.

    Examples:
        sindri replay run abc12345

        sindri replay run abc12345 --mode tool-only

        sindri replay run abc12345 --mode full
    """
    from sindri.replay.engine import ReplayEngine, ReplayMode
    from sindri.persistence.state import SessionState

    async def execute():
        state = SessionState()

        # Resolve short session ID
        full_session_id = session_id
        if len(session_id) < 36:
            all_sessions = await state.list_sessions(limit=100)
            matching = [s for s in all_sessions if s["id"].startswith(session_id)]

            if not matching:
                console.print(f"[red]✗ No session found starting with {session_id}[/]")
                return
            elif len(matching) > 1:
                console.print(f"[yellow]⚠ Multiple sessions match {session_id}[/]")
                for m in matching:
                    console.print(f"  • {m['id'][:8]}")
                return

            full_session_id = matching[0]["id"]

        session = await state.load_session(full_session_id)
        if not session:
            console.print(f"[red]✗ Session {full_session_id} not found[/]")
            return

        console.print(
            Panel(
                f"[bold blue]Session:[/] {full_session_id[:8]}\n"
                f"[dim]Task:[/] {session.task[:60]}...\n"
                f"[dim]Mode:[/] {mode}",
                title="Replay Session",
            )
        )

        engine = ReplayEngine()
        replay_mode = ReplayMode.TOOL_ONLY if mode == "tool-only" else ReplayMode.FULL

        with console.status("[bold green]Replaying..."):
            result = await engine.replay(full_session_id, mode=replay_mode)

        if result.status == "completed":
            console.print(f"[green]✓ Replay completed successfully[/]")
            console.print(
                f"  Tool outputs: {result.tool_outputs_replayed}/{result.tool_outputs_total}"
            )
            if result.duration_seconds:
                console.print(f"  Duration: {result.duration_seconds:.2f}s")
        elif result.status == "no_outputs":
            console.print("[yellow]⚠ No tool outputs recorded for this session[/]")
            console.print(
                "[dim]Tool outputs are captured automatically during execution[/]"
            )
        elif result.status == "diverged":
            console.print(f"[yellow]⚠ Replay diverged at turn {result.divergence_point}[/]")
            if result.divergence_reason:
                console.print(f"[dim]Reason: {result.divergence_reason}[/]")
        else:
            console.print(f"[red]✗ Replay failed: {result.status}[/]")
            for error in result.errors:
                console.print(f"  [dim]{error}[/]")

    asyncio.run(execute())


@replay.command("compare")
@click.argument("session1_id")
@click.argument("session2_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def replay_compare(session1_id: str, session2_id: str, as_json: bool = False):
    """Compare two sessions.

    Shows differences in environment, turns, and outputs between two sessions.

    Examples:
        sindri replay compare abc12345 def67890

        sindri replay compare abc12345 def67890 --json
    """
    import json
    from rich.table import Table

    from sindri.replay.comparator import SessionComparator
    from sindri.persistence.state import SessionState

    async def execute():
        state = SessionState()
        comparator = SessionComparator()

        # Resolve short session IDs
        async def resolve_id(sid):
            if len(sid) < 36:
                all_sessions = await state.list_sessions(limit=100)
                matching = [s for s in all_sessions if s["id"].startswith(sid)]
                if not matching:
                    return None, f"No session found starting with {sid}"
                elif len(matching) > 1:
                    return None, f"Multiple sessions match {sid}"
                return matching[0]["id"], None
            return sid, None

        full_id1, err1 = await resolve_id(session1_id)
        if err1:
            console.print(f"[red]✗ {err1}[/]")
            return

        full_id2, err2 = await resolve_id(session2_id)
        if err2:
            console.print(f"[red]✗ {err2}[/]")
            return

        try:
            comparison = await comparator.compare(full_id1, full_id2)
        except ValueError as e:
            console.print(f"[red]✗ {e}[/]")
            return

        if as_json:
            output = {
                "session1_id": comparison.session1_id,
                "session2_id": comparison.session2_id,
                "overall_similarity": comparison.overall_similarity,
                "turns_compared": comparison.turns_compared,
                "turns_identical": comparison.turns_identical,
                "summary": comparison.summary,
                "env_diff": comparison.env_diff.to_dict(),
            }
            console.print(json.dumps(output, indent=2, default=str))
            return

        # Header
        console.print(
            Panel(
                f"[bold blue]Session 1:[/] {comparison.session1_id[:8]}\n"
                f"[bold blue]Session 2:[/] {comparison.session2_id[:8]}\n"
                f"[dim]Similarity:[/] {comparison.overall_similarity:.1%}",
                title="Session Comparison",
            )
        )

        # Summary
        console.print(f"\n[bold]Summary:[/] {comparison.summary}")

        # Environment diff
        if comparison.env_diff.has_differences:
            console.print("\n[bold yellow]Environment Differences:[/]")
            env_table = Table(show_header=True, header_style="bold yellow")
            env_table.add_column("Property", style="yellow", width=20)
            env_table.add_column("Session 1", width=25)
            env_table.add_column("Session 2", width=25)

            diff_dict = comparison.env_diff.to_dict()
            for key, (val1, val2) in diff_dict.items():
                env_table.add_row(key.replace("_", " ").title(), str(val1), str(val2))

            console.print(env_table)

        # Turn diffs summary
        different_turns = [td for td in comparison.turn_diffs if not td.is_identical]
        if different_turns:
            console.print(f"\n[bold]Different Turns ({len(different_turns)}):[/]")
            for td in different_turns[:5]:  # Show first 5
                status = "content" if not td.content_match else ""
                if not td.tool_calls_match:
                    status += " tools" if status else "tools"
                console.print(
                    f"  Turn {td.turn_index} ({td.role}): {status} differ "
                    f"({td.similarity_score:.0%} similar)"
                )
            if len(different_turns) > 5:
                console.print(f"  [dim]... and {len(different_turns) - 5} more[/]")
        else:
            console.print("\n[green]All turns are identical.[/]")

    asyncio.run(execute())


if __name__ == "__main__":
    cli()
