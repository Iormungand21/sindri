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
        structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True
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
@click.option("--work-dir", "-w", type=click.Path(), help="Working directory for file operations")
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
            console.print(f"[red]✗ {result.reason} after {result.iterations} iterations[/]")

        return result

    asyncio.run(execute())


@cli.command()
@click.argument("task")
@click.option("--max-iter", default=30, help="Maximum iterations per agent")
@click.option("--vram-gb", default=16.0, help="Total VRAM in GB")
@click.option("--no-memory", is_flag=True, help="Disable memory system")
@click.option("--work-dir", "-w", type=click.Path(), help="Working directory for file operations")
def orchestrate(task: str, max_iter: int, vram_gb: float, no_memory: bool, work_dir: str = None):
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
            work_dir=work_path
        )

        with console.status("[bold green]Orchestrating..."):
            result = await orchestrator.run(task)

        if result["success"]:
            console.print(f"[green]✓ Completed successfully[/]")
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
                console.print("[dim]Use 'sindri sessions' to list available sessions[/dim]")
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

        console.print(Panel(
            f"[bold blue]Session:[/] {full_session_id[:8]}\n"
            f"[dim]Task:[/] {session.task[:60]}...\n"
            f"[dim]Model:[/] {session.model}\n"
            f"[dim]Iterations:[/] {session.iterations}",
            title="🔨 Resuming Sindri Session"
        ))

        # Create orchestrator
        config = LoopConfig(max_iterations=max_iter)
        orchestrator = Orchestrator(
            config=config,
            total_vram_gb=vram_gb,
            enable_memory=True
        )

        # Create a task with the existing session_id to resume
        resume_task = Task(
            description=session.task,
            assigned_agent="brokkr",
            session_id=full_session_id,
            priority=0
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
                    console.print(f"[green]✓ Task completed[/]")
                else:
                    console.print(f"[red]✗ Task failed: {result.reason}[/]")
                    break

        # Show final status
        if resume_task.status.value == "complete":
            console.print(f"\n[green]✓ Session {full_session_id[:8]} completed successfully[/]")
            if resume_task.result:
                console.print(f"\n[dim]{resume_task.result}[/]")
        else:
            console.print(f"\n[yellow]Session {full_session_id[:8]} status: {resume_task.status.value}[/]")

    asyncio.run(execute_resume())


@cli.command()
def agents():
    """List all available agents."""
    from sindri.agents.registry import AGENTS
    from rich.table import Table

    table = Table(title="🔨 Sindri Agents", show_header=True, header_style="bold magenta")
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
            delegates
        )

    console.print(table)
    console.print(f"\n[dim]Total agents: {len(AGENTS)}[/dim]")


@cli.command()
def sessions():
    """List recent sessions."""

    async def show_sessions():
        state = SessionState()
        sessions = await state.list_sessions()

        if not sessions:
            console.print("[yellow]No sessions found[/]")
            return

        console.print("[bold]Recent sessions:[/]\n")
        for session in sessions:
            status_color = "green" if session["status"] == "completed" else "yellow"
            console.print(f"[{status_color}]●[/] {session['id'][:8]} - {session['task'][:50]}")
            console.print(f"   Model: {session['model']} | Iterations: {session['iterations']} | {session['created_at']}")
            console.print()

    asyncio.run(show_sessions())


@cli.command()
@click.argument("session_id", required=False)
@click.option("--aggregate", "-a", is_flag=True, help="Show aggregate statistics across all sessions")
@click.option("--tools", "-t", is_flag=True, help="Show tool breakdown")
@click.option("--limit", "-l", default=10, help="Number of sessions to list")
def metrics(session_id: str = None, aggregate: bool = False, tools: bool = False, limit: int = 10):
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
    from sindri.persistence.metrics import MetricsStore, SessionMetrics

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
                matching = [s for s in all_sessions if s["session_id"].startswith(session_id)]

                if not matching:
                    console.print(f"[red]✗ No metrics found for session {session_id}[/]")
                    console.print("[dim]Use 'sindri metrics' to list sessions with metrics[/dim]")
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
            time_table.add_row("LLM Inference", f"{summary['time_breakdown']['llm_inference']:.2f}s")
            time_table.add_row("Tool Execution", f"{summary['time_breakdown']['tool_execution']:.2f}s")
            time_table.add_row("Model Loading", f"{summary['time_breakdown']['model_loading']:.2f}s")

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

                    for tool_name, data in sorted(breakdown.items(), key=lambda x: x[1]["count"], reverse=True):
                        success_rate = data["successes"] / data["count"] * 100 if data["count"] > 0 else 0
                        success_color = "green" if success_rate == 100 else ("yellow" if success_rate >= 50 else "red")
                        tool_table.add_row(
                            tool_name,
                            str(data["count"]),
                            f"{data['total_time']:.2f}s",
                            f"{data['avg_time']:.3f}s",
                            f"[{success_color}]{success_rate:.0f}%[/{success_color}]"
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
                f"[{status_color}]{status_short}[/{status_color}]"
            )

        console.print(table)
        console.print(f"\n[dim]Use 'sindri metrics <session_id>' for details[/dim]")
        console.print("[dim]Use 'sindri metrics -a' for aggregate statistics[/dim]")

    asyncio.run(show_metrics())


@cli.command()
@click.argument("session_id")
@click.argument("output", required=False, type=click.Path())
@click.option("--no-metadata", is_flag=True, help="Exclude metadata section")
@click.option("--no-timestamps", is_flag=True, help="Exclude timestamps from turns")
def export(session_id: str, output: str = None, no_metadata: bool = False, no_timestamps: bool = False):
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
                console.print("[dim]Use 'sindri sessions' to list available sessions[/dim]")
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
            include_timestamps=not no_timestamps,
            include_metadata=not no_metadata
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
        console.print(f"[dim]Turns: {len(session.turns)} | Model: {session.model}[/dim]")

        return True

    asyncio.run(do_export())


@cli.command()
@click.argument("task", required=False)
@click.option("--no-memory", is_flag=True, help="Disable memory system")
@click.option("--work-dir", "-w", type=click.Path(), help="Working directory for file operations")
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
        orchestrator = Orchestrator(enable_memory=not no_memory, event_bus=event_bus, work_dir=work_path)
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
    from sindri.persistence.database import Database
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
            console.print(f"[green]✓ Checkpoint loaded[/]")
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
                s.get("timestamp", "")[:19]
            )

        console.print(table)
        console.print(f"\n[dim]Use 'sindri recover --session-id <id>' to load a checkpoint[/]")
        console.print(f"[dim]Use 'sindri resume <id>' to continue execution[/]")


@cli.command()
@click.option("--config-path", help="Path to config file to validate")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
def doctor(config_path: str = None, verbose: bool = False):
    """Check Sindri installation and configuration."""

    from sindri.core.doctor import get_all_checks
    from rich.table import Table
    from pathlib import Path

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
            console.print(f"     [dim]... and {len(results['models']['available']) - 5} more[/dim]")

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
            status = "[green]✓[/green]" if installed else ("[yellow]⚠[/yellow]" if is_optional else "[red]✗[/red]")
            optional_tag = " [dim](optional)[/dim]" if is_optional else ""
            console.print(f"     {status} {description} ({module}){optional_tag}")

    # Overall status
    console.print()
    if results["overall"]["all_passed"]:
        console.print("[bold green]✓ All checks passed - Sindri is ready![/bold green]")
    elif results["overall"]["critical_passed"]:
        console.print("[bold yellow]⚠ Some optional checks failed - Sindri should work[/bold yellow]")
    else:
        console.print("[bold red]✗ Critical checks failed - Sindri may not work correctly[/bold red]")
        console.print("[dim]Fix the issues above and run 'sindri doctor' again[/dim]")


def _print_check(num: int, check):
    """Helper to print a health check result."""
    from sindri.core.doctor import HealthCheck

    status = "[green]✓[/green]" if check.passed else "[red]✗[/red]"
    console.print(f"[bold]{num}. {check.name}:[/] {status} {check.message}")

    if check.details:
        # Indent details
        for line in check.details.split('\n'):
            console.print(f"   [dim]{line}[/dim]")


@cli.group()
def plugins():
    """Manage Sindri plugins."""
    pass


@plugins.command("list")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
def plugins_list(verbose: bool = False):
    """List installed plugins."""
    from pathlib import Path
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
        console.print("\n[dim]Create plugins in these directories to extend Sindri.[/dim]")
        return

    # Group by type
    tools = [p for p in plugins if p.info.type == PluginType.TOOL]
    agents = [p for p in plugins if p.info.type == PluginType.AGENT]

    # Tool plugins table
    if tools:
        table = Table(title="🔧 Tool Plugins", show_header=True, header_style="bold cyan")
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
        table = Table(title="🤖 Agent Plugins", show_header=True, header_style="bold magenta")
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
    console.print(f"\n[dim]Total: {len(plugins)} plugins ({counts.get('VALIDATED', 0)} validated, {counts.get('FAILED', 0)} failed)[/dim]")


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
        strict=strict
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
    from pathlib import Path
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
        console.print(f"\n[dim]Edit the file to implement your custom tool.[/dim]")

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
        console.print(f"\n[dim]Edit the file to customize your agent.[/dim]")


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
        console.print(f"  [green]✓[/green] Tool directory exists ({tool_count} .py files)")
    else:
        console.print(f"  [yellow]⚠[/yellow] Tool directory doesn't exist (run 'sindri plugins init' to create)")

    if agent_exists:
        agent_count = len(list(manager.agent_dir.glob("*.toml")))
        console.print(f"  [green]✓[/green] Agent directory exists ({agent_count} .toml files)")
    else:
        console.print(f"  [yellow]⚠[/yellow] Agent directory doesn't exist (run 'sindri plugins init' to create)")


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
        header_style="bold cyan"
    )
    table.add_column("Name", style="cyan", width=20)
    table.add_column("Status", width=10)
    table.add_column("Indexed", width=10)
    table.add_column("Tags", width=25)
    if verbose:
        table.add_column("Path", style="dim", width=40)

    for p in projects:
        status = "[green]enabled[/green]" if p.enabled else "[yellow]disabled[/yellow]"
        indexed = f"[green]{p.file_count} files[/green]" if p.indexed else "[dim]not indexed[/dim]"
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
    console.print(f"\n[dim]Total: {stats['total']} | Enabled: {stats['enabled']} | Indexed: {stats['indexed']}[/dim]")


@projects.command("add")
@click.argument("path", type=click.Path(exists=True))
@click.option("--name", "-n", help="Project name (default: directory name)")
@click.option("--tags", "-t", help="Tags (comma-separated)")
@click.option("--no-index", is_flag=True, help="Don't index immediately")
def projects_add(path: str, name: str = None, tags: str = None, no_index: bool = False):
    """Add a project to the registry."""
    from pathlib import Path
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
                console.print("[dim]You can index later with: sindri projects index <path>[/dim]")
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
        console.print(f"[red]✗[/red] Failed to remove project")


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
    from rich.table import Table
    from rich.syntax import Syntax
    from sindri.memory.global_memory import GlobalMemoryStore

    console.print(f"[dim]Searching for: {query}[/dim]\n")

    try:
        global_memory = GlobalMemoryStore()
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        results = global_memory.search(
            query,
            limit=limit,
            tags=tag_list,
            exclude_current=exclude
        )

        if not results:
            console.print("[yellow]No results found.[/yellow]")
            stats = global_memory.get_stats()
            console.print(f"\n[dim]Indexed: {stats['indexed_projects']} projects, {stats['total_chunks']} chunks[/dim]")
            return

        console.print(f"[green]Found {len(results)} results:[/green]\n")

        for i, result in enumerate(results, 1):
            console.print(f"[bold cyan]{i}. [{result.project_name}][/bold cyan] {result.file_path}")
            console.print(f"   Lines {result.start_line}-{result.end_line} | Similarity: {result.similarity:.2%}")
            if result.tags:
                console.print(f"   Tags: {', '.join(result.tags)}")

            # Show code preview (truncated)
            preview = result.content[:200] + "..." if len(result.content) > 200 else result.content
            console.print(f"   [dim]─────[/dim]")
            for line in preview.split('\n')[:5]:
                console.print(f"   [dim]{line}[/dim]")
            console.print()

    except Exception as e:
        console.print(f"[red]✗[/red] Search failed: {e}")
        console.print("[dim]Make sure projects are indexed: sindri projects index --all[/dim]")


@projects.command("index")
@click.argument("path", type=click.Path(), required=False)
@click.option("--all", "-a", "index_all", is_flag=True, help="Index all registered projects")
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
        console.print(f"\n[green]✓[/green] Indexed {len(results)} projects, {total_chunks} total chunks")

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
@click.option("--host", "-h", default="0.0.0.0", help="Host to bind to")
@click.option("--port", "-p", default=8000, help="Port to listen on")
@click.option("--vram-gb", default=16.0, help="Total VRAM in GB")
@click.option("--work-dir", "-w", type=click.Path(), help="Working directory for file operations")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def web(host: str, port: int, vram_gb: float, work_dir: str = None, reload: bool = False):
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
        from fastapi import FastAPI
    except ImportError:
        console.print("[red]✗ Web dependencies not installed[/red]")
        console.print("[dim]Install with: pip install sindri[web][/dim]")
        return

    from pathlib import Path

    console.print(Panel(
        f"[bold blue]Sindri Web API[/bold blue]\n\n"
        f"Host: {host}\n"
        f"Port: {port}\n"
        f"VRAM: {vram_gb}GB",
        title="🌐 Starting Server"
    ))

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
            log_level="info"
        )
    else:
        # Production mode
        app = create_app(vram_gb=vram_gb, work_dir=work_path)
        uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    cli()
