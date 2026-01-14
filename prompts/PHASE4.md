# Phase 4: Terminal User Interface (TUI)

Build a rich terminal interface using Textual for monitoring and controlling Sindri.

## Phase 4 Objectives

1. Textual app skeleton with reactive components
2. Task tree widget showing hierarchy
3. Real-time agent output streaming
4. Tool activity log
5. Model/VRAM status display
6. User input handling
7. Intervention system (pause, edit, cancel)

## TUI Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│  SINDRI v0.1.0                                              [?] Help   │
├──────────────────────────┬──────────────────────────────────────────────┤
│  TASKS                   │  AGENT OUTPUT                               │
│  ────────────────────    │  ─────────────────────────────────────────  │
│  ▼ [✓] Build REST API    │  [Huginn] Creating app.py...                │
│    ├─[✓] Create models   │                                             │
│    ├─[▶] Implement API   │  ```python                                  │
│    │   └─[·] Add routes  │  from flask import Flask                    │
│    └─[·] Write tests     │  app = Flask(__name__)                      │
│                          │  ...                                        │
│                          │  ```                                        │
│                          │                                             │
│                          │  [Tool: write_file] → app.py (245 bytes)    │
│                          │  [Tool: shell] → python -m pytest           │
│                          │                                             │
├──────────────────────────┼──────────────────────────────────────────────┤
│  MODELS                  │  INPUT                                      │
│  ────────────────────    │  ─────────────────────────────────────────  │
│  ● qwen2.5:14b   10.2GB  │  > Add authentication to the API           │
│  ○ deepseek:16b   -.--   │                                             │
│  ○ phi4:3.8b      -.--   │  [Enter] Send  [Ctrl+P] Pause  [Ctrl+C] Stop │
└──────────────────────────┴──────────────────────────────────────────────┘
```

## New Components

```
sindri/
├── tui/
│   ├── __init__.py
│   ├── app.py              # Main Textual app
│   ├── screens/
│   │   ├── __init__.py
│   │   ├── main.py         # Main workspace screen
│   │   └── help.py         # Help screen
│   ├── widgets/
│   │   ├── __init__.py
│   │   ├── task_tree.py    # Task hierarchy tree
│   │   ├── agent_output.py # Streaming output log
│   │   ├── tool_log.py     # Tool activity
│   │   ├── model_status.py # VRAM/model status
│   │   └── input_bar.py    # User input
│   └── styles/
│       └── sindri.tcss     # Textual CSS
```

## Implementation Details

### Dependencies Update

```toml
[project.optional-dependencies]
tui = ["textual>=0.89.0"]
```

### Main App (tui/app.py)

```python
"""Sindri TUI - Terminal interface for LLM orchestration."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer

from sindri.tui.screens.main import MainScreen
from sindri.tui.screens.help import HelpScreen

class SindriApp(App):
    """The Sindri terminal user interface."""
    
    TITLE = "Sindri"
    SUB_TITLE = "Local LLM Orchestration"
    CSS_PATH = "styles/sindri.tcss"
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("?", "help", "Help"),
        Binding("ctrl+p", "pause", "Pause"),
        Binding("ctrl+c", "stop", "Stop", priority=True),
    ]
    
    def __init__(self, task: str = None, **kwargs):
        super().__init__(**kwargs)
        self.initial_task = task
        self.orchestrator = None  # Set by caller
        self._paused = False
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield MainScreen(id="main")
        yield Footer()
    
    def on_mount(self):
        """Start task if provided."""
        if self.initial_task:
            self.run_task(self.initial_task)
    
    async def run_task(self, task: str):
        """Start a new task."""
        main = self.query_one("#main", MainScreen)
        await main.start_task(task, self.orchestrator)
    
    def action_help(self):
        self.push_screen(HelpScreen())
    
    def action_pause(self):
        self._paused = not self._paused
        self.notify(f"{'Paused' if self._paused else 'Resumed'}")
    
    def action_stop(self):
        """Stop current task."""
        # Signal orchestrator to stop
        if self.orchestrator:
            self.orchestrator.request_stop()
        self.notify("Stopping...")

def run_tui(task: str = None, orchestrator = None):
    """Launch the TUI."""
    app = SindriApp(task=task)
    app.orchestrator = orchestrator
    app.run()
```

### Main Screen (tui/screens/main.py)

```python
"""Main workspace screen."""

from textual.screen import Screen
from textual.containers import Horizontal, Vertical
from textual.widgets import Static
from textual import on

from sindri.tui.widgets.task_tree import TaskTree
from sindri.tui.widgets.agent_output import AgentOutput
from sindri.tui.widgets.model_status import ModelStatus
from sindri.tui.widgets.input_bar import InputBar

class MainScreen(Screen):
    """Main workspace with task tree, output, and input."""
    
    def compose(self):
        with Horizontal():
            # Left panel
            with Vertical(id="left-panel"):
                yield TaskTree(id="tasks")
                yield ModelStatus(id="models")
            
            # Right panel
            with Vertical(id="right-panel"):
                yield AgentOutput(id="output")
                yield InputBar(id="input")
    
    async def start_task(self, task: str, orchestrator):
        """Start a task and stream output."""
        
        task_tree = self.query_one("#tasks", TaskTree)
        output = self.query_one("#output", AgentOutput)
        models = self.query_one("#models", ModelStatus)
        
        # Create root task in tree
        root_id = task_tree.add_task(task)
        
        # Hook up event handlers
        orchestrator.on_task_created = lambda t: task_tree.add_task(t.description, parent_id=t.parent_id)
        orchestrator.on_task_status = lambda t: task_tree.update_status(t.id, t.status)
        orchestrator.on_agent_output = lambda text: output.append(text)
        orchestrator.on_tool_call = lambda name, result: output.append_tool(name, result)
        orchestrator.on_model_loaded = lambda name, vram: models.set_active(name, vram)
        
        # Run
        await orchestrator.run(task)
    
    @on(InputBar.Submitted)
    async def on_input_submitted(self, event: InputBar.Submitted):
        """Handle user input."""
        output = self.query_one("#output", AgentOutput)
        output.append(f"[User] {event.value}")
        # Inject into current agent context
        if hasattr(self, 'orchestrator') and self.orchestrator:
            self.orchestrator.inject_user_input(event.value)
```

### Task Tree Widget (tui/widgets/task_tree.py)

```python
"""Hierarchical task display."""

from textual.widgets import Tree
from textual.widgets.tree import TreeNode

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

class TaskTree(Tree):
    """Display task hierarchy with status icons."""
    
    def __init__(self, **kwargs):
        super().__init__("Tasks", **kwargs)
        self._task_nodes: dict[str, TreeNode] = {}
    
    def add_task(
        self,
        description: str,
        task_id: str = None,
        parent_id: str = None,
        status: TaskStatus = TaskStatus.PENDING
    ) -> str:
        """Add a task to the tree."""
        
        import uuid
        task_id = task_id or str(uuid.uuid4())[:8]
        
        label = f"[{STATUS_ICONS[status]}] {description[:50]}"
        
        if parent_id and parent_id in self._task_nodes:
            parent_node = self._task_nodes[parent_id]
            node = parent_node.add(label, data={"id": task_id, "status": status})
        else:
            node = self.root.add(label, data={"id": task_id, "status": status})
        
        self._task_nodes[task_id] = node
        node.expand()
        return task_id
    
    def update_status(self, task_id: str, status: TaskStatus):
        """Update a task's status icon."""
        
        if task_id not in self._task_nodes:
            return
        
        node = self._task_nodes[task_id]
        old_label = str(node.label)
        
        # Replace status icon
        for old_status, icon in STATUS_ICONS.items():
            if f"[{icon}]" in old_label:
                new_label = old_label.replace(f"[{icon}]", f"[{STATUS_ICONS[status]}]")
                node.set_label(new_label)
                node.data["status"] = status
                break
```

### Agent Output Widget (tui/widgets/agent_output.py)

```python
"""Streaming agent output display."""

from textual.widgets import RichLog
from textual.widget import Widget
from rich.syntax import Syntax
from rich.panel import Panel
import re

class AgentOutput(RichLog):
    """Display streaming agent output with syntax highlighting."""
    
    def __init__(self, **kwargs):
        super().__init__(highlight=True, markup=True, **kwargs)
        self._current_agent = None
    
    def append(self, text: str, agent: str = None):
        """Append text, detecting code blocks for syntax highlighting."""
        
        if agent and agent != self._current_agent:
            self._current_agent = agent
            self.write(f"\n[bold blue][{agent}][/bold blue]")
        
        # Detect and highlight code blocks
        code_pattern = r'```(\w+)?\n(.*?)```'
        
        last_end = 0
        for match in re.finditer(code_pattern, text, re.DOTALL):
            # Write text before code block
            if match.start() > last_end:
                self.write(text[last_end:match.start()])
            
            # Write syntax highlighted code
            lang = match.group(1) or "python"
            code = match.group(2)
            syntax = Syntax(code, lang, theme="monokai", line_numbers=True)
            self.write(syntax)
            
            last_end = match.end()
        
        # Write remaining text
        if last_end < len(text):
            self.write(text[last_end:])
    
    def append_tool(self, name: str, result: str):
        """Append a tool call result."""
        
        success = not result.startswith("ERROR")
        color = "green" if success else "red"
        
        self.write(f"\n[{color}][Tool: {name}][/{color}] {result[:200]}")
```

### Model Status Widget (tui/widgets/model_status.py)

```python
"""Model and VRAM status display."""

from textual.widgets import Static
from textual.reactive import reactive

class ModelStatus(Static):
    """Display loaded models and VRAM usage."""
    
    models = reactive({})
    total_vram = reactive(16.0)
    used_vram = reactive(0.0)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._active_model = None
    
    def render(self) -> str:
        lines = ["[bold]Models[/bold]", ""]
        
        for name, vram in self.models.items():
            active = "●" if name == self._active_model else "○"
            lines.append(f"  {active} {name:20} {vram:.1f}GB")
        
        lines.append("")
        used_pct = (self.used_vram / self.total_vram) * 100
        bar_filled = int(used_pct / 5)
        bar = "█" * bar_filled + "░" * (20 - bar_filled)
        lines.append(f"  VRAM: [{bar}] {self.used_vram:.1f}/{self.total_vram:.1f}GB")
        
        return "\n".join(lines)
    
    def set_active(self, model: str, vram: float):
        """Set the currently active model."""
        self._active_model = model
        models = dict(self.models)
        models[model] = vram
        self.models = models
        self.used_vram = sum(self.models.values())
```

### Input Bar Widget (tui/widgets/input_bar.py)

```python
"""User input widget."""

from textual.widgets import Input
from textual.message import Message

class InputBar(Input):
    """Input bar for user commands and messages."""
    
    class Submitted(Message):
        """User submitted input."""
        def __init__(self, value: str):
            super().__init__()
            self.value = value
    
    def __init__(self, **kwargs):
        super().__init__(placeholder="Enter message or command...", **kwargs)
    
    def on_input_submitted(self, event: Input.Submitted):
        """Handle enter key."""
        if self.value.strip():
            self.post_message(self.Submitted(self.value))
            self.value = ""
```

### Styles (tui/styles/sindri.tcss)

```css
/* Sindri TUI Styles */

Screen {
    background: $surface;
}

#left-panel {
    width: 30%;
    min-width: 30;
    border-right: solid $primary;
}

#right-panel {
    width: 70%;
}

#tasks {
    height: 70%;
    border-bottom: solid $primary-darken-2;
}

#models {
    height: 30%;
    padding: 1;
}

#output {
    height: 1fr;
    border-bottom: solid $primary-darken-2;
}

#input {
    height: 3;
    dock: bottom;
}

TaskTree {
    padding: 1;
}

AgentOutput {
    padding: 1;
    scrollbar-gutter: stable;
}

ModelStatus {
    padding: 1;
}
```

### CLI Integration

Update `cli.py`:

```python
@cli.command()
@click.argument("task", required=False)
def tui(task: str = None):
    """Launch the interactive TUI."""
    
    from sindri.tui.app import run_tui
    from sindri.core.orchestrator import Orchestrator
    
    orchestrator = Orchestrator.create_default()
    run_tui(task=task, orchestrator=orchestrator)
```

## Event System

Create an event bus for TUI updates:

```python
# core/events.py

from dataclasses import dataclass
from typing import Callable, Any
from enum import Enum, auto

class EventType(Enum):
    TASK_CREATED = auto()
    TASK_STATUS_CHANGED = auto()
    AGENT_OUTPUT = auto()
    TOOL_CALLED = auto()
    MODEL_LOADED = auto()
    MODEL_UNLOADED = auto()
    ERROR = auto()

@dataclass
class Event:
    type: EventType
    data: Any

class EventBus:
    """Simple pub/sub event bus."""
    
    def __init__(self):
        self._handlers: dict[EventType, list[Callable]] = {}
    
    def subscribe(self, event_type: EventType, handler: Callable):
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
    
    def emit(self, event: Event):
        for handler in self._handlers.get(event.type, []):
            handler(event.data)
```

## Testing

1. Run TUI standalone: `sindri tui`
2. Run with task: `sindri tui "Create a hello world script"`
3. Test keyboard shortcuts work
4. Test task tree updates correctly
5. Test output streaming
6. Test user input injection

## Completion Criteria

Phase 4 is complete when:

1. ✅ TUI launches without errors
2. ✅ Task tree shows hierarchy with status icons
3. ✅ Agent output streams in real-time
4. ✅ Code blocks are syntax highlighted
5. ✅ Model status shows VRAM usage
6. ✅ User can input messages
7. ✅ Pause/stop controls work
8. ✅ Help screen displays

When complete: `<promise>PHASE4_COMPLETE</promise>`
