#!/usr/bin/env python
"""Simple TUI test."""

from textual.app import App
from textual.widgets import Header, Footer, Static
from textual.containers import Container

class TestWidget(Static):
    def render(self):
        return "Test Widget Working!"

class SimpleApp(App):
    def compose(self):
        yield Header()
        yield TestWidget()
        yield Footer()

if __name__ == "__main__":
    app = SimpleApp()
    app.run()
