#!/usr/bin/env python
"""Minimal TUI test to verify Textual works."""

from textual.app import App
from textual.widgets import Header, Footer, Static, Input
from textual.containers import Horizontal

class MinimalApp(App):
    """Minimal test app."""

    CSS = """
    Horizontal {
        height: 1fr;
    }

    #left {
        width: 35%;
        border-right: wide blue;
    }

    #right {
        width: 65%;
    }

    Input {
        dock: bottom;
        height: 3;
    }
    """

    def compose(self):
        yield Header()
        with Horizontal():
            yield Static("LEFT PANEL (35%)\n\nIf you see this,\nTextual is working!", id="left")
            yield Static("RIGHT PANEL (65%)\n\nWidgets are rendering\ncorrectly!", id="right")
        yield Input(placeholder="Type here and press Enter...")
        yield Footer()

if __name__ == "__main__":
    app = MinimalApp()
    app.run()
