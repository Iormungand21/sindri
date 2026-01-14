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
def run(task: str, model: str, max_iter: int):
    """Run a task with Sindri."""

    console.print(Panel(f"[bold blue]Task:[/] {task}", title="Sindri"))

    async def execute():
        client = OllamaClient()
        tools = ToolRegistry.default()
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
def orchestrate(task: str, max_iter: int, vram_gb: float):
    """Run a task with hierarchical agents (Brokkr → Huginn/Mimir/Ratatoskr)."""

    console.print(Panel(f"[bold blue]Task:[/] {task}", title="🔨 Sindri Orchestration"))

    async def execute():
        from sindri.core.orchestrator import Orchestrator
        from sindri.core.loop import LoopConfig

        config = LoopConfig(max_iterations=max_iter)
        orchestrator = Orchestrator(config=config, total_vram_gb=vram_gb)

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
def resume(session_id: str):
    """Resume an interrupted session."""
    console.print(f"Resuming session {session_id}...")
    # TODO: Implement resume logic


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
def tui(task: str = None, no_memory: bool = False):
    """Launch the interactive TUI."""

    from sindri.tui.app import run_tui
    from sindri.core.orchestrator import Orchestrator
    from sindri.core.events import EventBus

    try:
        # Create shared event bus for TUI and orchestrator
        event_bus = EventBus()
        orchestrator = Orchestrator(enable_memory=not no_memory, event_bus=event_bus)
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
def doctor(config_path: str = None):
    """Check Sindri installation and configuration."""

    from sindri.config import SindriConfig, validate_config
    from rich.table import Table
    import ollama

    console.print("[bold cyan]🔨 Sindri Doctor[/bold cyan]\n")

    # Check Ollama
    console.print("[bold]1. Checking Ollama...[/]", end=" ")
    try:
        client = ollama.Client()
        models = client.list()
        model_count = len(models.get("models", []))
        console.print(f"[green]✓ OK[/green] ({model_count} models available)")

        # Show available models
        if model_count > 0:
            table = Table(show_header=True, box=None, padding=(0, 2))
            table.add_column("Model", style="cyan")
            table.add_column("Size", style="yellow", justify="right")

            for model in models["models"][:10]:  # Show first 10
                size_gb = model.get("size", 0) / 1e9
                table.add_row(model["name"], f"{size_gb:.1f} GB")

            console.print(table)
            if model_count > 10:
                console.print(f"[dim]... and {model_count - 10} more[/dim]\n")
    except Exception as e:
        console.print(f"[red]✗ FAIL[/red] ({e})")

    # Check config
    console.print("[bold]2. Loading configuration...[/]", end=" ")
    try:
        config = SindriConfig.load(config_path)
        console.print("[green]✓ OK[/green]")

        # Show config summary
        console.print(f"   Data dir: {config.data_dir}")
        console.print(f"   Ollama host: {config.ollama_host}")
        console.print(f"   VRAM: {config.total_vram_gb}GB total, {config.reserve_vram_gb}GB reserved")

        # Validate config
        warnings = validate_config(config)
        if warnings:
            console.print("\n[yellow]⚠ Configuration Warnings:[/yellow]")
            for w in warnings:
                console.print(f"  • {w}")
        else:
            console.print("   [green]No configuration warnings[/green]")

    except Exception as e:
        console.print(f"[red]✗ FAIL[/red] ({e})")

    # Check data directory
    console.print("\n[bold]3. Checking data directory...[/]", end=" ")
    try:
        data_dir = Path.home() / ".sindri"
        if data_dir.exists():
            db_path = data_dir / "sindri.db"
            db_exists = db_path.exists()
            db_size = db_path.stat().st_size / 1024 if db_exists else 0

            console.print(f"[green]✓ OK[/green]")
            console.print(f"   Path: {data_dir}")
            console.print(f"   Database: {'exists' if db_exists else 'not created'}")
            if db_exists:
                console.print(f"   DB size: {db_size:.1f} KB")

            # Check state directory
            state_dir = data_dir / "state"
            if state_dir.exists():
                checkpoints = len(list(state_dir.glob("*.checkpoint.json")))
                console.print(f"   Checkpoints: {checkpoints}")
        else:
            console.print(f"[yellow]⚠ Not created[/yellow]")
            console.print(f"   Will be created on first run: {data_dir}")
    except Exception as e:
        console.print(f"[red]✗ FAIL[/red] ({e})")

    # Check Python environment
    console.print("\n[bold]4. Checking Python environment...[/]", end=" ")
    try:
        import sys
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

        if sys.version_info >= (3, 11):
            console.print(f"[green]✓ OK[/green] (Python {python_version})")
        else:
            console.print(f"[yellow]⚠ WARNING[/yellow] (Python {python_version}, requires >=3.11)")
    except Exception as e:
        console.print(f"[red]✗ FAIL[/red] ({e})")

    # Check dependencies
    console.print("\n[bold]5. Checking dependencies...[/]")
    deps = [
        ("ollama", "Ollama client"),
        ("click", "CLI framework"),
        ("rich", "Terminal formatting"),
        ("pydantic", "Data validation"),
        ("structlog", "Logging"),
        ("textual", "TUI framework (optional)"),
    ]

    for module, description in deps:
        try:
            __import__(module)
            console.print(f"   [green]✓[/green] {description} ({module})")
        except ImportError:
            optional = "(optional)" in description
            color = "yellow" if optional else "red"
            status = "⚠" if optional else "✗"
            console.print(f"   [{color}]{status}[/{color}] {description} ({module}) - Not installed")

    console.print("\n[bold green]✓ Doctor check complete[/bold green]")


if __name__ == "__main__":
    cli()
