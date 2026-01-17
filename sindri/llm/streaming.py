"""Streaming buffer for tool call detection in streamed responses.

Phase 6.3: Buffer accumulates tokens and detects tool calls in the stream.
"""

import re
import json
from dataclasses import dataclass, field
import structlog

log = structlog.get_logger()


@dataclass
class DetectedToolCall:
    """A tool call detected from streaming content."""

    name: str
    arguments: dict


@dataclass
class StreamingBuffer:
    """Buffer for accumulating and parsing streamed LLM output.

    Detects tool calls from text-based JSON patterns while streaming.
    Useful for models that don't support native tool calling.

    Usage:
        buffer = StreamingBuffer()
        for token in stream:
            buffer.add_token(token)
            # Token is safe to display unless we're in a tool call block
            if not buffer.in_tool_block:
                display(token)
        # After streaming, get any detected tool calls
        calls = buffer.get_tool_calls()
    """

    content: str = ""
    _tool_calls: list[DetectedToolCall] = field(default_factory=list)
    _in_json_block: bool = False
    _json_depth: int = 0
    _json_buffer: str = ""
    _pending_tokens: list[str] = field(default_factory=list)
    _last_processed_pos: int = 0  # Position up to which we've checked for patterns

    # Patterns that indicate start of a tool call
    TOOL_PATTERNS = [
        r"```json\s*\{",  # Markdown JSON block
        r'\{"name"\s*:\s*"',  # Direct JSON with name field
        r'\{"function"\s*:\s*"',  # Function calling format
        r'\{"tool"\s*:\s*"',  # Tool format
        r"<tool_call>\s*\{",  # XML-style wrapper
    ]

    @property
    def in_tool_block(self) -> bool:
        """Returns True if currently accumulating a potential tool call block."""
        return self._in_json_block

    def add_token(self, token: str) -> tuple[str, bool]:
        """Add a token to the buffer.

        Args:
            token: The token to add

        Returns:
            (displayable_text, is_tool_related) - text safe to display and flag
        """
        self.content += token

        # Check if we're starting a JSON block
        if not self._in_json_block:
            # Only check content after last processed position
            search_start = max(
                0, self._last_processed_pos - 50
            )  # Small overlap for context
            search_content = self.content[search_start:]

            # Check for tool call patterns in new content
            for pattern in self.TOOL_PATTERNS:
                match = re.search(pattern, search_content)
                if match:
                    self._in_json_block = True
                    self._json_buffer = ""
                    self._json_depth = 0

                    # Find where JSON starts (from the match position forward)
                    match_pos = search_start + match.start()
                    json_start = self._find_json_start(self.content, match_pos)

                    if json_start >= 0:
                        self._json_buffer = self.content[json_start:]
                        # Count initial depth
                        for char in self._json_buffer:
                            if char == "{":
                                self._json_depth += 1
                            elif char == "}":
                                self._json_depth -= 1
                        # Check if already complete
                        if self._json_depth == 0 and self._json_buffer.strip():
                            self._try_parse_tool_call()
                            self._in_json_block = False
                            self._json_buffer = ""
                            self._last_processed_pos = len(self.content)
                        # Don't display the JSON block
                        return ("", True)
                    break

            return (token, False)

        # We're in a JSON block - accumulate
        self._json_buffer += token

        # Track JSON depth to know when we've completed the object
        for char in token:
            if char == "{":
                self._json_depth += 1
            elif char == "}":
                self._json_depth -= 1
                if self._json_depth == 0:
                    # Complete JSON object - try to parse
                    self._try_parse_tool_call()
                    self._in_json_block = False
                    self._json_buffer = ""
                    self._last_processed_pos = len(self.content)
                    return ("", True)

        return ("", True)

    def _find_json_start(self, content: str, from_pos: int = 0) -> int:
        """Find where a JSON object starts in content.

        Args:
            content: The content to search
            from_pos: Start searching from this position

        Returns:
            Position of first '{' at or after from_pos, or -1 if not found
        """
        # Look for opening brace from the given position
        for i in range(from_pos, len(content)):
            if content[i] == "{":
                return i
        return -1

    def _try_parse_tool_call(self):
        """Try to parse accumulated JSON as a tool call."""
        # Clean up the buffer
        json_str = self._json_buffer.strip()

        # Remove markdown wrappers
        json_str = re.sub(r"^```json\s*", "", json_str)
        json_str = re.sub(r"\s*```$", "", json_str)
        json_str = re.sub(r"^<tool_call>\s*", "", json_str)
        json_str = re.sub(r"\s*</tool_call>$", "", json_str)

        try:
            data = json.loads(json_str)

            # Extract tool call (various formats)
            name = None
            arguments = {}

            if "name" in data:
                name = data["name"]
                arguments = data.get("arguments", data.get("parameters", {}))
            elif "function" in data:
                func = data["function"]
                name = func.get("name")
                arguments = func.get("arguments", {})
            elif "tool" in data:
                name = data["tool"]
                arguments = data.get("input", data.get("arguments", {}))

            if name:
                # Handle string arguments (some models double-encode)
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {"input": arguments}

                self._tool_calls.append(
                    DetectedToolCall(name=name, arguments=arguments)
                )
                log.info("tool_call_detected_from_stream", name=name)

        except json.JSONDecodeError as e:
            log.debug(
                "json_parse_failed_in_stream", error=str(e), buffer=json_str[:100]
            )

    def get_tool_calls(self) -> list[DetectedToolCall]:
        """Get all detected tool calls."""
        return self._tool_calls.copy()

    def get_display_content(self) -> str:
        """Get content that's safe to display (excludes tool call blocks)."""
        # Remove detected tool call patterns from content
        display = self.content

        # Remove markdown JSON blocks
        display = re.sub(r"```json\s*\{[^`]*\}\s*```", "[Tool Call]", display)

        # Remove inline JSON tool calls
        display = re.sub(r'\{"name"\s*:\s*"[^}]+\}', "[Tool Call]", display)

        # Remove XML-style tool calls
        display = re.sub(
            r"<tool_call>\s*\{[^<]*\}\s*</tool_call>", "[Tool Call]", display
        )

        return display.strip()

    def reset(self):
        """Reset the buffer for a new response."""
        self.content = ""
        self._tool_calls = []
        self._in_json_block = False
        self._json_depth = 0
        self._json_buffer = ""
        self._pending_tokens = []
        self._last_processed_pos = 0
