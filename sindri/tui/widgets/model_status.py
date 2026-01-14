"""Model and VRAM status display widget."""

from textual.widgets import Static
from textual.reactive import reactive
from rich.text import Text


class ModelStatus(Static):
    """Display loaded models and VRAM usage."""

    models = reactive({})
    total_vram = reactive(16.0)
    used_vram = reactive(0.0)

    def __init__(self, total_vram: float = 16.0, **kwargs):
        super().__init__(**kwargs)
        self.total_vram = total_vram
        self._active_model = None

    def render(self) -> Text:
        """Render the model status display."""
        text = Text()
        text.append("MODELS\n", style="bold")
        text.append("─" * 25 + "\n", style="dim")

        if not self.models:
            text.append("  No models loaded\n", style="dim")
        else:
            for name, vram in self.models.items():
                active = "●" if name == self._active_model else "○"
                style = "green" if name == self._active_model else "dim"

                # Truncate long model names
                display_name = name[:18] + "..." if len(name) > 18 else name

                text.append(f"  {active} ", style=style)
                text.append(f"{display_name:<20} ", style=style)
                text.append(f"{vram:>4.1f}GB\n", style=style)

        text.append("\n")

        # VRAM bar
        used = sum(self.models.values())
        used_pct = min((used / self.total_vram) * 100, 100) if self.total_vram > 0 else 0
        bar_length = 20
        bar_filled = int((used_pct / 100) * bar_length)

        bar = "█" * bar_filled + "░" * (bar_length - bar_filled)

        vram_color = "green" if used_pct < 70 else "yellow" if used_pct < 90 else "red"

        text.append("  VRAM: [", style="dim")
        text.append(bar, style=vram_color)
        text.append(f"] {used:.1f}/{self.total_vram:.1f}GB\n", style="dim")

        return text

    def set_active(self, model: str, vram: float):
        """Set the currently active model."""
        self._active_model = model
        models = dict(self.models)
        models[model] = vram
        self.models = models

    def unload_model(self, model: str):
        """Unload a model."""
        models = dict(self.models)
        if model in models:
            del models[model]
            self.models = models
            if self._active_model == model:
                self._active_model = None

    def clear_models(self):
        """Clear all models."""
        self.models = {}
        self._active_model = None
