"""Sindri TUI - Terminal interface for LLM orchestration."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer, Input, Tree, RichLog
from textual.containers import Horizontal
from typing import Optional
import asyncio

from sindri.tui.screens.help import HelpScreen
from sindri.core.events import EventBus, EventType, Event
from sindri.core.tasks import Task, TaskStatus


STATUS_ICONS = {
    TaskStatus.PENDING: "·",
    TaskStatus.PLANNING: "○",
    TaskStatus.WAITING: "◔",
    TaskStatus.RUNNING: "▶",
    TaskStatus.COMPLETE: "✓",
    TaskStatus.FAILED: "✗",
    TaskStatus.BLOCKED: "⚠",
}


class SindriApp(App):
    """The Sindri terminal user interface."""

    TITLE = "Sindri"
    SUB_TITLE = "Local LLM Orchestration"

    CSS = """
    Screen {
        background: $surface;
    }

    Horizontal {
        height: 1fr;
    }

    #tasks {
        width: 35%;
        border-right: wide $primary;
    }

    #output {
        width: 65%;
    }

    #input {
        dock: bottom;
        height: 3;
        border: tall $accent;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("?", "help", "Help"),
    ]

    def __init__(self, task: Optional[str] = None, orchestrator=None, event_bus=None, **kwargs):
        super().__init__(**kwargs)
        self.initial_task = task
        self.orchestrator = orchestrator
        self.event_bus = event_bus or EventBus()
        self._task_nodes = {}
        self._running_task = None

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header()
        with Horizontal():
            yield Tree("📋 Tasks", id="tasks")
            yield RichLog(highlight=True, markup=True, id="output")
        yield Input(placeholder="Enter task and press Enter...", id="input")
        yield Footer()

    def on_mount(self):
        """Initialize on mount."""
        # Write welcome message
        output = self.query_one("#output", RichLog)
        output.write("[bold cyan]━━━ Sindri TUI ━━━[/bold cyan]")
        output.write("")
        output.write("[green]✓[/green] Ready to forge code with local LLMs")
        output.write("")
        output.write("[dim]• Type a task in the input field below[/dim]")
        output.write("[dim]• Press Enter to submit[/dim]")
        output.write("[dim]• Press q to quit, ? for help[/dim]")

        # Expand task tree
        tree = self.query_one("#tasks", Tree)
        tree.show_root = True
        tree.root.expand()

        # Focus input
        self.query_one("#input", Input).focus()

        # Set up event handlers
        self._setup_event_handlers()

        # Run initial task if provided
        if self.initial_task and self.orchestrator:
            self.run_worker(self._run_task(self.initial_task))

    def _setup_event_handlers(self):
        """Set up event handlers for orchestrator events."""

        def on_task_created(data):
            try:
                tree = self.query_one("#tasks", Tree)
                desc = data.get("description", "Unknown")[:50]
                status = data.get("status", TaskStatus.PENDING)
                icon = STATUS_ICONS.get(status, "·")
                label = f"[{icon}] {desc}"

                task_id = data.get("task_id")
                parent_id = data.get("parent_id")

                if parent_id and parent_id in self._task_nodes:
                    node = self._task_nodes[parent_id].add(label)
                else:
                    node = tree.root.add(label)

                self._task_nodes[task_id] = node
                node.expand()
                self.refresh()
            except Exception as e:
                self.log(f"Error in task_created: {e}")

        def on_task_status(data):
            try:
                task_id = data.get("task_id")
                status = data.get("status")
                if task_id in self._task_nodes:
                    node = self._task_nodes[task_id]
                    old_label = str(node.label)
                    for old_status, old_icon in STATUS_ICONS.items():
                        if f"[{old_icon}]" in old_label:
                            new_icon = STATUS_ICONS.get(status, "·")
                            new_label = old_label.replace(f"[{old_icon}]", f"[{new_icon}]")
                            node.set_label(new_label)
                            break
                    self.refresh()
            except Exception as e:
                self.log(f"Error in task_status: {e}")

        def on_agent_output(data):
            try:
                output = self.query_one("#output", RichLog)
                agent = data.get("agent")
                text = data.get("text", "")
                if agent:
                    output.write(f"\n[bold blue][{agent}][/bold blue]")
                output.write(text)
            except Exception as e:
                self.log(f"Error in agent_output: {e}")

        def on_tool_called(data):
            try:
                output = self.query_one("#output", RichLog)
                name = data.get("name", "unknown")
                success = data.get("success", True)
                result = str(data.get("result", ""))[:200]
                color = "green" if success else "red"
                icon = "✓" if success else "✗"
                output.write(f"\n[{color}]{icon} [Tool: {name}][/{color}] {result}")
            except Exception as e:
                self.log(f"Error in tool_called: {e}")

        def on_iteration_start(data):
            try:
                output = self.query_one("#output", RichLog)
                iteration = data.get("iteration", 0)
                agent = data.get("agent", "unknown")
                output.write(f"\n[dim]─── Iteration {iteration} ({agent}) ───[/dim]")
            except Exception as e:
                self.log(f"Error in iteration_start: {e}")

        # Subscribe to events
        self.event_bus.subscribe(EventType.TASK_CREATED, on_task_created)
        self.event_bus.subscribe(EventType.TASK_STATUS_CHANGED, on_task_status)
        self.event_bus.subscribe(EventType.AGENT_OUTPUT, on_agent_output)
        self.event_bus.subscribe(EventType.TOOL_CALLED, on_tool_called)
        self.event_bus.subscribe(EventType.ITERATION_START, on_iteration_start)

    async def _run_task(self, task_description: str):
        """Run a task with the orchestrator."""
        output = self.query_one("#output", RichLog)

        try:
            output.write(f"\n[bold yellow]Starting task:[/bold yellow] {task_description}")

            # Create root task and emit event
            root_task = Task(
                description=task_description,
                task_type="orchestration",
                assigned_agent="brokkr",
                priority=0
            )

            self.event_bus.emit(Event(
                type=EventType.TASK_CREATED,
                data={
                    "task_id": root_task.id,
                    "description": task_description,
                    "status": TaskStatus.PENDING,
                    "parent_id": None
                }
            ))

            # Run the orchestrator (event_bus already wired in __init__)
            result = await self.orchestrator.run(task_description)

            # Update status
            status = TaskStatus.COMPLETE if result.get("success") else TaskStatus.FAILED
            self.event_bus.emit(Event(
                type=EventType.TASK_STATUS_CHANGED,
                data={"task_id": root_task.id, "status": status}
            ))

            if result.get("success"):
                output.write(f"\n[bold green]✓ Task completed successfully![/bold green]")
            else:
                error = result.get("error", "Unknown error")
                output.write(f"\n[bold red]✗ Task failed: {error}[/bold red]")

        except Exception as e:
            output.write(f"\n[bold red]✗ Error: {str(e)}[/bold red]")
            self.log(f"Task execution error: {e}")

        finally:
            self._running_task = None
            # Re-enable input
            input_widget = self.query_one("#input", Input)
            input_widget.disabled = False
            input_widget.focus()

    def on_input_submitted(self, event: Input.Submitted):
        """Handle input submission."""
        if not event.value.strip():
            return

        # Check if orchestrator is available
        if not self.orchestrator:
            output = self.query_one("#output", RichLog)
            output.write("\n[red]✗ Orchestrator not initialized[/red]")
            output.write("[dim]Launch TUI with: sindri tui[/dim]")
            event.input.value = ""
            return

        # Check if task is already running
        if self._running_task and not self._running_task.done():
            self.notify("Task already running", severity="warning")
            event.input.value = ""
            return

        # Disable input while running
        event.input.disabled = True

        # Start the task
        task = event.value.strip()
        event.input.value = ""
        self._running_task = self.run_worker(self._run_task(task))

    def action_help(self):
        """Show help screen."""
        self.push_screen(HelpScreen())


def run_tui(task: Optional[str] = None, orchestrator=None, event_bus=None):
    """Launch the TUI."""
    app = SindriApp(task=task, orchestrator=orchestrator, event_bus=event_bus)
    app.run()
