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


if __name__ == "__main__":
    cli()
