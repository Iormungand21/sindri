"""Parser for extracting tool calls from model text output.

For models that don't natively support function calling, this parser
extracts JSON-formatted tool calls from their text responses.
"""

import json
import re
from typing import Optional
from dataclasses import dataclass
import structlog

log = structlog.get_logger()


@dataclass
class ParsedToolCall:
    """A parsed tool call from text."""
    name: str
    arguments: dict


class ToolCallParser:
    """Extracts tool calls from model text output."""

    # Patterns for detecting tool calls in text
    JSON_BLOCK_PATTERN = re.compile(r'```json\s*(\{.*?\})\s*```', re.DOTALL)

    # More permissive inline JSON pattern - handles nested objects
    def _find_json_objects(self, text: str) -> list[str]:
        """Find JSON objects in text, handling nesting."""
        results = []
        brace_count = 0
        start_pos = None

        for i, char in enumerate(text):
            if char == '{':
                if brace_count == 0:
                    start_pos = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0 and start_pos is not None:
                    json_str = text[start_pos:i+1]
                    # Check if it looks like a tool call
                    if any(key in json_str for key in ['"name"', '"function"', '"tool"']):
                        results.append(json_str)
                    start_pos = None

        return results

    def parse(self, text: str) -> list[ParsedToolCall]:
        """Extract tool calls from text."""

        tool_calls = []

        # Try JSON code blocks first (```json ... ```)
        for match in self.JSON_BLOCK_PATTERN.finditer(text):
            try:
                data = json.loads(match.group(1))
                call = self._extract_from_json(data)
                if call:
                    tool_calls.append(call)
                    log.debug("parsed_tool_call_from_json_block", call=call.name)
            except json.JSONDecodeError:
                continue

        if tool_calls:
            return tool_calls

        # Try inline JSON (find all JSON objects)
        json_objects = self._find_json_objects(text)
        for json_str in json_objects:
            try:
                data = json.loads(json_str)
                call = self._extract_from_json(data)
                if call:
                    tool_calls.append(call)
                    log.debug("parsed_tool_call_from_inline_json", call=call.name)
            except json.JSONDecodeError:
                continue

        return tool_calls

    def _extract_from_json(self, data: dict) -> Optional[ParsedToolCall]:
        """Extract tool call from JSON object."""

        # Format 1: {"name": "tool_name", "arguments": {...}}
        if "name" in data and "arguments" in data:
            return ParsedToolCall(
                name=data["name"],
                arguments=data["arguments"]
            )

        # Format 2: {"function": "tool_name", "arguments": {...}}
        if "function" in data and "arguments" in data:
            return ParsedToolCall(
                name=data["function"],
                arguments=data["arguments"]
            )

        # Format 3: {"tool": "tool_name", "args": {...}}
        if "tool" in data and "args" in data:
            return ParsedToolCall(
                name=data["tool"],
                arguments=data["args"]
            )

        # Format 4: Ollama-style {"function": {"name": "...", "arguments": {...}}}
        if "function" in data and isinstance(data["function"], dict):
            func = data["function"]
            if "name" in func and "arguments" in func:
                return ParsedToolCall(
                    name=func["name"],
                    arguments=func["arguments"]
                )

        return None

    def has_completion_marker(self, text: str, marker: str = "<sindri:complete/>") -> bool:
        """Check if text contains completion marker."""
        return marker in text

    def extract_thinking(self, text: str) -> tuple[str, str]:
        """Separate thinking/reasoning from tool calls.

        Returns (thinking, remaining_text)
        """
        # Look for common reasoning patterns
        reasoning_end = -1

        # Check for explicit reasoning blocks
        if "<think>" in text.lower():
            start = text.lower().find("<think>")
            end = text.lower().find("</think>")
            if end > start:
                reasoning = text[start:end+8]
                remaining = text[:start] + text[end+8:]
                return reasoning.strip(), remaining.strip()

        # Check for "Let me" or "I will" patterns
        patterns = [
            r"(?:Let me|I will|I'll|First,|Here's what|My approach).*?(?=\{|```|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                reasoning = match.group(0)
                remaining = text[match.end():]
                return reasoning.strip(), remaining.strip()

        return "", text
