"""Custom header widget with VRAM gauge and task metrics.

Phase 5.5: Added task duration and iteration display.
"""

from textual.widgets import Static
from textual.reactive import reactive
from rich.text import Text


class SindriHeader(Static):
    """Custom header with VRAM usage gauge and task metrics."""

    vram_used = reactive(0.0)
    vram_total = reactive(16.0)
    loaded_models = reactive([])
    # Phase 5.5: Task metrics
    task_duration = reactive(0.0)  # Current task duration in seconds
    current_iteration = reactive(0)  # Current iteration number

    DEFAULT_CSS = """
    SindriHeader {
        dock: top;
        width: 100%;
        background: $panel;
        color: $text;
        height: 1;
        content-align: center middle;
    }
    """

    def _get_title_subtitle(self) -> tuple[str, str | None]:
        """Get title and subtitle from app."""
        try:
            app = self.app
            title = getattr(app, "title", "Sindri")
            subtitle = getattr(app, "sub_title", None)
            return title, subtitle
        except Exception:
            return "Sindri", None

    def render(self) -> Text:
        """Render header with title and VRAM gauge."""
        text = Text()

        # Get app title and subtitle
        title, subtitle = self._get_title_subtitle()

        # Add title
        text.append(f" {title}", style="bold")

        # Add subtitle if present
        if subtitle:
            text.append(" — ", style="dim")
            text.append(subtitle, style="dim")

        # Add VRAM gauge
        if self.vram_total > 0:
            # Calculate percentage
            used_pct = min((self.vram_used / self.vram_total) * 100, 100)

            # Create bar (10 blocks for compact display)
            bar_length = 10
            bar_filled = int((used_pct / 100) * bar_length)
            bar = "█" * bar_filled + "░" * (bar_length - bar_filled)

            # Color based on usage
            if used_pct < 60:
                bar_color = "green"
            elif used_pct < 85:
                bar_color = "yellow"
            else:
                bar_color = "red"

            # Add gauge to header
            text.append(" │ VRAM: [", style="dim")
            text.append(bar, style=bar_color)
            text.append(f"] {self.vram_used:.1f}/{self.vram_total:.1f}GB", style="dim")

            # Show loaded models count if any
            if self.loaded_models:
                models_count = len(self.loaded_models)
                text.append(
                    f" ({models_count} model{'s' if models_count != 1 else ''})",
                    style="dim cyan",
                )

        # Phase 5.5: Show task metrics if running
        if self.task_duration > 0 or self.current_iteration > 0:
            text.append(" │ ", style="dim")
            if self.current_iteration > 0:
                text.append(f"Iter {self.current_iteration}", style="bold cyan")
                text.append(" ", style="dim")

            # Format duration
            if self.task_duration >= 60:
                mins = int(self.task_duration // 60)
                secs = int(self.task_duration % 60)
                duration_str = f"{mins}m{secs}s"
            else:
                duration_str = f"{self.task_duration:.1f}s"

            text.append(f"⏱ {duration_str}", style="yellow")

        return text

    def update_vram(self, used: float, total: float, loaded_models: list[str]):
        """Update VRAM stats."""
        self.vram_used = used
        self.vram_total = total
        self.loaded_models = loaded_models

    def update_task_metrics(self, duration: float, iteration: int):
        """Update task metrics display.

        Phase 5.5: Called from TUI app on METRICS_UPDATED events.

        Args:
            duration: Task duration in seconds
            iteration: Current iteration number
        """
        self.task_duration = duration
        self.current_iteration = iteration

    def reset_task_metrics(self):
        """Reset task metrics when task completes or is cleared."""
        self.task_duration = 0.0
        self.current_iteration = 0
