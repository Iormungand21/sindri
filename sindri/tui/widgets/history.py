"""Task history panel widget for browsing past sessions.

Phase 5.5: Task History Panel implementation.
Shows completed sessions with task descriptions, status, and timestamps.
"""

from textual.widgets import Static, ListView, ListItem
from textual.reactive import reactive
from textual.message import Message
from rich.text import Text
from typing import Optional
from datetime import datetime


class SessionSelected(Message):
    """Message sent when a session is selected in the history panel."""

    def __init__(self, session_id: str, task: str) -> None:
        self.session_id = session_id
        self.task = task
        super().__init__()


class SessionItem(ListItem):
    """A single session item in the history list."""

    def __init__(
        self,
        session_id: str,
        task: str,
        status: str,
        created_at: str,
        iterations: int,
        model: str,
    ) -> None:
        super().__init__()
        self.session_id = session_id
        self._task_text = task  # Avoid conflict with ListItem.task property
        self.status = status
        self.created_at = created_at
        self.iterations = iterations
        self.model = model

    @property
    def task_description(self) -> str:
        """Get the task description."""
        return self._task_text

    def compose(self):
        """Compose the session item display."""
        yield SessionItemContent(
            session_id=self.session_id,
            task=self._task_text,
            status=self.status,
            created_at=self.created_at,
            iterations=self.iterations,
            model=self.model,
        )


class SessionItemContent(Static):
    """Content display for a session item."""

    def __init__(
        self,
        session_id: str,
        task: str,
        status: str,
        created_at: str,
        iterations: int,
        model: str,
    ) -> None:
        super().__init__()
        self._session_id = session_id
        self._task = task
        self._status = status
        self._created_at = created_at
        self._iterations = iterations
        self._model = model

    def render(self) -> Text:
        """Render the session item."""
        text = Text()

        # Status icon
        status_icons = {
            "completed": ("green", "[OK]"),
            "active": ("cyan", "[~~]"),
            "failed": ("red", "[!!]"),
            "cancelled": ("yellow", "[--]"),
        }
        color, icon = status_icons.get(self._status, ("white", "[??]"))

        text.append(icon, style=color)
        text.append(" ")

        # Truncated task description
        task_display = self._task[:40] + "..." if len(self._task) > 40 else self._task
        text.append(task_display)
        text.append("\n")

        # Metadata line
        text.append("   ", style="dim")

        # Format timestamp
        try:
            dt = datetime.fromisoformat(self._created_at)
            time_str = dt.strftime("%m/%d %H:%M")
        except (ValueError, TypeError):
            time_str = str(self._created_at)[:16]

        text.append(time_str, style="dim")
        text.append(" | ", style="dim")
        text.append(f"{self._iterations} iter", style="dim cyan")
        text.append(" | ", style="dim")

        # Short model name
        model_short = self._model.split(":")[0] if ":" in self._model else self._model
        text.append(model_short[:12], style="dim magenta")

        return text


class TaskHistoryPanel(Static):
    """Panel showing past session history.

    Displays a scrollable list of past sessions with:
    - Task description (truncated)
    - Status indicator (completed, failed, active)
    - Timestamp
    - Iteration count
    - Model used

    Usage:
        panel = TaskHistoryPanel()
        await panel.load_sessions()  # Load from database
        # Or manually:
        panel.add_session("id", "task", "completed", "2026-01-15 10:00", 5, "qwen2.5")
    """

    sessions = reactive([], init=False)
    visible = reactive(True)

    DEFAULT_CSS = """
    TaskHistoryPanel {
        width: 100%;
        height: 100%;
        background: $surface;
        border: solid $primary;
    }

    TaskHistoryPanel > .history-header {
        dock: top;
        height: 1;
        background: $panel;
        text-align: center;
        text-style: bold;
    }

    TaskHistoryPanel > .history-empty {
        height: 100%;
        content-align: center middle;
        color: $text-muted;
    }

    TaskHistoryPanel ListView {
        height: 1fr;
    }

    TaskHistoryPanel ListItem {
        padding: 0 1;
        height: auto;
        min-height: 3;
    }

    TaskHistoryPanel ListItem:hover {
        background: $boost;
    }

    TaskHistoryPanel ListItem.-selected {
        background: $accent;
    }
    """

    def __init__(
        self,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._session_items: list[dict] = []

    def compose(self):
        """Compose the history panel."""
        yield Static("History", classes="history-header")
        yield ListView(id="history-list")

    def on_mount(self):
        """Initialize on mount."""
        self._update_display()

    def add_session(
        self,
        session_id: str,
        task: str,
        status: str,
        created_at: str,
        iterations: int,
        model: str,
    ) -> None:
        """Add a session to the history panel.

        Args:
            session_id: Unique session identifier
            task: Task description
            status: Session status (completed, active, failed, cancelled)
            created_at: ISO format timestamp
            iterations: Number of iterations
            model: Model used for the session
        """
        self._session_items.append({
            "session_id": session_id,
            "task": task,
            "status": status,
            "created_at": created_at,
            "iterations": iterations,
            "model": model,
        })
        self._update_display()

    def clear_sessions(self) -> None:
        """Clear all sessions from the panel."""
        self._session_items = []
        self._update_display()

    def set_sessions(self, sessions: list[dict]) -> None:
        """Set all sessions at once.

        Args:
            sessions: List of session dictionaries with keys:
                - id: Session ID
                - task: Task description
                - status: Session status
                - created_at: Timestamp
                - iterations: Iteration count
                - model: Model name
        """
        self._session_items = []
        for s in sessions:
            self._session_items.append({
                "session_id": s.get("id", ""),
                "task": s.get("task", "Unknown task"),
                "status": s.get("status", "unknown"),
                "created_at": s.get("created_at", ""),
                "iterations": s.get("iterations", 0),
                "model": s.get("model", "unknown"),
            })
        self._update_display()

    def _update_display(self) -> None:
        """Update the ListView with current sessions."""
        try:
            list_view = self.query_one("#history-list", ListView)
            list_view.clear()

            if not self._session_items:
                # Show empty message by adding a placeholder item
                list_view.append(ListItem(Static("[dim]No sessions yet[/dim]")))
                return

            for session in self._session_items:
                item = SessionItem(
                    session_id=session["session_id"],
                    task=session["task"],
                    status=session["status"],
                    created_at=session["created_at"],
                    iterations=session["iterations"],
                    model=session["model"],
                )
                list_view.append(item)

        except Exception:
            # Widget might not be mounted yet
            pass

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle session selection."""
        if isinstance(event.item, SessionItem):
            self.post_message(
                SessionSelected(
                    session_id=event.item.session_id,
                    task=event.item.task_description,
                )
            )

    async def load_sessions(self, limit: int = 20) -> None:
        """Load sessions from the database.

        Args:
            limit: Maximum number of sessions to load
        """
        from sindri.persistence.state import SessionState

        state = SessionState()
        sessions = await state.list_sessions(limit=limit)
        self.set_sessions(sessions)

    def get_session_count(self) -> int:
        """Return the number of sessions in the panel."""
        return len(self._session_items)

    def get_session_ids(self) -> list[str]:
        """Return list of session IDs in the panel."""
        return [s["session_id"] for s in self._session_items]
