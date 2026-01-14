"""Completion detection for Sindri."""

import structlog

log = structlog.get_logger()


class CompletionDetector:
    """Detects when a task is complete."""

    def __init__(self, marker: str = "<sindri:complete/>"):
        self.marker = marker

    def is_complete(self, text: str) -> bool:
        """Check if completion marker is present in text."""
        is_done = self.marker in text
        if is_done:
            log.info("completion_detected", marker=self.marker)
        return is_done
