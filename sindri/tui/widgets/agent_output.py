"""Streaming agent output display widget."""

from textual.widgets import RichLog
from rich.syntax import Syntax
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
        code_pattern = r"```(\w+)?\n(.*?)```"

        last_end = 0
        for match in re.finditer(code_pattern, text, re.DOTALL):
            # Write text before code block
            if match.start() > last_end:
                self.write(text[last_end : match.start()])

            # Write syntax highlighted code
            lang = match.group(1) or "python"
            code = match.group(2)
            try:
                syntax = Syntax(code, lang, theme="monokai", line_numbers=True)
                self.write(syntax)
            except Exception:
                # Fallback if syntax highlighting fails
                self.write(f"```{lang}\n{code}```")

            last_end = match.end()

        # Write remaining text
        if last_end < len(text):
            self.write(text[last_end:])

    def append_tool(self, name: str, result: str, success: bool = True):
        """Append a tool call result."""

        color = "green" if success else "red"
        icon = "✓" if success else "✗"

        # Truncate long results
        display_result = result[:200]
        if len(result) > 200:
            display_result += "..."

        self.write(f"\n[{color}]{icon} [Tool: {name}][/{color}] {display_result}")

    def append_iteration(self, iteration: int, agent: str):
        """Append an iteration marker."""
        self.write(f"\n[dim]─── Iteration {iteration} ({agent}) ───[/dim]")

    def clear_output(self):
        """Clear all output."""
        self.clear()
        self._current_agent = None
