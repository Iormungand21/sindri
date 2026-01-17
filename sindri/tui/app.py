"""Sindri TUI - Terminal interface for LLM orchestration."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Input, Tree, RichLog
from textual.containers import Horizontal, Vertical
from typing import Optional

from sindri.tui.widgets.header import SindriHeader
from sindri.tui.widgets.history import TaskHistoryPanel, SessionSelected
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
    TaskStatus.CANCELLED: "⊗",
}


class SindriApp(App):
    """The Sindri terminal user interface."""

    TITLE = "Sindri"
    SUB_TITLE = "Local LLM Orchestration"

    CSS = """
    Screen {
        background: $surface;
    }

    #main-container {
        height: 1fr;
    }

    #left-pane {
        width: 35%;
        border-right: wide $primary;
    }

    #tasks {
        height: 60%;
        border-bottom: solid $primary;
    }

    #history-panel {
        height: 40%;
    }

    #history-panel.hidden {
        display: none;
    }

    #tasks.expanded {
        height: 100%;
    }

    #output {
        width: 65%;
    }

    #input {
        dock: bottom;
        height: 3;
        border: tall $accent;
    }

    /* Error styling for task tree */
    Tree > .tree--label {
        padding: 0 1;
    }

    .task-failed {
        background: $error 20%;
        color: $error;
    }

    .task-cancelled {
        background: $warning 20%;
        color: $warning;
    }

    .task-blocked {
        background: $warning 20%;
        color: $warning;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("?", "help", "Help"),
        Binding("ctrl+c", "cancel", "Cancel Task"),
        Binding("e", "export", "Export"),
        Binding("h", "toggle_history", "History"),
    ]

    def __init__(
        self, task: Optional[str] = None, orchestrator=None, event_bus=None, **kwargs
    ):
        super().__init__(**kwargs)
        self.initial_task = task
        self.orchestrator = orchestrator
        self.event_bus = event_bus or EventBus()
        self._task_nodes = {}
        self._running_task = None
        self._root_task_id = None  # Track root task for cancellation
        self._task_errors = {}  # Track task errors for display
        self._history_visible = True  # Phase 5.5: History panel visibility

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield SindriHeader()
        with Horizontal(id="main-container"):
            with Vertical(id="left-pane"):
                yield Tree("Tasks", id="tasks")
                yield TaskHistoryPanel(id="history-panel")
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

        # Show memory status if enabled
        if self.orchestrator and self.orchestrator.memory:
            try:
                # Get memory stats
                memory = self.orchestrator.memory
                indexed_files = memory.semantic.get_indexed_file_count()
                episodes_count = memory.episodic.get_episode_count()
                pattern_count = memory.get_pattern_count()

                output.write(
                    f"[dim]📚 Memory: {indexed_files} files, {episodes_count} episodes, {pattern_count} patterns[/dim]"
                )
                output.write("")

                # Update subtitle in header
                self.query_one(SindriHeader)
                self.sub_title = f"Memory: {indexed_files} files, {episodes_count} episodes, {pattern_count} patterns"
            except Exception as e:
                output.write(
                    f"[dim yellow]⚠ Memory system available (stats unavailable: {e})[/dim yellow]"
                )
                output.write("")
        else:
            output.write("[dim]📚 Memory system disabled[/dim]")
            output.write("")

        output.write("[dim]• Type a task in the input field below[/dim]")
        output.write("[dim]• Press Enter to submit[/dim]")
        output.write("[dim]• Press Ctrl+C to cancel running task[/dim]")
        output.write("[dim]• Press h to toggle history, e to export[/dim]")
        output.write("[dim]• Press q to quit, ? for help[/dim]")

        # Expand task tree
        tree = self.query_one("#tasks", Tree)
        tree.show_root = True
        tree.root.expand()

        # Focus input
        self.query_one("#input", Input).focus()

        # Set up event handlers
        self._setup_event_handlers()

        # Start VRAM monitor
        if self.orchestrator and hasattr(self.orchestrator, "model_manager"):
            self.set_interval(2.0, self._update_vram_stats)
            self._update_vram_stats()  # Initial update

        # Run initial task if provided
        if self.initial_task and self.orchestrator:
            self.run_worker(self._run_task(self.initial_task))

        # Phase 5.5: Load session history
        self.run_worker(self._load_history())

    async def _load_history(self):
        """Load session history into the history panel."""
        try:
            history_panel = self.query_one("#history-panel", TaskHistoryPanel)
            await history_panel.load_sessions(limit=20)
        except Exception as e:
            self.log(f"Error loading history: {e}")

    def _update_vram_stats(self):
        """Update VRAM stats in header."""
        try:
            if self.orchestrator and hasattr(self.orchestrator, "model_manager"):
                stats = self.orchestrator.model_manager.get_vram_stats()
                header = self.query_one(SindriHeader)
                header.update_vram(
                    used=stats["used"],
                    total=stats["total"],
                    loaded_models=stats["loaded_models"],
                )
        except Exception as e:
            self.log(f"Error updating VRAM stats: {e}")

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

                    # Update icon
                    for old_status, old_icon in STATUS_ICONS.items():
                        if f"[{old_icon}]" in old_label:
                            new_icon = STATUS_ICONS.get(status, "·")
                            base_label = old_label.replace(f"[{old_icon}]", "").strip()

                            # Add error message if task failed/cancelled
                            if (
                                status == TaskStatus.FAILED
                                and task_id in self._task_errors
                            ):
                                error_msg = self._task_errors[task_id]
                                new_label = f"[bold red][{new_icon}] {base_label}[/bold red]\n[dim red]    ↳ {error_msg[:60]}[/dim red]"
                            elif status == TaskStatus.CANCELLED:
                                new_label = f"[yellow][{new_icon}] {base_label}[/yellow] [dim](cancelled)[/dim]"
                            elif status == TaskStatus.BLOCKED:
                                new_label = f"[yellow][{new_icon}] {base_label}[/yellow] [dim](blocked)[/dim]"
                            elif status == TaskStatus.COMPLETE:
                                new_label = f"[green][{new_icon}] {base_label}[/green]"
                            elif status == TaskStatus.RUNNING:
                                new_label = f"[cyan][{new_icon}] {base_label}[/cyan]"
                            else:
                                new_label = f"[{new_icon}] {base_label}"

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

                if success:
                    output.write(
                        f"\n[green]✓ [Tool: {name}][/green] [dim]{result}[/dim]"
                    )
                else:
                    # Failed tool calls get prominent display
                    output.write("")
                    output.write(f"[bold red]✗ [Tool: {name}] FAILED[/bold red]")
                    output.write(f"[red]   {result}[/red]")
                    output.write("")
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

        def on_error(data):
            try:
                output = self.query_one("#output", RichLog)
                task_id = data.get("task_id")
                error_msg = data.get("error", "Unknown error")
                data.get("error_type", "error")

                # Store error for task tree display
                if task_id:
                    self._task_errors[task_id] = error_msg

                # Display error prominently in output
                output.write("")
                output.write("[bold red]━━━ ERROR ━━━[/bold red]")
                if task_id:
                    output.write(f"[red]Task:[/red] {task_id}")
                output.write(f"[red]Message:[/red] {error_msg}")
                output.write("[bold red]━━━━━━━━━━━━━[/bold red]")
                output.write("")

                # Show notification
                self.notify(f"Error: {error_msg[:50]}", severity="error", timeout=5)
            except Exception as e:
                self.log(f"Error in error handler: {e}")

        # Phase 6.3: Streaming token handlers
        def on_streaming_start(data):
            """Handle start of streaming response."""
            try:
                output = self.query_one("#output", RichLog)
                agent = data.get("agent", "unknown")
                output.write(f"\n[bold blue][{agent}][/bold blue] ", end="")
            except Exception as e:
                self.log(f"Error in streaming_start: {e}")

        def on_streaming_token(data):
            """Handle individual streaming token."""
            try:
                output = self.query_one("#output", RichLog)
                token = data.get("token", "")
                if token:
                    # Write token without newline for streaming effect
                    # Note: RichLog.write() adds newline, so we use write with end=""
                    output.write(token, end="")
            except Exception as e:
                self.log(f"Error in streaming_token: {e}")

        def on_streaming_end(data):
            """Handle end of streaming response."""
            try:
                output = self.query_one("#output", RichLog)
                # Add newline after streaming is complete
                output.write("")
            except Exception as e:
                self.log(f"Error in streaming_end: {e}")

        # Subscribe to events
        self.event_bus.subscribe(EventType.TASK_CREATED, on_task_created)
        self.event_bus.subscribe(EventType.TASK_STATUS_CHANGED, on_task_status)
        self.event_bus.subscribe(EventType.AGENT_OUTPUT, on_agent_output)
        self.event_bus.subscribe(EventType.TOOL_CALLED, on_tool_called)
        self.event_bus.subscribe(EventType.ITERATION_START, on_iteration_start)
        self.event_bus.subscribe(EventType.ERROR, on_error)
        # Phase 6.3: Streaming events
        self.event_bus.subscribe(EventType.STREAMING_START, on_streaming_start)
        self.event_bus.subscribe(EventType.STREAMING_TOKEN, on_streaming_token)
        self.event_bus.subscribe(EventType.STREAMING_END, on_streaming_end)

        # Phase 7.3: Planning events
        def on_plan_proposed(data):
            """Handle plan proposal event."""
            try:
                output = self.query_one("#output", RichLog)
                formatted_plan = data.get("formatted", "")
                step_count = data.get("step_count", 0)
                agents = data.get("agents", [])
                vram = data.get("estimated_vram_gb", 0)

                output.write("")
                output.write("[bold magenta]━━━ EXECUTION PLAN ━━━[/bold magenta]")
                output.write("")

                # Parse and display the plan nicely
                for line in formatted_plan.split("\n"):
                    if line.startswith("Plan:"):
                        output.write(f"[bold]{line}[/bold]")
                    elif line.strip().startswith(tuple("123456789")):
                        # Step line - highlight agent name
                        output.write(f"[cyan]{line}[/cyan]")
                    elif "Tools:" in line:
                        output.write(f"[dim]{line}[/dim]")
                    elif "Estimated VRAM:" in line or "Rationale:" in line:
                        output.write(f"[yellow]{line}[/yellow]")
                    elif "Risks:" in line:
                        output.write(f"[red]{line}[/red]")
                    elif line.strip().startswith("-"):
                        output.write(f"[dim red]{line}[/dim red]")
                    else:
                        output.write(line)

                output.write("")
                output.write(
                    f"[dim]Steps: {step_count} | Agents: {', '.join(agents)} | VRAM: ~{vram:.1f}GB[/dim]"
                )
                output.write("[bold magenta]━━━━━━━━━━━━━━━━━━━━━━[/bold magenta]")
                output.write("")

            except Exception as e:
                self.log(f"Error in plan_proposed: {e}")

        self.event_bus.subscribe(EventType.PLAN_PROPOSED, on_plan_proposed)

        # Phase 7.2: Pattern learning events
        def on_pattern_learned(data):
            """Handle pattern learned event."""
            try:
                output = self.query_one("#output", RichLog)
                pattern_id = data.get("pattern_id", "?")
                agent = data.get("agent", "unknown")
                iterations = data.get("iterations", 0)
                tools = data.get("tools", [])

                # Display a subtle notification about learning
                tool_str = ", ".join(tools[:3]) if tools else "no tools"
                if len(tools) > 3:
                    tool_str += f" +{len(tools) - 3}"

                output.write(
                    f"[dim green]📚 Pattern learned (#{pattern_id}) - "
                    f"{agent} in {iterations} iterations, tools: {tool_str}[/dim green]"
                )
            except Exception as e:
                self.log(f"Error in pattern_learned: {e}")

        self.event_bus.subscribe(EventType.PATTERN_LEARNED, on_pattern_learned)

        # Phase 5.5: Metrics update events
        def on_metrics_updated(data):
            """Handle metrics update event for real-time display."""
            try:
                header = self.query_one(SindriHeader)
                duration = data.get("duration_seconds", 0.0)
                iteration = data.get("iteration", 0)
                header.update_task_metrics(duration, iteration)
            except Exception as e:
                self.log(f"Error in metrics_updated: {e}")

        self.event_bus.subscribe(EventType.METRICS_UPDATED, on_metrics_updated)

    async def _run_task(self, task_description: str):
        """Run a task with the orchestrator."""
        output = self.query_one("#output", RichLog)

        try:
            output.write(
                f"\n[bold yellow]Starting task:[/bold yellow] {task_description}"
            )

            # Create root task and emit event
            root_task = Task(
                description=task_description,
                task_type="orchestration",
                assigned_agent="brokkr",
                priority=0,
            )

            # Store root task ID for cancellation
            self._root_task_id = root_task.id

            self.event_bus.emit(
                Event(
                    type=EventType.TASK_CREATED,
                    data={
                        "task_id": root_task.id,
                        "description": task_description,
                        "status": TaskStatus.PENDING,
                        "parent_id": None,
                    },
                )
            )

            # Run the orchestrator (event_bus already wired in __init__)
            result = await self.orchestrator.run(task_description)

            # Update status
            status = TaskStatus.COMPLETE if result.get("success") else TaskStatus.FAILED
            self.event_bus.emit(
                Event(
                    type=EventType.TASK_STATUS_CHANGED,
                    data={"task_id": root_task.id, "status": status},
                )
            )

            if result.get("success"):
                output.write("")
                output.write(
                    "[bold green]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold green]"
                )
                output.write("[bold green]✓ Task completed successfully![/bold green]")
                output.write(
                    "[bold green]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold green]"
                )
                output.write("")
            else:
                error = result.get("error", "Unknown error")
                task_output = result.get("output", "")

                output.write("")
                output.write("[bold red]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold red]")
                output.write("[bold red]✗ Task Failed[/bold red]")
                output.write(f"[red]Error:[/red] {error}")
                if task_output:
                    output.write(f"[dim]Output:[/dim] {task_output[:200]}")
                output.write("[bold red]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold red]")
                output.write("")

                # Show persistent notification
                self.notify(f"Task failed: {error[:50]}", severity="error", timeout=10)

        except Exception as e:
            output.write(f"\n[bold red]✗ Error: {str(e)}[/bold red]")
            self.log(f"Task execution error: {e}")

        finally:
            self._running_task = None
            self._root_task_id = None
            # Phase 5.5: Reset task metrics display
            try:
                header = self.query_one(SindriHeader)
                header.reset_task_metrics()
            except Exception:
                pass  # Header might not exist during shutdown
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

    def action_cancel(self):
        """Cancel the currently running task."""
        if not self._root_task_id or not self.orchestrator:
            self.notify("No task running", severity="warning")
            return

        if not self._running_task or self._running_task.done():
            self.notify("No task to cancel", severity="warning")
            return

        output = self.query_one("#output", RichLog)
        output.write("\n[bold yellow]⊗ Cancelling task...[/bold yellow]")

        # Request cancellation
        self.orchestrator.cancel_task(self._root_task_id)

        self.notify("Task cancellation requested", severity="information")

    def action_help(self):
        """Show help screen."""
        self.push_screen(HelpScreen())

    def action_export(self):
        """Export the most recent session to Markdown."""
        from pathlib import Path
        from sindri.persistence.state import SessionState
        from sindri.persistence.export import MarkdownExporter, generate_export_filename

        output = self.query_one("#output", RichLog)

        async def do_export():
            state = SessionState()
            sessions = await state.list_sessions(limit=10)

            # Find the most recent completed session
            completed = [s for s in sessions if s["status"] == "completed"]

            if not completed:
                output.write("\n[yellow]⚠ No completed sessions to export[/yellow]")
                self.notify("No completed sessions to export", severity="warning")
                return

            recent_session = completed[0]
            session = await state.load_session(recent_session["id"])

            if not session:
                output.write("\n[red]✗ Failed to load session[/red]")
                return

            # Export to current directory
            exporter = MarkdownExporter()
            filename = generate_export_filename(session)
            output_path = Path.cwd() / filename
            exporter.export_to_file(session, output_path)

            output.write(f"\n[green]✓ Exported session to {output_path}[/green]")
            output.write(f"[dim]Task: {session.task[:60]}...[/dim]")
            output.write(
                f"[dim]Turns: {len(session.turns)} | Model: {session.model}[/dim]"
            )

            self.notify(f"Exported to {filename}", severity="information")

        self.run_worker(do_export())

    def action_toggle_history(self):
        """Toggle visibility of the history panel."""
        try:
            history_panel = self.query_one("#history-panel", TaskHistoryPanel)
            tasks_tree = self.query_one("#tasks", Tree)

            self._history_visible = not self._history_visible

            if self._history_visible:
                history_panel.remove_class("hidden")
                tasks_tree.remove_class("expanded")
                self.notify("History panel shown", severity="information")
                # Refresh history when shown
                self.run_worker(self._load_history())
            else:
                history_panel.add_class("hidden")
                tasks_tree.add_class("expanded")
                self.notify("History panel hidden", severity="information")

        except Exception as e:
            self.log(f"Error toggling history: {e}")

    def on_session_selected(self, message: SessionSelected):
        """Handle session selection from history panel."""
        output = self.query_one("#output", RichLog)

        output.write("")
        output.write("[bold cyan]━━━ Session Selected ━━━[/bold cyan]")
        output.write(f"[dim]ID:[/dim] {message.session_id[:16]}...")
        output.write(f"[dim]Task:[/dim] {message.task[:60]}...")
        output.write("")
        output.write("[dim]Use 'sindri export <id>' to export this session[/dim]")
        output.write("[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]")

        self.notify(f"Session: {message.task[:30]}...", severity="information")


def run_tui(task: Optional[str] = None, orchestrator=None, event_bus=None):
    """Launch the TUI."""
    app = SindriApp(task=task, orchestrator=orchestrator, event_bus=event_bus)
    app.run()
