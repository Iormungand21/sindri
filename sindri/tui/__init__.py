"""Sindri TUI - Terminal User Interface.

A rich terminal interface using Textual for monitoring and controlling
the Sindri LLM orchestration system.
"""

from sindri.tui.app import SindriApp, run_tui

__all__ = ["SindriApp", "run_tui"]
