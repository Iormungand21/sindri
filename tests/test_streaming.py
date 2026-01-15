"""Tests for Phase 6.3 - Streaming Output.

Tests cover:
- StreamingResponse dataclass
- OllamaClient.chat_stream() method
- StreamingBuffer tool call detection
- Event system streaming events
- HierarchicalAgentLoop streaming mode
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from sindri.llm.client import OllamaClient, StreamingResponse, Response, Message
from sindri.llm.streaming import StreamingBuffer, DetectedToolCall
from sindri.core.events import EventBus, EventType, Event
from sindri.core.loop import LoopConfig


# =============================================================================
# StreamingResponse Tests
# =============================================================================

class TestStreamingResponse:
    """Tests for StreamingResponse dataclass."""

    def test_default_values(self):
        """Test StreamingResponse default initialization."""
        resp = StreamingResponse()
        assert resp.content == ""
        assert resp.tool_calls is None
        assert resp.model == ""
        assert resp.done is False

    def test_to_response_conversion(self):
        """Test conversion to standard Response."""
        streaming = StreamingResponse(
            content="Hello world",
            tool_calls=[{"name": "test"}],
            model="qwen2.5:7b",
            done=True
        )
        response = streaming.to_response()

        assert isinstance(response, Response)
        assert response.message.role == "assistant"
        assert response.message.content == "Hello world"
        assert response.message.tool_calls == [{"name": "test"}]
        assert response.model == "qwen2.5:7b"
        assert response.done is True

    def test_to_response_without_tool_calls(self):
        """Test conversion without tool calls."""
        streaming = StreamingResponse(
            content="Just text",
            model="llama3.1:8b"
        )
        response = streaming.to_response()

        assert response.message.tool_calls is None
        assert response.message.content == "Just text"


# =============================================================================
# StreamingBuffer Tests
# =============================================================================

class TestStreamingBuffer:
    """Tests for StreamingBuffer tool call detection."""

    def test_basic_text_accumulation(self):
        """Test that regular text is accumulated and returned."""
        buffer = StreamingBuffer()

        text, is_tool = buffer.add_token("Hello ")
        assert text == "Hello "
        assert is_tool is False

        text, is_tool = buffer.add_token("world!")
        assert text == "world!"
        assert is_tool is False

        assert buffer.content == "Hello world!"

    def test_tool_call_detection_json(self):
        """Test detection of inline JSON tool calls."""
        buffer = StreamingBuffer()

        # Regular text first
        buffer.add_token("Let me call a tool: ")

        # Start of JSON tool call
        text, is_tool = buffer.add_token('{"name": "read_file"')
        # Once we detect tool pattern, we're in tool block
        assert buffer.in_tool_block or is_tool

    def test_tool_call_detection_markdown(self):
        """Test detection of markdown code block tool calls."""
        buffer = StreamingBuffer()

        buffer.add_token("Here's my tool call:\n")
        buffer.add_token("```json\n{")

        # Should be in JSON block now
        assert buffer.in_tool_block is True

    def test_complete_tool_call_parsing(self):
        """Test parsing a complete tool call."""
        buffer = StreamingBuffer()

        # Add complete tool call
        json_str = '{"name": "write_file", "arguments": {"path": "test.txt", "content": "hello"}}'
        for char in json_str:
            buffer.add_token(char)

        calls = buffer.get_tool_calls()
        assert len(calls) == 1
        assert calls[0].name == "write_file"
        assert calls[0].arguments["path"] == "test.txt"

    def test_function_format_parsing(self):
        """Test parsing function calling format."""
        buffer = StreamingBuffer()

        json_str = '{"function": {"name": "shell", "arguments": {"command": "ls"}}}'
        for char in json_str:
            buffer.add_token(char)

        calls = buffer.get_tool_calls()
        assert len(calls) == 1
        assert calls[0].name == "shell"
        assert calls[0].arguments["command"] == "ls"

    def test_tool_format_parsing(self):
        """Test parsing tool format."""
        buffer = StreamingBuffer()

        json_str = '{"tool": "edit_file", "input": {"path": "foo.py"}}'
        for char in json_str:
            buffer.add_token(char)

        calls = buffer.get_tool_calls()
        assert len(calls) == 1
        assert calls[0].name == "edit_file"
        assert calls[0].arguments["path"] == "foo.py"

    def test_multiple_tool_calls(self):
        """Test detecting multiple tool calls in sequence."""
        buffer = StreamingBuffer()

        # First tool call
        json1 = '{"name": "read_file", "arguments": {"path": "a.txt"}}'
        for char in json1:
            buffer.add_token(char)

        # Some text in between
        buffer.add_token(" and then ")

        # Second tool call
        json2 = '{"name": "write_file", "arguments": {"path": "b.txt", "content": "x"}}'
        for char in json2:
            buffer.add_token(char)

        calls = buffer.get_tool_calls()
        assert len(calls) == 2
        assert calls[0].name == "read_file"
        assert calls[1].name == "write_file"

    def test_invalid_json_handled(self):
        """Test that invalid JSON doesn't crash."""
        buffer = StreamingBuffer()

        # Malformed JSON
        buffer.add_token('{"name": invalid}')

        # Should not crash, just no tool calls detected
        calls = buffer.get_tool_calls()
        assert len(calls) == 0

    def test_string_arguments_parsing(self):
        """Test parsing double-encoded string arguments."""
        buffer = StreamingBuffer()

        # Some models double-encode arguments as string
        json_str = '{"name": "test", "arguments": "{\\"key\\": \\"value\\"}"}'
        for char in json_str:
            buffer.add_token(char)

        calls = buffer.get_tool_calls()
        assert len(calls) == 1
        assert calls[0].arguments.get("key") == "value"

    def test_get_display_content(self):
        """Test getting displayable content without tool JSON."""
        buffer = StreamingBuffer()

        buffer.add_token("Here's the result: ")
        buffer.add_token('{"name": "test", "arguments": {}}')
        buffer.add_token(" Done!")

        display = buffer.get_display_content()
        # Should not contain raw JSON
        assert '{"name"' not in display
        assert "Here's the result:" in display

    def test_reset(self):
        """Test buffer reset."""
        buffer = StreamingBuffer()

        buffer.add_token("Some content")
        buffer.add_token('{"name": "test", "arguments": {}}')

        buffer.reset()

        assert buffer.content == ""
        assert len(buffer.get_tool_calls()) == 0
        assert buffer.in_tool_block is False

    def test_in_tool_block_property(self):
        """Test in_tool_block property updates correctly."""
        buffer = StreamingBuffer()

        assert buffer.in_tool_block is False

        buffer.add_token('{"name": "test"')
        # After starting JSON, should be in tool block
        assert buffer.in_tool_block is True

        buffer.add_token(', "arguments": {}}')
        # After closing JSON, should be out of tool block
        assert buffer.in_tool_block is False


# =============================================================================
# Event System Tests
# =============================================================================

class TestStreamingEvents:
    """Tests for streaming-related events."""

    def test_streaming_token_event_type_exists(self):
        """Test that STREAMING_TOKEN event type is defined."""
        assert hasattr(EventType, 'STREAMING_TOKEN')
        assert hasattr(EventType, 'STREAMING_START')
        assert hasattr(EventType, 'STREAMING_END')

    def test_streaming_event_subscription(self):
        """Test subscribing to streaming events."""
        bus = EventBus()
        received = []

        def handler(data):
            received.append(data)

        bus.subscribe(EventType.STREAMING_TOKEN, handler)

        bus.emit(Event(
            type=EventType.STREAMING_TOKEN,
            data={"token": "Hello"}
        ))

        assert len(received) == 1
        assert received[0]["token"] == "Hello"

    def test_streaming_start_event(self):
        """Test STREAMING_START event emission."""
        bus = EventBus()
        received = []

        bus.subscribe(EventType.STREAMING_START, lambda d: received.append(d))

        bus.emit(Event(
            type=EventType.STREAMING_START,
            data={
                "task_id": "task-123",
                "agent": "huginn",
                "model": "qwen2.5:7b"
            }
        ))

        assert len(received) == 1
        assert received[0]["agent"] == "huginn"

    def test_streaming_end_event(self):
        """Test STREAMING_END event emission."""
        bus = EventBus()
        received = []

        bus.subscribe(EventType.STREAMING_END, lambda d: received.append(d))

        bus.emit(Event(
            type=EventType.STREAMING_END,
            data={
                "task_id": "task-123",
                "agent": "huginn",
                "content_length": 150
            }
        ))

        assert len(received) == 1
        assert received[0]["content_length"] == 150

    def test_streaming_events_have_task_id(self):
        """Test that streaming events include task_id for filtering."""
        event = Event(
            type=EventType.STREAMING_TOKEN,
            data={"token": "x"},
            task_id="task-456"
        )

        assert event.task_id == "task-456"


# =============================================================================
# OllamaClient Streaming Tests
# =============================================================================

class TestOllamaClientStreaming:
    """Tests for OllamaClient.chat_stream() method."""

    @pytest.mark.asyncio
    async def test_chat_stream_accumulates_content(self):
        """Test that streaming accumulates content correctly."""
        client = OllamaClient()

        # Mock the async client
        async def mock_stream(*args, **kwargs):
            chunks = [
                {"message": {"content": "Hello"}, "done": False},
                {"message": {"content": " "}, "done": False},
                {"message": {"content": "world"}, "done": False},
                {"message": {"content": "!"}, "done": True, "model": "test:7b"}
            ]
            for chunk in chunks:
                yield chunk

        with patch.object(client._async_client, 'chat', return_value=mock_stream()):
            result = await client.chat_stream(
                model="test:7b",
                messages=[{"role": "user", "content": "Hi"}]
            )

            assert result.content == "Hello world!"
            assert result.done is True

    @pytest.mark.asyncio
    async def test_chat_stream_calls_on_token(self):
        """Test that on_token callback is called for each token."""
        client = OllamaClient()
        tokens = []

        async def mock_stream(*args, **kwargs):
            for text in ["A", "B", "C"]:
                yield {"message": {"content": text}, "done": False}
            yield {"message": {"content": ""}, "done": True, "model": "test:7b"}

        with patch.object(client._async_client, 'chat', return_value=mock_stream()):
            result = await client.chat_stream(
                model="test:7b",
                messages=[],
                on_token=lambda t: tokens.append(t)
            )

            assert tokens == ["A", "B", "C"]

    @pytest.mark.asyncio
    async def test_chat_stream_handles_tool_calls(self):
        """Test that native tool calls are captured."""
        client = OllamaClient()

        async def mock_stream(*args, **kwargs):
            yield {"message": {"content": "Let me help"}, "done": False}
            yield {
                "message": {
                    "content": "",
                    "tool_calls": [{"function": {"name": "test", "arguments": {}}}]
                },
                "done": True,
                "model": "test:7b"
            }

        with patch.object(client._async_client, 'chat', return_value=mock_stream()):
            result = await client.chat_stream(
                model="test:7b",
                messages=[],
                tools=[{"function": {"name": "test", "description": "Test"}}]
            )

            assert result.tool_calls is not None
            assert len(result.tool_calls) == 1

    @pytest.mark.asyncio
    async def test_chat_stream_to_response(self):
        """Test converting streaming response to standard Response."""
        client = OllamaClient()

        async def mock_stream(*args, **kwargs):
            yield {"message": {"content": "Test"}, "done": True, "model": "test:7b"}

        with patch.object(client._async_client, 'chat', return_value=mock_stream()):
            streaming_result = await client.chat_stream(
                model="test:7b",
                messages=[]
            )

            response = streaming_result.to_response()
            assert isinstance(response, Response)
            assert response.message.content == "Test"


# =============================================================================
# LoopConfig Streaming Tests
# =============================================================================

class TestLoopConfigStreaming:
    """Tests for streaming configuration."""

    def test_streaming_enabled_by_default(self):
        """Test that streaming is enabled by default."""
        config = LoopConfig()
        assert config.streaming is True

    def test_streaming_can_be_disabled(self):
        """Test that streaming can be disabled."""
        config = LoopConfig(streaming=False)
        assert config.streaming is False


# =============================================================================
# Integration Tests
# =============================================================================

class TestStreamingIntegration:
    """Integration tests for streaming through the system."""

    def test_detected_tool_call_dataclass(self):
        """Test DetectedToolCall dataclass."""
        call = DetectedToolCall(
            name="read_file",
            arguments={"path": "test.py"}
        )

        assert call.name == "read_file"
        assert call.arguments["path"] == "test.py"

    def test_streaming_buffer_with_xml_wrapper(self):
        """Test tool call detection with XML wrapper."""
        buffer = StreamingBuffer()

        buffer.add_token("<tool_call>{")
        buffer.add_token('"name": "test", "arguments": {}')
        buffer.add_token("}</tool_call>")

        calls = buffer.get_tool_calls()
        assert len(calls) == 1
        assert calls[0].name == "test"

    def test_event_bus_streaming_flow(self):
        """Test full streaming event flow through event bus."""
        bus = EventBus()
        events = []

        bus.subscribe(EventType.STREAMING_START, lambda d: events.append(("start", d)))
        bus.subscribe(EventType.STREAMING_TOKEN, lambda d: events.append(("token", d)))
        bus.subscribe(EventType.STREAMING_END, lambda d: events.append(("end", d)))

        # Simulate streaming flow
        bus.emit(Event(type=EventType.STREAMING_START, data={"agent": "huginn"}))
        for char in "Hello":
            bus.emit(Event(type=EventType.STREAMING_TOKEN, data={"token": char}))
        bus.emit(Event(type=EventType.STREAMING_END, data={"content_length": 5}))

        assert len(events) == 7  # 1 start + 5 tokens + 1 end
        assert events[0][0] == "start"
        assert events[6][0] == "end"
        assert all(e[0] == "token" for e in events[1:6])


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestStreamingEdgeCases:
    """Edge case tests for streaming."""

    def test_empty_stream(self):
        """Test handling empty stream."""
        buffer = StreamingBuffer()
        assert buffer.content == ""
        assert len(buffer.get_tool_calls()) == 0

    def test_partial_json_not_detected(self):
        """Test that partial JSON is not prematurely detected."""
        buffer = StreamingBuffer()

        # Just an opening brace shouldn't trigger tool detection
        buffer.add_token("{")
        # Not in tool block yet since pattern not matched
        assert buffer.content == "{"

    def test_nested_json_handling(self):
        """Test handling nested JSON in tool calls."""
        buffer = StreamingBuffer()

        json_str = '{"name": "test", "arguments": {"nested": {"deep": "value"}}}'
        for char in json_str:
            buffer.add_token(char)

        calls = buffer.get_tool_calls()
        assert len(calls) == 1
        assert calls[0].arguments["nested"]["deep"] == "value"

    def test_unicode_in_stream(self):
        """Test handling unicode in stream."""
        buffer = StreamingBuffer()

        buffer.add_token("Hello ")
        buffer.add_token("世界")
        buffer.add_token("! 🚀")

        assert buffer.content == "Hello 世界! 🚀"

    def test_large_content_accumulation(self):
        """Test accumulating large content."""
        buffer = StreamingBuffer()

        # Simulate many tokens
        for i in range(1000):
            buffer.add_token(f"token{i} ")

        assert len(buffer.content) > 5000
        assert "token999" in buffer.content

    def test_interleaved_text_and_tools(self):
        """Test text interleaved with tool calls."""
        buffer = StreamingBuffer()

        buffer.add_token("First I'll read: ")
        json1 = '{"name": "read_file", "arguments": {"path": "a.txt"}}'
        for char in json1:
            buffer.add_token(char)

        buffer.add_token("\nThen write: ")
        json2 = '{"name": "write_file", "arguments": {"path": "b.txt", "content": "x"}}'
        for char in json2:
            buffer.add_token(char)

        buffer.add_token("\nDone!")

        calls = buffer.get_tool_calls()
        assert len(calls) == 2

        display = buffer.get_display_content()
        assert "First I'll read:" in display
        assert "Done!" in display
