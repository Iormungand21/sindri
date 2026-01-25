"""Tests for tool call parser."""

import pytest

from sindri.llm.tool_parser import ToolCallParser


@pytest.fixture
def parser():
    """Create a parser for testing."""
    return ToolCallParser()


def test_parse_json_block(parser):
    """Test parsing JSON in code blocks."""
    text = """
    I'll write the file now.

    ```json
    {
        "name": "write_file",
        "arguments": {
            "path": "test.txt",
            "content": "Hello, world!"
        }
    }
    ```
    """

    calls = parser.parse(text)

    assert len(calls) == 1
    assert calls[0].name == "write_file"
    assert calls[0].arguments["path"] == "test.txt"
    assert calls[0].arguments["content"] == "Hello, world!"


def test_parse_inline_json(parser):
    """Test parsing inline JSON."""
    text = 'Let me call {"name": "read_file", "arguments": {"path": "/tmp/test.txt"}} to read the file.'

    calls = parser.parse(text)

    assert len(calls) == 1
    assert calls[0].name == "read_file"
    assert calls[0].arguments["path"] == "/tmp/test.txt"


def test_parse_ollama_style(parser):
    """Test parsing Ollama-style function calls."""
    text = """
    ```json
    {
        "function": {
            "name": "shell",
            "arguments": {
                "command": "ls -la"
            }
        }
    }
    ```
    """

    calls = parser.parse(text)

    assert len(calls) == 1
    assert calls[0].name == "shell"
    assert calls[0].arguments["command"] == "ls -la"


def test_parse_multiple_calls(parser):
    """Test parsing multiple tool calls."""
    text = """
    First, let me read the file:
    ```json
    {"name": "read_file", "arguments": {"path": "test.txt"}}
    ```

    Then I'll write a new file:
    ```json
    {"name": "write_file", "arguments": {"path": "output.txt", "content": "data"}}
    ```
    """

    calls = parser.parse(text)

    assert len(calls) == 2
    assert calls[0].name == "read_file"
    assert calls[1].name == "write_file"


def test_parse_no_calls(parser):
    """Test text with no tool calls."""
    text = "I think this is a good approach. Let me explain the plan."

    calls = parser.parse(text)

    assert len(calls) == 0


def test_has_completion_marker(parser):
    """Test completion marker detection."""
    text_with_marker = "Task is done. <sindri:complete/>"
    text_without = "Still working on it."

    assert parser.has_completion_marker(text_with_marker)
    assert not parser.has_completion_marker(text_without)


def test_extract_thinking(parser):
    """Test extracting thinking from tool calls."""
    text = """
    <think>
    I need to first check if the file exists, then read it.
    </think>

    {"name": "read_file", "arguments": {"path": "test.txt"}}
    """

    thinking, remaining = parser.extract_thinking(text)

    assert "I need to first check" in thinking
    assert "read_file" in remaining
    assert "<think>" not in remaining


def test_parse_tool_format(parser):
    """Test parsing {"tool": ..., "args": ...} format."""
    text = '{"tool": "delegate", "args": {"agent": "huginn", "task": "Write code"}}'

    calls = parser.parse(text)

    assert len(calls) == 1
    assert calls[0].name == "delegate"
    assert calls[0].arguments["agent"] == "huginn"


# --- New tests for wrapped/array tool-call payloads ---


def test_parse_wrapped_tool_calls(parser):
    """Test parsing {"tool_calls": [...]} wrapper format."""
    text = """
    ```json
    {
        "tool_calls": [
            {"name": "read_file", "arguments": {"path": "a.txt"}},
            {"name": "write_file", "arguments": {"path": "b.txt", "content": "hello"}}
        ]
    }
    ```
    """

    calls = parser.parse(text)

    assert len(calls) == 2
    assert calls[0].name == "read_file"
    assert calls[0].arguments["path"] == "a.txt"
    assert calls[1].name == "write_file"
    assert calls[1].arguments["path"] == "b.txt"


def test_parse_array_tool_calls(parser):
    """Test parsing top-level array [...] format."""
    text = """
    ```json
    [
        {"name": "shell", "arguments": {"command": "ls"}},
        {"name": "shell", "arguments": {"command": "pwd"}}
    ]
    ```
    """

    calls = parser.parse(text)

    assert len(calls) == 2
    assert calls[0].name == "shell"
    assert calls[0].arguments["command"] == "ls"
    assert calls[1].name == "shell"
    assert calls[1].arguments["command"] == "pwd"


def test_parse_empty_array(parser):
    """Test graceful handling of empty arrays."""
    text = '{"tool_calls": []}'

    calls = parser.parse(text)

    assert len(calls) == 0


def test_parse_empty_top_level_array(parser):
    """Test graceful handling of empty top-level array."""
    text = "[]"

    calls = parser.parse(text)

    assert len(calls) == 0


def test_parse_inline_wrapped_tool_calls(parser):
    """Test parsing inline wrapped format without code block."""
    text = 'Here are my calls: {"tool_calls": [{"name": "read_file", "arguments": {"path": "x.py"}}]}'

    calls = parser.parse(text)

    assert len(calls) == 1
    assert calls[0].name == "read_file"
    assert calls[0].arguments["path"] == "x.py"


def test_parse_inline_array_tool_calls(parser):
    """Test parsing inline array format without code block."""
    text = 'Execute: [{"name": "shell", "arguments": {"command": "echo hi"}}]'

    calls = parser.parse(text)

    assert len(calls) == 1
    assert calls[0].name == "shell"
    assert calls[0].arguments["command"] == "echo hi"


def test_parse_wrapped_mixed_formats(parser):
    """Test wrapped array with mixed tool call formats inside."""
    text = """
    {
        "tool_calls": [
            {"name": "read_file", "arguments": {"path": "a.txt"}},
            {"function": "write_file", "arguments": {"path": "b.txt", "content": "x"}},
            {"tool": "shell", "args": {"command": "ls"}}
        ]
    }
    """

    calls = parser.parse(text)

    assert len(calls) == 3
    assert calls[0].name == "read_file"
    assert calls[1].name == "write_file"
    assert calls[2].name == "shell"


def test_parse_array_preserves_order(parser):
    """Test that array parsing preserves tool call order."""
    text = """
    [
        {"name": "step1", "arguments": {}},
        {"name": "step2", "arguments": {}},
        {"name": "step3", "arguments": {}},
        {"name": "step4", "arguments": {}}
    ]
    """

    calls = parser.parse(text)

    assert len(calls) == 4
    assert [c.name for c in calls] == ["step1", "step2", "step3", "step4"]


def test_parse_nested_wrapper_not_recursive(parser):
    """Test that nested tool_calls keys are not recursively unwrapped."""
    # This should extract only the outer wrapper's contents
    text = """
    {
        "tool_calls": [
            {"name": "outer_tool", "arguments": {"nested": {"tool_calls": []}}}
        ]
    }
    """

    calls = parser.parse(text)

    assert len(calls) == 1
    assert calls[0].name == "outer_tool"
    # The nested tool_calls should be preserved as argument data, not parsed
    assert calls[0].arguments["nested"]["tool_calls"] == []
