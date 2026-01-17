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
        super().__init__(
            placeholder="Enter message or command... (Ctrl+C to stop)", **kwargs
        )

    def on_input_submitted(self, event: Input.Submitted):
        """Handle enter key."""
        if self.value.strip():
            self.post_message(self.Submitted(self.value))
            self.value = ""
