"""Help screen."""

from textual.screen import Screen
from textual.widgets import Static, MarkdownViewer
from textual.binding import Binding


HELP_TEXT = """# Sindri TUI Help

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `?` | Show this help |
| `q` | Quit Sindri |
| `Ctrl+P` | Pause/Resume execution |
| `Ctrl+C` | Stop current task |
| `Escape` | Close help screen |

## Task Tree Icons

| Icon | Status |
|------|--------|
| `·` | Pending |
| `○` | Planning |
| `◔` | Waiting |
| `▶` | Running |
| `✓` | Complete |
| `✗` | Failed |
| `⚠` | Blocked |

## Using the TUI

### Starting a Task

You can start Sindri with a task:
```bash
sindri tui "Your task description"
```

Or enter tasks in the input bar at the bottom.

### Task Hierarchy

The left panel shows a tree of tasks and subtasks. Tasks can delegate to other agents,
creating a hierarchy. The current status is shown with an icon.

### Agent Output

The right panel shows streaming output from agents, including:
- Agent messages and reasoning
- Syntax-highlighted code blocks
- Tool call results

### Model Status

The bottom-left panel shows:
- Currently loaded models
- VRAM usage per model
- Total VRAM utilization

## About Sindri

Sindri is a local-first LLM orchestration system with:
- **Hierarchical agents**: Specialized agents for different tasks
- **Memory system**: Codebase indexing and episodic memory
- **Local models**: Runs entirely on your hardware via Ollama

Press `Escape` to close this help screen.
"""


class HelpScreen(Screen):
    """Help documentation screen."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
    ]

    def compose(self):
        """Create child widgets."""
        yield MarkdownViewer(HELP_TEXT, show_table_of_contents=False)

    def action_dismiss(self):
        """Dismiss the help screen."""
        self.app.pop_screen()
