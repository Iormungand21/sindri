"""Main workspace screen."""

from textual.screen import Screen
from textual.containers import Horizontal
from textual.widgets import Input, Tree, RichLog
from textual import on

from sindri.core.events import EventBus, EventType
from sindri.core.tasks import TaskStatus


STATUS_ICONS = {
    TaskStatus.PENDING: "·",
    TaskStatus.PLANNING: "○",
    TaskStatus.WAITING: "◔",
    TaskStatus.RUNNING: "▶",
    TaskStatus.COMPLETE: "✓",
    TaskStatus.FAILED: "✗",
    TaskStatus.BLOCKED: "⚠",
}


class MainScreen(Screen):
    """Main workspace with task tree, output, and input."""

    def __init__(self, event_bus: EventBus = None, **kwargs):
        super().__init__(**kwargs)
        self.event_bus = event_bus or EventBus()
        self._task_nodes = {}
        self._setup_event_handlers()

    def compose(self):
        """Create child widgets."""
        with Horizontal():
            yield Tree("📋 Tasks", id="tasks")
            yield RichLog(highlight=True, markup=True, id="output")
        yield Input(placeholder="Type task and press Enter...", id="input")

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
            except Exception:
                pass

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
                            new_label = old_label.replace(
                                f"[{old_icon}]", f"[{new_icon}]"
                            )
                            node.set_label(new_label)
                            break
            except Exception:
                pass

        def on_agent_output(data):
            try:
                output = self.query_one("#output", RichLog)
                agent = data.get("agent")
                text = data.get("text", "")
                if agent:
                    output.write(f"\n[bold blue][{agent}][/bold blue]")
                output.write(text)
            except Exception:
                pass

        def on_tool_called(data):
            try:
                output = self.query_one("#output", RichLog)
                name = data.get("name", "unknown")
                success = data.get("success", True)
                result = data.get("result", "")[:200]
                color = "green" if success else "red"
                icon = "✓" if success else "✗"
                output.write(f"\n[{color}]{icon} [Tool: {name}][/{color}] {result}")
            except Exception:
                pass

        self.event_bus.subscribe(EventType.TASK_CREATED, on_task_created)
        self.event_bus.subscribe(EventType.TASK_STATUS_CHANGED, on_task_status)
        self.event_bus.subscribe(EventType.AGENT_OUTPUT, on_agent_output)
        self.event_bus.subscribe(EventType.TOOL_CALLED, on_tool_called)

    @on(Input.Submitted)
    async def on_input_submitted(self, event: Input.Submitted):
        """Handle user input."""
        if event.value.strip():
            output = self.query_one("#output", RichLog)
            output.write(f"\n[bold yellow][User][/bold yellow] {event.value}")

            input_widget = self.query_one("#input", Input)
            input_widget.value = ""

    def on_mount(self):
        """Called when screen is mounted."""
        output = self.query_one("#output", RichLog)
        output.write("[bold cyan]━━━ Sindri TUI ━━━[/bold cyan]")
        output.write("")
        output.write("[bold green]✓[/bold green] Ready to forge code")
        output.write("")
        output.write("[dim]Type task below and press Enter[/dim]")
        output.write("[dim]Press q to quit, ? for help[/dim]")

        tree = self.query_one("#tasks", Tree)
        tree.show_root = True
        tree.root.expand()

        self.query_one("#input", Input).focus()
