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

    # Improved pattern - matches greedy to get full JSON block
    # Handles multiline and nested structures
    JSON_BLOCK_PATTERN = re.compile(r"```json\s*(\{.+?\})\s*```", re.DOTALL)

    # Alternative pattern without json marker
    CODE_BLOCK_PATTERN = re.compile(r"```\s*(\{.+?\})\s*```", re.DOTALL)

    def _find_json_objects(self, text: str) -> list[str]:
        """Find JSON objects in text, handling nesting and strings properly."""
        results = []
        brace_count = 0
        start_pos = None
        in_string = False
        escape_next = False

        for i, char in enumerate(text):
            # Handle escape sequences
            if escape_next:
                escape_next = False
                continue

            if char == "\\":
                escape_next = True
                continue

            # Handle strings (to ignore braces inside strings)
            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            # Only count braces outside of strings
            if not in_string:
                if char == "{":
                    if brace_count == 0:
                        start_pos = i
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0 and start_pos is not None:
                        json_str = text[start_pos : i + 1]
                        # Check if it looks like a tool call
                        if any(
                            key in json_str
                            for key in ['"name"', '"function"', '"tool"']
                        ):
                            results.append(json_str)
                        start_pos = None

        # If we have an unclosed JSON object, try to salvage it
        if brace_count > 0 and start_pos is not None:
            log.warning(
                "unclosed_json_detected",
                start_pos=start_pos,
                missing_braces=brace_count,
                preview=text[start_pos : start_pos + 100],
            )
            # Try to extract partial JSON for better error reporting
            partial = text[start_pos:]
            if any(key in partial for key in ['"name"', '"function"', '"tool"']):
                # Attempt to close the JSON
                closed = partial + ("}" * brace_count)
                results.append(closed)
                log.info("attempting_recovery_with_closed_braces", recovered=True)

        return results

    def parse(self, text: str) -> list[ParsedToolCall]:
        """Extract tool calls from text with multiple strategies."""

        tool_calls = []

        # Strategy 1: JSON code blocks with json marker (```json ... ```)
        for match in self.JSON_BLOCK_PATTERN.finditer(text):
            try:
                data = json.loads(match.group(1))
                call = self._extract_from_json(data)
                if call:
                    tool_calls.append(call)
                    log.info("parsed_tool_call_from_json_block", call=call.name)
            except json.JSONDecodeError as e:
                log.warning(
                    "json_block_decode_failed",
                    error=str(e),
                    json_preview=match.group(1)[:100],
                )
                continue

        if tool_calls:
            return tool_calls

        # Strategy 2: Code blocks without json marker (``` ... ```)
        for match in self.CODE_BLOCK_PATTERN.finditer(text):
            try:
                data = json.loads(match.group(1))
                call = self._extract_from_json(data)
                if call:
                    tool_calls.append(call)
                    log.info("parsed_tool_call_from_code_block", call=call.name)
            except json.JSONDecodeError:
                continue

        if tool_calls:
            return tool_calls

        # Strategy 3: Inline JSON (find all JSON objects with brace matching)
        json_objects = self._find_json_objects(text)
        log.debug("found_json_objects", count=len(json_objects))

        for i, json_str in enumerate(json_objects):
            try:
                data = json.loads(json_str)
                call = self._extract_from_json(data)
                if call:
                    tool_calls.append(call)
                    log.info("parsed_tool_call_from_inline_json", call=call.name)
            except json.JSONDecodeError as e:
                log.warning(
                    "inline_json_decode_failed",
                    attempt=i + 1,
                    error=str(e),
                    json_preview=json_str[:150],
                )
                # Try to fix common issues
                fixed_json = self._attempt_json_fix(json_str)
                if fixed_json:
                    try:
                        data = json.loads(fixed_json)
                        call = self._extract_from_json(data)
                        if call:
                            tool_calls.append(call)
                            log.info("parsed_tool_call_after_fix", call=call.name)
                    except json.JSONDecodeError:
                        continue

        if not tool_calls:
            log.warning(
                "no_tool_calls_extracted",
                text_length=len(text),
                has_braces="{" in text,
                has_json_marker="```json" in text,
                text_preview=text[:200],
            )

        return tool_calls

    def _attempt_json_fix(self, json_str: str) -> Optional[str]:
        """Attempt to fix common JSON issues."""
        # Remove trailing commas before closing braces/brackets
        fixed = re.sub(r",\s*([\]}])", r"\1", json_str)

        # Try to handle truncated strings - find last complete field
        if fixed.count('"') % 2 != 0:
            # Odd number of quotes - truncated string
            last_quote = fixed.rfind('"')
            if last_quote > 0:
                # Find the previous complete field
                prev_quote = fixed.rfind('"', 0, last_quote - 1)
                if prev_quote > 0:
                    # Truncate at the last complete field and close JSON
                    truncated = fixed[: prev_quote + 1]
                    # Count unclosed braces
                    open_braces = truncated.count("{") - truncated.count("}")
                    if open_braces > 0:
                        fixed = truncated + ("}" * open_braces)
                        log.info("attempted_truncation_fix", result_preview=fixed[:100])
                        return fixed

        return fixed if fixed != json_str else None

    def _extract_from_json(self, data: dict) -> Optional[ParsedToolCall]:
        """Extract tool call from JSON object."""

        # Format 1: {"name": "tool_name", "arguments": {...}}
        if "name" in data and "arguments" in data:
            return ParsedToolCall(name=data["name"], arguments=data["arguments"])

        # Format 2: {"function": "tool_name", "arguments": {...}}
        if "function" in data and "arguments" in data:
            return ParsedToolCall(name=data["function"], arguments=data["arguments"])

        # Format 3: {"tool": "tool_name", "args": {...}}
        if "tool" in data and "args" in data:
            return ParsedToolCall(name=data["tool"], arguments=data["args"])

        # Format 4: Ollama-style {"function": {"name": "...", "arguments": {...}}}
        if "function" in data and isinstance(data["function"], dict):
            func = data["function"]
            if "name" in func and "arguments" in func:
                return ParsedToolCall(name=func["name"], arguments=func["arguments"])

        return None

    def has_completion_marker(
        self, text: str, marker: str = "<sindri:complete/>"
    ) -> bool:
        """Check if text contains completion marker."""
        return marker in text

    def extract_thinking(self, text: str) -> tuple[str, str]:
        """Separate thinking/reasoning from tool calls.

        Returns (thinking, remaining_text)
        """
        # Look for common reasoning patterns

        # Check for explicit reasoning blocks
        if "<think>" in text.lower():
            start = text.lower().find("<think>")
            end = text.lower().find("</think>")
            if end > start:
                reasoning = text[start : end + 8]
                remaining = text[:start] + text[end + 8 :]
                return reasoning.strip(), remaining.strip()

        # Check for "Let me" or "I will" patterns
        patterns = [
            r"(?:Let me|I will|I'll|First,|Here's what|My approach).*?(?=\{|```|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                reasoning = match.group(0)
                remaining = text[match.end() :]
                return reasoning.strip(), remaining.strip()

        return "", text
