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
@click.option("--ref", "-r", help="Git branch/tag/commit (for git sources)")
@click.option("--no-validate", is_flag=True, help="Skip validation")
@click.option("--strict", is_flag=True, help="Treat validation warnings as errors")
def marketplace_install(
    source: str,
    name: str = None,
    ref: str = None,
    no_validate: bool = False,
    strict: bool = False,
):
    """Install a plugin from a source.

    SOURCE can be:
    - Local path: /path/to/plugin.py
    - GitHub shorthand: user/repo
    - Git URL: https://github.com/user/repo.git
    - Direct URL: https://example.com/plugin.py

    Examples:
        sindri marketplace install /path/to/my_tool.py
        sindri marketplace install user/sindri-plugin-example
        sindri marketplace install https://github.com/user/repo.git --ref v1.0.0
    """
    import asyncio
    from sindri.marketplace import PluginInstaller

    installer = PluginInstaller(
        validate=not no_validate,
        strict=strict,
    )

    console.print(f"[bold]Installing plugin from: {source}[/bold]\n")

    result = asyncio.run(installer.install(source, name=name, ref=ref))

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
    """Update installed plugins to latest versions.

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
# Phase 9.2: Remote Collaboration Commands
# ============================================


@cli.command()
@click.argument("session_id")
@click.option(
    "--permission",
    "-p",
    type=click.Choice(["read", "comment", "write"]),
    default="read",
    help="Permission level",
)
@click.option("--expires", "-e", type=float, help="Hours until link expires")
@click.option("--max-uses", "-m", type=int, help="Maximum number of uses")
@click.option("--user", "-u", help="Your username (optional)")
def share(
    session_id: str,
    permission: str,
    expires: float = None,
    max_uses: int = None,
    user: str = None,
):
    """Create a share link for a session.

    SESSION_ID can be the full UUID or first 8 characters.

    Permission levels:
    - read: View session only
    - comment: View + add comments
    - write: View + comment + continue session (future)

    Examples:

        sindri share abc12345

        sindri share abc12345 -p comment -e 24

        sindri share abc12345 --max-uses 5 --user alice
    """
    from sindri.collaboration import ShareStore, SharePermission

    async def do_share():
        state = SessionState()
        share_store = ShareStore()

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

        # Map permission string to enum
        perm_map = {
            "read": SharePermission.READ,
            "comment": SharePermission.COMMENT,
            "write": SharePermission.WRITE,
        }

        # Create share
        share_obj = await share_store.create_share(
            session_id=full_session_id,
            permission=perm_map[permission],
            created_by=user,
            expires_in_hours=expires,
            max_uses=max_uses,
        )

        # Display share link
        share_url = share_obj.get_share_url()
        console.print("[green]✓ Share link created![/green]\n")
        console.print(f"[bold cyan]{share_url}[/bold cyan]\n")
        console.print(f"  Session: {full_session_id[:8]} - {session.task[:40]}...")
        console.print(f"  Permission: {permission}")
        if expires:
            console.print(f"  Expires: in {expires} hours")
        if max_uses:
            console.print(f"  Max uses: {max_uses}")

        console.print(
            "\n[dim]Share this link to give others access to the session[/dim]"
        )
        return True

    asyncio.run(do_share())


@cli.command("share-list")
@click.argument("session_id")
def share_list(session_id: str):
    """List all share links for a session.

    SESSION_ID can be the full UUID or first 8 characters.

    Example:

        sindri share-list abc12345
    """
    from rich.table import Table
    from sindri.collaboration import ShareStore

    async def list_shares():
        state = SessionState()
        share_store = ShareStore()

        # Resolve short session ID
        full_session_id = session_id
        if len(session_id) < 36:
            all_sessions = await state.list_sessions(limit=100)
            matching = [s for s in all_sessions if s["id"].startswith(session_id)]

            if not matching:
                console.print(f"[red]✗ No session found starting with {session_id}[/]")
                return
            elif len(matching) > 1:
                console.print(f"[yellow]⚠ Multiple sessions match {session_id}:[/]")
                for m in matching:
                    console.print(f"  • {m['id'][:8]} - {m['task'][:50]}")
                return

            full_session_id = matching[0]["id"]

        shares = await share_store.get_shares_for_session(full_session_id)

        if not shares:
            console.print(
                f"[yellow]No shares found for session {full_session_id[:8]}[/]"
            )
            console.print("[dim]Create one with: sindri share <session_id>[/dim]")
            return

        table = Table(title=f"Share Links for {full_session_id[:8]}")
        table.add_column("ID", width=6)
        table.add_column("Token", width=12)
        table.add_column("Permission", width=10)
        table.add_column("Status", width=10)
        table.add_column("Uses", justify="right", width=8)
        table.add_column("Created", width=16)

        for s in shares:
            # Status
            if not s.is_active:
                status = "[red]revoked[/red]"
            elif s.is_expired:
                status = "[yellow]expired[/yellow]"
            elif s.is_exhausted:
                status = "[yellow]exhausted[/yellow]"
            else:
                status = "[green]active[/green]"

            # Uses
            uses_str = str(s.use_count)
            if s.max_uses:
                uses_str += f"/{s.max_uses}"

            table.add_row(
                str(s.id),
                s.share_token[:10] + "...",
                s.permission.value,
                status,
                uses_str,
                s.created_at.strftime("%Y-%m-%d %H:%M"),
            )

        console.print(table)
        console.print("\n[dim]Revoke a share: sindri share-revoke <id>[/dim]")

    asyncio.run(list_shares())


@cli.command("share-revoke")
@click.argument("share_id", type=int)
def share_revoke(share_id: int):
    """Revoke a share link.

    SHARE_ID is the numeric ID from 'sindri share-list'.

    Example:

        sindri share-revoke 5
    """
    from sindri.collaboration import ShareStore

    async def revoke():
        share_store = ShareStore()

        success = await share_store.revoke_share(share_id)

        if success:
            console.print(f"[green]✓ Share {share_id} revoked[/green]")
            console.print("[dim]The link will no longer grant access[/dim]")
        else:
            console.print(f"[red]✗ Share {share_id} not found[/]")

    asyncio.run(revoke())


@cli.command()
@click.argument("session_id")
@click.argument("content")
@click.option("--turn", "-t", type=int, help="Turn index to attach comment to")
@click.option("--line", "-l", type=int, help="Line number within turn")
@click.option(
    "--type",
    "-T",
    "comment_type",
    type=click.Choice(["comment", "suggestion", "question", "issue", "praise", "note"]),
    default="comment",
    help="Comment type",
)
@click.option("--author", "-a", default="cli", help="Author name")
def comment(
    session_id: str,
    content: str,
    turn: int = None,
    line: int = None,
    comment_type: str = "comment",
    author: str = "cli",
):
    """Add a review comment to a session.

    SESSION_ID can be the full UUID or first 8 characters.
    CONTENT is the comment text (supports markdown).

    Examples:

        sindri comment abc12345 "Great use of type hints!"

        sindri comment abc12345 "Consider using a list comprehension" -t 3 -T suggestion

        sindri comment abc12345 "Why this approach?" -t 5 -l 42 -T question
    """
    from sindri.collaboration import CommentStore, SessionComment, CommentType

    async def add_comment():
        state = SessionState()
        comment_store = CommentStore()

        # Resolve short session ID
        full_session_id = session_id
        if len(session_id) < 36:
            all_sessions = await state.list_sessions(limit=100)
            matching = [s for s in all_sessions if s["id"].startswith(session_id)]

            if not matching:
                console.print(f"[red]✗ No session found starting with {session_id}[/]")
                return False
            elif len(matching) > 1:
                console.print(f"[yellow]⚠ Multiple sessions match {session_id}:[/]")
                for m in matching:
                    console.print(f"  • {m['id'][:8]} - {m['task'][:50]}")
                return False

            full_session_id = matching[0]["id"]

        # Verify session exists
        session = await state.load_session(full_session_id)
        if not session:
            console.print(f"[red]✗ Session {full_session_id} not found[/]")
            return False

        # Validate turn index if provided
        if turn is not None and (turn < 0 or turn >= len(session.turns)):
            console.print(
                f"[red]✗ Invalid turn {turn}. Session has {len(session.turns)} turns (0-{len(session.turns)-1})[/]"
            )
            return False

        # Map type string to enum
        type_map = {
            "comment": CommentType.COMMENT,
            "suggestion": CommentType.SUGGESTION,
            "question": CommentType.QUESTION,
            "issue": CommentType.ISSUE,
            "praise": CommentType.PRAISE,
            "note": CommentType.NOTE,
        }

        # Create comment
        c = SessionComment(
            session_id=full_session_id,
            author=author,
            content=content,
            turn_index=turn,
            line_number=line,
            comment_type=type_map[comment_type],
        )

        await comment_store.add_comment(c)

        # Type icons
        type_icons = {
            "comment": "💬",
            "suggestion": "💡",
            "question": "❓",
            "issue": "🐛",
            "praise": "👍",
            "note": "📝",
        }

        console.print("[green]✓ Comment added![/green]")
        console.print(
            f"  {type_icons.get(comment_type, '💬')} [{comment_type}] by {author}"
        )
        if turn is not None:
            loc = f"Turn {turn}"
            if line is not None:
                loc += f", Line {line}"
            console.print(f"  📍 {loc}")
        console.print(f"  {content[:60]}{'...' if len(content) > 60 else ''}")

        return True

    asyncio.run(add_comment())


@cli.command("comment-list")
@click.argument("session_id")
@click.option(
    "--include-resolved", "-r", is_flag=True, help="Include resolved comments"
)
@click.option("--turn", "-t", type=int, help="Filter by turn index")
def comment_list(session_id: str, include_resolved: bool = False, turn: int = None):
    """List comments on a session.

    SESSION_ID can be the full UUID or first 8 characters.

    Examples:

        sindri comment-list abc12345

        sindri comment-list abc12345 --include-resolved

        sindri comment-list abc12345 -t 5
    """
    from rich.table import Table
    from sindri.collaboration import CommentStore

    async def list_comments():
        state = SessionState()
        comment_store = CommentStore()

        # Resolve short session ID
        full_session_id = session_id
        if len(session_id) < 36:
            all_sessions = await state.list_sessions(limit=100)
            matching = [s for s in all_sessions if s["id"].startswith(session_id)]

            if not matching:
                console.print(f"[red]✗ No session found starting with {session_id}[/]")
                return
            elif len(matching) > 1:
                console.print(f"[yellow]⚠ Multiple sessions match {session_id}:[/]")
                for m in matching:
                    console.print(f"  • {m['id'][:8]} - {m['task'][:50]}")
                return

            full_session_id = matching[0]["id"]

        if turn is not None:
            comments = await comment_store.get_comments_for_turn(full_session_id, turn)
        else:
            comments = await comment_store.get_comments_for_session(
                full_session_id, include_resolved=include_resolved
            )

        if not comments:
            console.print(
                f"[yellow]No comments found for session {full_session_id[:8]}[/]"
            )
            console.print(
                '[dim]Add one with: sindri comment <session_id> "comment text"[/dim]'
            )
            return

        # Type icons
        type_icons = {
            "comment": "💬",
            "suggestion": "💡",
            "question": "❓",
            "issue": "🐛",
            "praise": "👍",
            "note": "📝",
        }

        table = Table(title=f"Comments on {full_session_id[:8]}")
        table.add_column("ID", width=5)
        table.add_column("Type", width=4)
        table.add_column("Author", width=12)
        table.add_column("Location", width=12)
        table.add_column("Content", width=40)
        table.add_column("Status", width=10)

        for c in comments:
            icon = type_icons.get(c.comment_type.value, "💬")

            # Location
            if c.turn_index is not None:
                loc = f"Turn {c.turn_index}"
                if c.line_number is not None:
                    loc += f":{c.line_number}"
            else:
                loc = "Session"

            # Status color
            if c.status.value == "open":
                status = "[yellow]open[/yellow]"
            elif c.status.value == "resolved":
                status = "[green]resolved[/green]"
            else:
                status = f"[dim]{c.status.value}[/dim]"

            # Content preview
            content_preview = (
                c.content[:37] + "..." if len(c.content) > 40 else c.content
            )
            content_preview = content_preview.replace("\n", " ")

            table.add_row(
                str(c.id),
                icon,
                c.author[:12],
                loc,
                content_preview,
                status,
            )

        console.print(table)

        # Summary
        open_count = sum(1 for c in comments if c.status.value == "open")
        console.print(f"\n[dim]Total: {len(comments)} | Open: {open_count}[/dim]")

    asyncio.run(list_comments())


@cli.command("comment-resolve")
@click.argument("comment_id", type=int)
def comment_resolve(comment_id: int):
    """Resolve a comment.

    COMMENT_ID is the numeric ID from 'sindri comment-list'.

    Example:

        sindri comment-resolve 5
    """
    from sindri.collaboration import CommentStore

    async def resolve():
        comment_store = CommentStore()

        success = await comment_store.resolve_comment(comment_id)

        if success:
            console.print(f"[green]✓ Comment {comment_id} resolved[/green]")
        else:
            console.print(f"[red]✗ Comment {comment_id} not found[/]")

    asyncio.run(resolve())


@cli.command("collab-stats")
def collab_stats():
    """Show collaboration statistics.

    Displays statistics about session sharing, comments, and activity.
    """
    from sindri.collaboration import ShareStore, CommentStore

    async def show_stats():
        share_store = ShareStore()
        comment_store = CommentStore()

        share_stats = await share_store.get_share_stats()
        comment_stats = await comment_store.get_comment_stats()

        console.print("[bold]🤝 Collaboration Statistics[/bold]\n")

        # Sharing stats
        console.print("[bold]📤 Session Sharing:[/bold]")
        console.print(f"  Total shares: {share_stats['total_shares']}")
        console.print(f"  Active shares: {share_stats['active_shares']}")
        console.print(f"  Sessions shared: {share_stats['sessions_shared']}")
        console.print(f"  Total link uses: {share_stats['total_uses']}")

        if share_stats["permission_breakdown"]:
            console.print("  Permissions:")
            for perm, count in share_stats["permission_breakdown"].items():
                console.print(f"    • {perm}: {count}")

        console.print()

        # Comment stats
        console.print("[bold]💬 Review Comments:[/bold]")
        console.print(f"  Total comments: {comment_stats['total_comments']}")
        console.print(
            f"  Sessions with comments: {comment_stats['sessions_commented']}"
        )
        console.print(f"  Unique authors: {comment_stats['unique_authors']}")

        if comment_stats["status_breakdown"]:
            console.print("  Status:")
            for status, count in comment_stats["status_breakdown"].items():
                console.print(f"    • {status}: {count}")

        if comment_stats["type_breakdown"]:
            console.print("  Types:")
            for ctype, count in comment_stats["type_breakdown"].items():
                console.print(f"    • {ctype}: {count}")

    asyncio.run(show_stats())


# ============================================
# Phase 10: Notification Commands
# ============================================


@cli.command("notifications")
@click.option("--unread", "-u", is_flag=True, help="Show only unread notifications")
@click.option("--all", "-a", "show_all", is_flag=True, help="Include archived notifications")
@click.option(
    "--type",
    "-t",
    "notif_type",
    type=click.Choice(
        ["mention", "comment", "team_invite", "team_joined", "session_shared"]
    ),
    help="Filter by notification type",
)
@click.option("--limit", "-n", default=20, help="Maximum notifications to show")
@click.argument("user_id")
def notifications(
    user_id: str,
    unread: bool = False,
    show_all: bool = False,
    notif_type: str = None,
    limit: int = 20,
):
    """List notifications for a user.

    USER_ID is the user identifier.

    Examples:

        sindri notifications user123

        sindri notifications user123 --unread

        sindri notifications user123 --type mention
    """
    from rich.table import Table
    from sindri.collaboration import NotificationStore, NotificationType

    async def list_notifications():
        store = NotificationStore()

        # Map type string to enum
        type_filter = None
        if notif_type:
            type_map = {
                "mention": NotificationType.MENTION,
                "comment": NotificationType.COMMENT,
                "team_invite": NotificationType.TEAM_INVITE,
                "team_joined": NotificationType.TEAM_JOINED,
                "session_shared": NotificationType.SESSION_SHARED,
            }
            type_filter = type_map.get(notif_type)

        notifications = await store.get_user_notifications(
            user_id=user_id,
            unread_only=unread,
            include_archived=show_all,
            notification_type=type_filter,
            limit=limit,
        )

        if not notifications:
            console.print(f"[yellow]No notifications found for {user_id}[/]")
            return

        # Get unread count
        unread_count = await store.get_unread_count(user_id)

        table = Table(title=f"Notifications for {user_id} ({unread_count} unread)")
        table.add_column("ID", width=8)
        table.add_column("", width=2)  # Read indicator
        table.add_column("Type", width=12)
        table.add_column("Title", width=30)
        table.add_column("Time", width=16)

        type_icons = {
            "mention": "@",
            "comment": "\U0001F4AC",
            "comment_reply": "\U0001F5E8",
            "team_invite": "\U0001F465",
            "team_joined": "\U0001F44B",
            "team_left": "\U0001F6AA",
            "team_role_changed": "\U0001F451",
            "session_shared": "\U0001F4E4",
            "session_activity": "\u26A1",
        }

        for n in notifications:
            read_mark = " " if n.is_read else "\U0001F534"
            icon = type_icons.get(n.type.value, "\U0001F514")
            time_str = n.created_at.strftime("%Y-%m-%d %H:%M")
            style = "dim" if n.is_read else ""

            table.add_row(
                n.id[:8],
                read_mark,
                f"{icon} {n.type.value}",
                n.title[:30],
                time_str,
                style=style,
            )

        console.print(table)
        console.print(f"\n[dim]Use 'sindri notification-read <id>' to mark as read[/dim]")

    asyncio.run(list_notifications())


@cli.command("notification-read")
@click.argument("notification_id")
def notification_read(notification_id: str):
    """Mark a notification as read.

    NOTIFICATION_ID is the full ID or first 8 characters.

    Example:
        sindri notification-read abc12345
    """
    from sindri.collaboration import NotificationStore

    async def mark_read():
        store = NotificationStore()

        # Try to find the notification by prefix
        success = await store.mark_read(notification_id)

        if success:
            console.print(f"[green]\u2713 Notification marked as read[/green]")
        else:
            console.print(f"[yellow]\u26A0 Notification not found or already read[/]")

    asyncio.run(mark_read())


@cli.command("notification-read-all")
@click.argument("user_id")
def notification_read_all(user_id: str):
    """Mark all notifications as read for a user.

    USER_ID is the user identifier.

    Example:
        sindri notification-read-all user123
    """
    from sindri.collaboration import NotificationStore

    async def mark_all():
        store = NotificationStore()
        count = await store.mark_all_read(user_id)
        console.print(f"[green]\u2713 Marked {count} notifications as read[/green]")

    asyncio.run(mark_all())


@cli.command("notification-prefs")
@click.argument("user_id")
@click.option("--enabled/--disabled", default=None, help="Enable/disable all notifications")
@click.option("--mentions/--no-mentions", default=None, help="Enable/disable mention notifications")
@click.option("--comments/--no-comments", default=None, help="Enable/disable comment notifications")
@click.option("--teams/--no-teams", default=None, help="Enable/disable team notifications")
@click.option("--sessions/--no-sessions", default=None, help="Enable/disable session notifications")
@click.option("--quiet-start", type=int, help="Quiet hours start (0-23)")
@click.option("--quiet-end", type=int, help="Quiet hours end (0-23)")
def notification_prefs(
    user_id: str,
    enabled: bool = None,
    mentions: bool = None,
    comments: bool = None,
    teams: bool = None,
    sessions: bool = None,
    quiet_start: int = None,
    quiet_end: int = None,
):
    """View or update notification preferences for a user.

    USER_ID is the user identifier.

    With no options, shows current preferences.
    With options, updates the specified settings.

    Examples:

        sindri notification-prefs user123

        sindri notification-prefs user123 --no-mentions

        sindri notification-prefs user123 --quiet-start 22 --quiet-end 7
    """
    from sindri.collaboration import NotificationStore

    async def manage_prefs():
        store = NotificationStore()

        # Check if any update flags provided
        has_updates = any(
            x is not None
            for x in [enabled, mentions, comments, teams, sessions, quiet_start, quiet_end]
        )

        if has_updates:
            # Update preferences
            prefs = await store.update_preferences(
                user_id=user_id,
                enabled=enabled,
                mention_enabled=mentions,
                comment_enabled=comments,
                team_enabled=teams,
                session_enabled=sessions,
                quiet_hours_start=quiet_start,
                quiet_hours_end=quiet_end,
            )
            console.print("[green]\u2713 Preferences updated[/green]\n")
        else:
            prefs = await store.get_preferences(user_id)

        # Display current preferences
        console.print(f"[bold]Notification Preferences for {user_id}[/bold]\n")

        status = "[green]Enabled[/green]" if prefs.enabled else "[red]Disabled[/red]"
        console.print(f"  Global: {status}")

        console.print("\n  [bold]Notification Types:[/bold]")
        console.print(f"    Mentions: {'[green]\u2713[/green]' if prefs.mention_enabled else '[red]\u2717[/red]'}")
        console.print(f"    Comments: {'[green]\u2713[/green]' if prefs.comment_enabled else '[red]\u2717[/red]'}")
        console.print(f"    Team events: {'[green]\u2713[/green]' if prefs.team_enabled else '[red]\u2717[/red]'}")
        console.print(f"    Session events: {'[green]\u2713[/green]' if prefs.session_enabled else '[red]\u2717[/red]'}")

        console.print("\n  [bold]Quiet Hours:[/bold]")
        if prefs.quiet_hours_start is not None and prefs.quiet_hours_end is not None:
            console.print(f"    {prefs.quiet_hours_start:02d}:00 - {prefs.quiet_hours_end:02d}:00")
        else:
            console.print("    Not configured")

    asyncio.run(manage_prefs())


@cli.command("notification-stats")
@click.option("--user", "-u", help="Show stats for specific user")
def notification_stats(user: str = None):
    """Show notification statistics.

    Examples:

        sindri notification-stats

        sindri notification-stats --user user123
    """
    from sindri.collaboration import NotificationStore

    async def show_stats():
        store = NotificationStore()

        stats = await store.get_statistics(user)

        if user:
            console.print(f"[bold]\U0001F514 Notification Statistics for {user}[/bold]\n")
        else:
            console.print("[bold]\U0001F514 Global Notification Statistics[/bold]\n")

        console.print(f"  Total notifications: {stats['total']}")
        console.print(f"  Unread: {stats['unread']}")
        console.print(f"  Read: {stats['read']}")
        console.print(f"  Archived: {stats['archived']}")

        if not user and "users_with_notifications" in stats:
            console.print(f"  Users with notifications: {stats['users_with_notifications']}")

        if user:
            # Also show type breakdown for user
            type_counts = await store.get_type_counts(user)
            if type_counts:
                console.print("\n  [bold]By Type:[/bold]")
                for notif_type, count in type_counts.items():
                    console.print(f"    {notif_type}: {count}")

    asyncio.run(show_stats())


# ============================================
# Phase 10.2: Activity Feed Commands
# ============================================


@cli.command("activity")
@click.argument("team_id")
@click.option("--limit", "-n", default=20, help="Maximum activities to show")
@click.option("--offset", "-o", default=0, help="Offset for pagination")
@click.option(
    "--type",
    "-t",
    "activity_type",
    type=click.Choice(
        [
            "session_created",
            "session_completed",
            "session_failed",
            "member_joined",
            "member_left",
            "comment_added",
            "session_shared",
        ]
    ),
    help="Filter by activity type",
)
@click.option("--user", "-u", "user_id", help="Filter by actor user ID")
def activity(
    team_id: str,
    limit: int = 20,
    offset: int = 0,
    activity_type: str = None,
    user_id: str = None,
):
    """List activity feed for a team.

    TEAM_ID is the team identifier.

    Examples:

        sindri activity team123

        sindri activity team123 --limit 50

        sindri activity team123 --type session_created

        sindri activity team123 --user user456
    """
    from rich.table import Table
    from sindri.collaboration import ActivityStore, ActivityType

    async def list_activities():
        store = ActivityStore()

        # Get activities
        if user_id:
            activities = await store.list_by_user(user_id, limit=limit, offset=offset)
            # Filter by team
            activities = [a for a in activities if a.team_id == team_id]
        else:
            type_filter = None
            if activity_type:
                type_filter = [ActivityType(activity_type)]

            activities = await store.list_by_team(
                team_id=team_id,
                limit=limit,
                offset=offset,
                activity_types=type_filter,
            )

        if not activities:
            console.print(f"[yellow]No activities found for team {team_id}[/]")
            return

        # Get total count
        total = await store.count_by_team(team_id)

        table = Table(title=f"Activity Feed for {team_id} ({total} total)")
        table.add_column("Time", width=16)
        table.add_column("Type", width=18)
        table.add_column("Actor", width=12)
        table.add_column("Message", width=40)

        type_icons = {
            "session_created": "\U0001F4C4",
            "session_completed": "\u2705",
            "session_failed": "\u274C",
            "session_resumed": "\u25B6",
            "task_started": "\U0001F3C3",
            "task_completed": "\u2713",
            "task_delegated": "\U0001F4E4",
            "comment_added": "\U0001F4AC",
            "comment_resolved": "\u2714",
            "comment_replied": "\U0001F5E8",
            "member_joined": "\U0001F44B",
            "member_left": "\U0001F6AA",
            "member_role_changed": "\U0001F451",
            "member_invited": "\u2709",
            "session_shared": "\U0001F517",
            "share_revoked": "\U0001F512",
            "team_created": "\U0001F389",
            "team_updated": "\u270E",
            "team_settings_changed": "\u2699",
        }

        for a in activities:
            time_str = a.created_at.strftime("%Y-%m-%d %H:%M")
            icon = type_icons.get(a.type.value, "\U0001F4DD")

            table.add_row(
                time_str,
                f"{icon} {a.type.value}",
                a.actor_id[:12],
                a.message[:40] + ("..." if len(a.message) > 40 else ""),
            )

        console.print(table)

        if total > offset + len(activities):
            console.print(
                f"\n[dim]Showing {offset + 1}-{offset + len(activities)} of {total}. "
                f"Use --offset {offset + limit} to see more.[/dim]"
            )

    asyncio.run(list_activities())


@cli.command("activity-stats")
@click.option("--team", "-t", "team_id", help="Show stats for specific team")
def activity_stats(team_id: str = None):
    """Show activity feed statistics.

    Examples:

        sindri activity-stats

        sindri activity-stats --team team123
    """
    from sindri.collaboration import ActivityStore

    async def show_stats():
        store = ActivityStore()
        stats = await store.get_stats(team_id)

        if team_id:
            console.print(f"[bold]\U0001F4CA Activity Statistics for {team_id}[/bold]\n")
        else:
            console.print("[bold]\U0001F4CA Global Activity Statistics[/bold]\n")

        console.print(f"  Total activities: {stats['total_activities']}")
        console.print(f"  Last 24 hours: {stats['last_24h']}")

        if stats.get("by_type"):
            console.print("\n  [bold]By Type:[/bold]")
            for act_type, count in stats["by_type"].items():
                console.print(f"    {act_type}: {count}")

        if stats.get("most_active_users"):
            console.print("\n  [bold]Most Active Users:[/bold]")
            for user in stats["most_active_users"]:
                console.print(f"    {user['user_id']}: {user['count']} activities")

    asyncio.run(show_stats())


@cli.command("activity-cleanup")
@click.option(
    "--days",
    "-d",
    default=90,
    help="Delete activities older than this many days (default: 90)",
)
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without deleting")
def activity_cleanup(days: int = 90, dry_run: bool = False):
    """Clean up old activities from the activity feed.

    Examples:

        sindri activity-cleanup

        sindri activity-cleanup --days 30

        sindri activity-cleanup --days 30 --dry-run
    """
    from datetime import datetime, timedelta
    from sindri.collaboration import ActivityStore

    async def cleanup():
        store = ActivityStore()

        if dry_run:
            # Count what would be deleted
            cutoff = datetime.now() - timedelta(days=days)
            stats = await store.get_stats()
            console.print(
                f"[yellow]Dry run: Would delete activities older than {cutoff.strftime('%Y-%m-%d')} ({days} days)[/]"
            )
            console.print(f"[yellow]Total activities in database: {stats['total_activities']}[/]")
        else:
            deleted = await store.delete_old(days_old=days)
            console.print(f"[green]\u2713 Deleted {deleted} activities older than {days} days[/]")

    asyncio.run(cleanup())


# ============================================
# Phase 10: Webhook Commands
# ============================================


@cli.command("webhooks")
@click.argument("team_id")
@click.option("--enabled-only", "-e", is_flag=True, help="Show only enabled webhooks")
def webhooks(team_id: str, enabled_only: bool = False):
    """List webhooks for a team.

    TEAM_ID is the team identifier.

    Examples:

        sindri webhooks team123

        sindri webhooks team123 --enabled-only
    """
    from rich.table import Table
    from sindri.collaboration import WebhookStore

    async def list_webhooks():
        store = WebhookStore()
        hooks = await store.get_team_webhooks(team_id, enabled_only=enabled_only)

        if not hooks:
            console.print(f"[yellow]No webhooks found for team {team_id}[/]")
            return

        table = Table(title=f"Webhooks for Team {team_id}")
        table.add_column("ID", width=12)
        table.add_column("Name", width=20)
        table.add_column("URL", width=30)
        table.add_column("Format", width=10)
        table.add_column("Events", width=20)
        table.add_column("Status", width=10)

        for hook in hooks:
            status = "[green]Enabled[/]" if hook.enabled else "[red]Disabled[/]"
            events = ", ".join(e.value[:15] for e in hook.events[:3])
            if len(hook.events) > 3:
                events += f" (+{len(hook.events) - 3})"

            table.add_row(
                hook.id[:12],
                hook.name[:20],
                hook.url[:30],
                hook.format.value,
                events,
                status,
            )

        console.print(table)
        console.print(f"\n[dim]Use 'sindri webhook-info <id>' for details[/dim]")

    asyncio.run(list_webhooks())


@cli.command("webhook-create")
@click.argument("team_id")
@click.argument("name")
@click.argument("url")
@click.option(
    "--event",
    "-e",
    "events",
    multiple=True,
    help="Event types to subscribe to (can specify multiple)",
)
@click.option(
    "--format",
    "-f",
    "fmt",
    type=click.Choice(["generic", "slack", "discord"]),
    default="generic",
    help="Payload format",
)
@click.option("--description", "-d", default="", help="Webhook description")
@click.option("--retry-count", "-r", default=3, help="Number of retries on failure")
@click.option("--timeout", "-t", default=30, help="Request timeout in seconds")
@click.option("--created-by", "-u", help="User ID creating the webhook")
def webhook_create(
    team_id: str,
    name: str,
    url: str,
    events: tuple,
    fmt: str,
    description: str,
    retry_count: int,
    timeout: int,
    created_by: str = None,
):
    """Create a new webhook for a team.

    TEAM_ID is the team identifier.
    NAME is a human-readable name for the webhook.
    URL is the endpoint to deliver webhooks to.

    Examples:

        sindri webhook-create team123 "Session Alerts" https://example.com/webhook

        sindri webhook-create team123 "Slack Notifier" https://hooks.slack.com/... \\
            --format slack --event session.completed --event session.failed

        sindri webhook-create team123 "Discord Bot" https://discord.com/api/webhooks/... \\
            --format discord --event "*"
    """
    from sindri.collaboration import WebhookStore, WebhookEventType, WebhookFormat

    async def create():
        store = WebhookStore()

        # Parse events
        event_list = []
        for e in events:
            if e == "*":
                event_list.append(WebhookEventType.ALL)
            else:
                try:
                    event_list.append(WebhookEventType(e))
                except ValueError:
                    console.print(f"[red]Unknown event type: {e}[/]")
                    console.print(
                        f"[dim]Valid events: {', '.join(et.value for et in WebhookEventType)}[/]"
                    )
                    return

        # Default to all events if none specified
        if not event_list:
            event_list = [WebhookEventType.ALL]

        # Parse format
        format_map = {
            "generic": WebhookFormat.GENERIC,
            "slack": WebhookFormat.SLACK,
            "discord": WebhookFormat.DISCORD,
        }

        webhook = await store.create_webhook(
            team_id=team_id,
            name=name,
            url=url,
            events=event_list,
            format=format_map[fmt],
            description=description,
            retry_count=retry_count,
            timeout_seconds=timeout,
            created_by=created_by,
        )

        console.print(f"[green]\u2713 Webhook created successfully[/green]")
        console.print(f"\n  [bold]ID:[/bold] {webhook.id}")
        console.print(f"  [bold]Name:[/bold] {webhook.name}")
        console.print(f"  [bold]URL:[/bold] {webhook.url}")
        console.print(f"  [bold]Secret:[/bold] {webhook.secret}")
        console.print(f"  [bold]Events:[/bold] {', '.join(e.value for e in webhook.events)}")
        console.print(
            f"\n[yellow]\u26A0 Save the secret! It won't be shown again.[/]"
        )

    asyncio.run(create())


@cli.command("webhook-info")
@click.argument("webhook_id")
@click.option("--show-secret", "-s", is_flag=True, help="Show the webhook secret")
def webhook_info(webhook_id: str, show_secret: bool = False):
    """Show detailed information about a webhook.

    WEBHOOK_ID is the webhook identifier.

    Example:
        sindri webhook-info abc12345
    """
    from sindri.collaboration import WebhookStore

    async def show_info():
        store = WebhookStore()
        webhook = await store.get_webhook(webhook_id)

        if not webhook:
            console.print(f"[red]Webhook not found: {webhook_id}[/]")
            return

        console.print(f"\n[bold]Webhook Details[/bold]")
        console.print(f"  [bold]ID:[/bold] {webhook.id}")
        console.print(f"  [bold]Name:[/bold] {webhook.name}")
        console.print(f"  [bold]Team:[/bold] {webhook.team_id}")
        console.print(f"  [bold]URL:[/bold] {webhook.url}")
        console.print(f"  [bold]Format:[/bold] {webhook.format.value}")
        console.print(f"  [bold]Status:[/bold] {'Enabled' if webhook.enabled else 'Disabled'}")
        console.print(f"  [bold]Events:[/bold] {', '.join(e.value for e in webhook.events)}")
        console.print(f"  [bold]Created:[/bold] {webhook.created_at.strftime('%Y-%m-%d %H:%M')}")
        if webhook.created_by:
            console.print(f"  [bold]Created By:[/bold] {webhook.created_by}")
        if webhook.description:
            console.print(f"  [bold]Description:[/bold] {webhook.description}")
        console.print(f"  [bold]Retry Count:[/bold] {webhook.retry_count}")
        console.print(f"  [bold]Timeout:[/bold] {webhook.timeout_seconds}s")

        if show_secret:
            console.print(f"  [bold]Secret:[/bold] {webhook.secret}")

        # Get delivery stats
        stats = await store.get_statistics(webhook_id=webhook.id)
        console.print(f"\n[bold]Delivery Statistics[/bold]")
        console.print(f"  Total: {stats['deliveries']['total']}")
        console.print(f"  Success: {stats['deliveries']['success']}")
        console.print(f"  Failed: {stats['deliveries']['failed']}")
        console.print(f"  Pending: {stats['deliveries']['pending']}")
        console.print(f"  Retrying: {stats['deliveries']['retrying']}")

    asyncio.run(show_info())


@cli.command("webhook-update")
@click.argument("webhook_id")
@click.option("--name", "-n", help="New name")
@click.option("--url", "-u", help="New URL")
@click.option("--enable/--disable", default=None, help="Enable or disable webhook")
@click.option("--description", "-d", help="New description")
@click.option("--retry-count", "-r", type=int, help="New retry count")
@click.option("--timeout", "-t", type=int, help="New timeout in seconds")
def webhook_update(
    webhook_id: str,
    name: str = None,
    url: str = None,
    enable: bool = None,
    description: str = None,
    retry_count: int = None,
    timeout: int = None,
):
    """Update a webhook configuration.

    WEBHOOK_ID is the webhook identifier.

    Examples:

        sindri webhook-update abc12345 --name "New Name"

        sindri webhook-update abc12345 --disable

        sindri webhook-update abc12345 --url https://new-url.com --enable
    """
    from sindri.collaboration import WebhookStore

    async def update():
        store = WebhookStore()

        webhook = await store.update_webhook(
            webhook_id=webhook_id,
            name=name,
            url=url,
            enabled=enable,
            description=description,
            retry_count=retry_count,
            timeout_seconds=timeout,
        )

        if not webhook:
            console.print(f"[red]Webhook not found: {webhook_id}[/]")
            return

        console.print(f"[green]\u2713 Webhook updated successfully[/green]")

    asyncio.run(update())


@cli.command("webhook-delete")
@click.argument("webhook_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def webhook_delete(webhook_id: str, yes: bool = False):
    """Delete a webhook.

    WEBHOOK_ID is the webhook identifier.

    Example:
        sindri webhook-delete abc12345
    """
    from sindri.collaboration import WebhookStore

    async def delete():
        store = WebhookStore()

        # Get webhook info first
        webhook = await store.get_webhook(webhook_id)
        if not webhook:
            console.print(f"[red]Webhook not found: {webhook_id}[/]")
            return

        if not yes:
            console.print(f"[yellow]About to delete webhook:[/]")
            console.print(f"  Name: {webhook.name}")
            console.print(f"  URL: {webhook.url}")
            if not click.confirm("Continue?"):
                console.print("[dim]Cancelled[/]")
                return

        deleted = await store.delete_webhook(webhook_id)
        if deleted:
            console.print(f"[green]\u2713 Webhook deleted[/green]")
        else:
            console.print(f"[red]Failed to delete webhook[/]")

    asyncio.run(delete())


@cli.command("webhook-regenerate-secret")
@click.argument("webhook_id")
def webhook_regenerate_secret(webhook_id: str):
    """Regenerate the secret for a webhook.

    WEBHOOK_ID is the webhook identifier.

    Example:
        sindri webhook-regenerate-secret abc12345
    """
    from sindri.collaboration import WebhookStore

    async def regenerate():
        store = WebhookStore()
        new_secret = await store.regenerate_secret(webhook_id)

        if not new_secret:
            console.print(f"[red]Webhook not found: {webhook_id}[/]")
            return

        console.print(f"[green]\u2713 Secret regenerated[/green]")
        console.print(f"\n  [bold]New Secret:[/bold] {new_secret}")
        console.print(f"\n[yellow]\u26A0 Update your webhook endpoint with the new secret![/]")

    asyncio.run(regenerate())


@cli.command("webhook-deliveries")
@click.argument("webhook_id")
@click.option(
    "--status",
    "-s",
    type=click.Choice(["pending", "success", "failed", "retrying"]),
    help="Filter by status",
)
@click.option("--limit", "-n", default=20, help="Maximum deliveries to show")
def webhook_deliveries(webhook_id: str, status: str = None, limit: int = 20):
    """List delivery history for a webhook.

    WEBHOOK_ID is the webhook identifier.

    Examples:

        sindri webhook-deliveries abc12345

        sindri webhook-deliveries abc12345 --status failed

        sindri webhook-deliveries abc12345 --limit 50
    """
    from rich.table import Table
    from sindri.collaboration import WebhookStore, DeliveryStatus

    async def list_deliveries():
        store = WebhookStore()

        status_filter = None
        if status:
            status_filter = DeliveryStatus(status)

        deliveries = await store.get_webhook_deliveries(
            webhook_id=webhook_id,
            status=status_filter,
            limit=limit,
        )

        if not deliveries:
            console.print(f"[yellow]No deliveries found[/]")
            return

        table = Table(title=f"Webhook Deliveries")
        table.add_column("ID", width=12)
        table.add_column("Event", width=20)
        table.add_column("Status", width=10)
        table.add_column("Code", width=6)
        table.add_column("Attempts", width=8)
        table.add_column("Time", width=16)

        status_colors = {
            "success": "green",
            "failed": "red",
            "pending": "yellow",
            "retrying": "cyan",
        }

        for d in deliveries:
            color = status_colors.get(d.status.value, "white")
            status_str = f"[{color}]{d.status.value}[/]"
            code = str(d.status_code) if d.status_code else "-"
            time_str = d.created_at.strftime("%Y-%m-%d %H:%M")

            table.add_row(
                d.id[:12],
                d.event_type.value,
                status_str,
                code,
                str(d.attempt_count),
                time_str,
            )

        console.print(table)

    asyncio.run(list_deliveries())


@cli.command("webhook-test")
@click.argument("webhook_id")
def webhook_test(webhook_id: str):
    """Send a test event to a webhook.

    WEBHOOK_ID is the webhook identifier.

    Example:
        sindri webhook-test abc12345
    """
    from sindri.collaboration import (
        WebhookStore,
        WebhookDeliveryService,
        WebhookEventType,
    )

    async def test():
        store = WebhookStore()
        webhook = await store.get_webhook(webhook_id)

        if not webhook:
            console.print(f"[red]Webhook not found: {webhook_id}[/]")
            return

        if not webhook.enabled:
            console.print(f"[yellow]\u26A0 Webhook is disabled, enabling for test...[/]")

        console.print(f"[cyan]Sending test event to: {webhook.url}[/]")

        service = WebhookDeliveryService(store)
        delivery = await service.deliver(
            webhook=webhook,
            event_type=WebhookEventType.SESSION_COMPLETED,
            data={
                "title": "Test Webhook",
                "message": "This is a test delivery from Sindri",
                "session_id": "test-session-123",
                "user": "test-user",
                "duration": "0s",
                "test": True,
            },
        )

        # Wait a moment for delivery
        await asyncio.sleep(1)

        # Check result
        delivery = await store.get_delivery(delivery.id)

        if delivery.status.value == "success":
            console.print(f"[green]\u2713 Test successful! HTTP {delivery.status_code}[/]")
        elif delivery.status.value == "retrying":
            console.print(f"[yellow]\u26A0 Delivery scheduled for retry[/]")
            if delivery.error_message:
                console.print(f"  Error: {delivery.error_message}")
        else:
            console.print(f"[red]\u2717 Test failed[/]")
            if delivery.error_message:
                console.print(f"  Error: {delivery.error_message}")
            if delivery.status_code:
                console.print(f"  HTTP Status: {delivery.status_code}")

    asyncio.run(test())


@cli.command("webhook-stats")
@click.option("--team", "-t", "team_id", help="Filter by team ID")
def webhook_stats(team_id: str = None):
    """Show webhook statistics.

    Examples:

        sindri webhook-stats

        sindri webhook-stats --team team123
    """
    from sindri.collaboration import WebhookStore

    async def show_stats():
        store = WebhookStore()
        stats = await store.get_statistics(team_id=team_id)

        if team_id:
            console.print(f"\n[bold]Webhook Statistics for Team {team_id}[/bold]")
        else:
            console.print("\n[bold]Global Webhook Statistics[/bold]")

        console.print(f"\n[bold]Webhooks:[/bold]")
        console.print(f"  Total: {stats['webhooks']['total']}")
        console.print(f"  Enabled: {stats['webhooks']['enabled']}")

        console.print(f"\n[bold]Deliveries:[/bold]")
        console.print(f"  Total: {stats['deliveries']['total']}")
        console.print(f"  Success: {stats['deliveries']['success']}")
        console.print(f"  Failed: {stats['deliveries']['failed']}")
        console.print(f"  Pending: {stats['deliveries']['pending']}")
        console.print(f"  Retrying: {stats['deliveries']['retrying']}")

        # Calculate success rate
        total = stats["deliveries"]["total"]
        if total > 0:
            success_rate = (stats["deliveries"]["success"] / total) * 100
            console.print(f"\n  Success Rate: {success_rate:.1f}%")

    asyncio.run(show_stats())


@cli.command("webhook-cleanup")
@click.option(
    "--days",
    "-d",
    default=7,
    help="Delete deliveries older than this many days (default: 7)",
)
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without deleting")
def webhook_cleanup(days: int = 7, dry_run: bool = False):
    """Clean up old webhook delivery records.

    Examples:

        sindri webhook-cleanup

        sindri webhook-cleanup --days 3

        sindri webhook-cleanup --dry-run
    """
    from sindri.collaboration import WebhookStore

    async def cleanup():
        store = WebhookStore()

        if dry_run:
            stats = await store.get_statistics()
            completed = stats["deliveries"]["success"] + stats["deliveries"]["failed"]
            console.print(
                f"[yellow]Dry run: Would delete completed deliveries older than {days} days[/]"
            )
            console.print(f"[yellow]Total completed deliveries in database: {completed}[/]")
        else:
            deleted = await store.cleanup_old_deliveries(days=days)
            console.print(
                f"[green]\u2713 Deleted {deleted} delivery records older than {days} days[/]"
            )

    asyncio.run(cleanup())


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
# Phase 9+: IDE Integration Commands
# ============================================


@cli.command()
@click.option(
    "--mode",
    "-m",
    type=click.Choice(["stdio", "http"]),
    default="stdio",
    help="Communication mode",
)
@click.option(
    "--port",
    "-p",
    type=int,
    default=9999,
    help="Port for HTTP mode (default: 9999)",
)
@click.option(
    "--work-dir",
    "-w",
    type=click.Path(exists=True),
    help="Working directory for file operations",
)
def ide(mode: str, port: int, work_dir: str = None):
    """Start IDE integration server.

    Provides JSON-RPC interface for IDE plugins (Neovim, VS Code, etc.).

    Modes:
    - stdio: Communication over stdin/stdout (for Neovim)
    - http: HTTP/WebSocket server (for VS Code, web editors)

    Examples:
        sindri ide                     # Start in stdio mode

        sindri ide --mode stdio        # Explicit stdio mode (for Neovim)

        sindri ide --mode http --port 9999  # Start HTTP server

        sindri ide --work-dir ~/projects/myapp  # Set working directory
    """
    from pathlib import Path

    from sindri.ide import IDEServer

    work_path = Path(work_dir).resolve() if work_dir else Path.cwd()

    if mode == "stdio":
        console.print("[dim]Starting Sindri IDE server (stdio mode)...[/dim]", err=True)

        async def run_stdio():
            server = IDEServer(work_dir=work_path)
            await server.run_stdio()

        try:
            asyncio.run(run_stdio())
        except KeyboardInterrupt:
            console.print("[dim]IDE server stopped[/dim]", err=True)

    elif mode == "http":
        console.print(
            f"[bold blue]Starting Sindri IDE server on port {port}[/bold blue]"
        )
        console.print(f"[dim]Working directory: {work_path}[/dim]")
        console.print("[dim]Press Ctrl+C to stop[/dim]")

        # HTTP mode would use FastAPI, sharing code with web server
        # For now, just show a message
        console.print("[yellow]HTTP mode not yet implemented. Use stdio mode.[/yellow]")
        console.print("[dim]For web access, use 'sindri web' instead.[/dim]")


@cli.command("ide-status")
def ide_status():
    """Check IDE integration status.

    Shows whether IDE server is running and connection information.
    """
    from pathlib import Path
    import shutil

    console.print("[bold]IDE Integration Status[/bold]\n")

    # Check if sindri executable is findable
    sindri_path = shutil.which("sindri")
    if sindri_path:
        console.print(f"[green]✓[/green] Sindri executable: {sindri_path}")
    else:
        console.print("[yellow]![/yellow] Sindri not in PATH")
        console.print("[dim]  Add to PATH or use full path in IDE config[/dim]")

    # Check Neovim plugin installation
    nvim_plugin_paths = [
        Path.home() / ".local/share/nvim/lazy/sindri.nvim",
        Path.home() / ".local/share/nvim/site/pack/sindri/start/sindri.nvim",
        Path.home() / ".config/nvim/lua/sindri",
    ]

    nvim_found = False
    for nvim_path in nvim_plugin_paths:
        if nvim_path.exists():
            console.print(f"[green]✓[/green] Neovim plugin: {nvim_path}")
            nvim_found = True
            break

    if not nvim_found:
        console.print("[dim]-[/dim] Neovim plugin: not installed")
        console.print("[dim]  Copy sindri/ide/nvim to your Neovim config[/dim]")

    # Show available features
    console.print("\n[bold]Available Features:[/bold]")
    features = [
        ("Task execution", "Run Sindri tasks from editor"),
        ("Code explanation", "Explain selected code"),
        ("Fix suggestions", "Get fixes for errors"),
        ("Test generation", "Generate tests for code"),
        ("Code refactoring", "Refactor selected code"),
        ("Symbol search", "Find symbols in codebase"),
        ("Agent info", "View agent capabilities"),
    ]

    for feature, desc in features:
        console.print(f"  [green]✓[/green] {feature}: {desc}")


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


if __name__ == "__main__":
    cli()
