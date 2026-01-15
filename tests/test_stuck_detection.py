"""Tests for enhanced stuck detection functionality."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from sindri.core.loop import LoopConfig
from sindri.core.hierarchical import HierarchicalAgentLoop
from sindri.core.events import EventBus


class TestEnhancedStuckDetection:
    """Test the enhanced _is_stuck method."""

    @pytest.fixture
    def loop(self):
        """Create a HierarchicalAgentLoop with mocked dependencies."""
        client = MagicMock()
        tools = MagicMock()
        state = MagicMock()
        scheduler = MagicMock()
        delegation = MagicMock()
        config = LoopConfig(
            stuck_threshold=3,
            max_nudges=3,
            similarity_threshold=0.8
        )
        event_bus = EventBus()

        loop = HierarchicalAgentLoop(
            client=client,
            tools=tools,
            state=state,
            scheduler=scheduler,
            delegation=delegation,
            config=config,
            event_bus=event_bus
        )
        return loop

    def test_not_stuck_with_few_responses(self, loop):
        """Should not detect stuck with fewer than threshold responses."""
        responses = ["hello", "world"]
        is_stuck, reason = loop._is_stuck(responses)
        assert is_stuck is False
        assert reason == ""

    def test_exact_repeat_detection(self, loop):
        """Should detect exact repeat responses."""
        responses = ["same response", "same response", "same response"]
        is_stuck, reason = loop._is_stuck(responses)
        assert is_stuck is True
        assert reason == "exact_repeat"

    def test_different_responses_not_stuck(self, loop):
        """Should not detect stuck with different responses."""
        responses = [
            "I'll create the file",
            "Now let me add content",
            "The file is ready"
        ]
        is_stuck, reason = loop._is_stuck(responses)
        assert is_stuck is False

    def test_high_similarity_detection(self, loop):
        """Should detect highly similar responses (80%+ word overlap)."""
        responses = [
            "I will create the file with the content you requested for the project",
            "I will create the file with content you requested for project",
            "I will create the file with the content you requested for this project"
        ]
        is_stuck, reason = loop._is_stuck(responses)
        assert is_stuck is True
        assert reason == "high_similarity"

    def test_moderate_similarity_not_stuck(self, loop):
        """Should not detect stuck with moderate similarity."""
        responses = [
            "I'll create a Python file with hello world",
            "Let me write a test file for this function",
            "Now I'll add documentation to the code"
        ]
        is_stuck, reason = loop._is_stuck(responses)
        assert is_stuck is False

    def test_repeated_tool_calls_detection(self, loop):
        """Should detect repeated tool calls with same args."""
        responses = ["calling tool", "calling tool again", "trying tool once more"]
        tool_history = [
            ("read_file", hash("path/to/file")),
            ("read_file", hash("path/to/file")),
            ("read_file", hash("path/to/file"))
        ]
        is_stuck, reason = loop._is_stuck(responses, tool_history)
        assert is_stuck is True
        assert reason == "repeated_tool_calls"

    def test_different_tool_calls_not_stuck(self, loop):
        """Should not detect stuck with different tool calls."""
        responses = ["reading", "writing", "editing"]
        tool_history = [
            ("read_file", hash("file1")),
            ("write_file", hash("file2")),
            ("edit_file", hash("file3"))
        ]
        is_stuck, reason = loop._is_stuck(responses, tool_history)
        assert is_stuck is False

    def test_clarification_loop_detection(self, loop):
        """Should detect agent stuck in clarification loop."""
        responses = [
            "What would you like me to do with this file?",
            "Could you please clarify what changes you need?",
            "I need more information to proceed. Please provide details."
        ]
        is_stuck, reason = loop._is_stuck(responses)
        assert is_stuck is True
        assert reason == "clarification_loop"

    def test_single_clarification_not_stuck(self, loop):
        """Should not detect stuck with single clarification request."""
        responses = [
            "What would you like me to do?",
            "Okay, I'll create the file now",
            "Done! The file has been created."
        ]
        is_stuck, reason = loop._is_stuck(responses)
        assert is_stuck is False


class TestHighSimilarity:
    """Test the _high_similarity helper method."""

    @pytest.fixture
    def loop(self):
        """Create a loop for testing."""
        client = MagicMock()
        tools = MagicMock()
        state = MagicMock()
        scheduler = MagicMock()
        delegation = MagicMock()
        config = LoopConfig(similarity_threshold=0.8)
        event_bus = EventBus()

        return HierarchicalAgentLoop(
            client=client, tools=tools, state=state, scheduler=scheduler,
            delegation=delegation, config=config, event_bus=event_bus
        )

    def test_high_overlap_detected(self, loop):
        """Should detect high word overlap."""
        responses = [
            "creating file with python code function",
            "creating file with python code function here",
            "creating file with python code function now"
        ]
        assert loop._high_similarity(responses) is True

    def test_low_overlap_not_detected(self, loop):
        """Should not flag low overlap as similar."""
        responses = [
            "first I will read the file",
            "now let me write the output",
            "finally testing the result"
        ]
        assert loop._high_similarity(responses) is False

    def test_single_response_not_similar(self, loop):
        """Should not flag single response."""
        responses = ["only one response"]
        assert loop._high_similarity(responses) is False

    def test_empty_responses_not_similar(self, loop):
        """Should handle empty responses gracefully."""
        responses = ["", "", ""]
        assert loop._high_similarity(responses) is False


class TestRepeatedToolCalls:
    """Test the _repeated_tool_calls helper method."""

    @pytest.fixture
    def loop(self):
        """Create a loop for testing."""
        client = MagicMock()
        tools = MagicMock()
        state = MagicMock()
        scheduler = MagicMock()
        delegation = MagicMock()
        config = LoopConfig()
        event_bus = EventBus()

        return HierarchicalAgentLoop(
            client=client, tools=tools, state=state, scheduler=scheduler,
            delegation=delegation, config=config, event_bus=event_bus
        )

    def test_same_tool_same_args_detected(self, loop):
        """Should detect same tool called with same args."""
        tool_history = [
            ("read_file", 12345),
            ("read_file", 12345),
            ("read_file", 12345)
        ]
        assert loop._repeated_tool_calls(tool_history) is True

    def test_same_tool_different_args_not_detected(self, loop):
        """Should not flag same tool with different args."""
        tool_history = [
            ("read_file", 12345),
            ("read_file", 67890),
            ("read_file", 11111)
        ]
        assert loop._repeated_tool_calls(tool_history) is False

    def test_different_tools_not_detected(self, loop):
        """Should not flag different tools."""
        tool_history = [
            ("read_file", 12345),
            ("write_file", 12345),
            ("edit_file", 12345)
        ]
        assert loop._repeated_tool_calls(tool_history) is False

    def test_short_history_not_detected(self, loop):
        """Should not flag with fewer than 3 tool calls."""
        tool_history = [
            ("read_file", 12345),
            ("read_file", 12345)
        ]
        assert loop._repeated_tool_calls(tool_history) is False


class TestLoopConfigEnhancements:
    """Test LoopConfig Phase 5.6 enhancements."""

    def test_default_max_nudges(self):
        """Should have default max_nudges."""
        config = LoopConfig()
        assert config.max_nudges == 3

    def test_default_similarity_threshold(self):
        """Should have default similarity threshold."""
        config = LoopConfig()
        assert config.similarity_threshold == 0.8

    def test_custom_max_nudges(self):
        """Should accept custom max_nudges."""
        config = LoopConfig(max_nudges=5)
        assert config.max_nudges == 5

    def test_custom_similarity_threshold(self):
        """Should accept custom similarity threshold."""
        config = LoopConfig(similarity_threshold=0.9)
        assert config.similarity_threshold == 0.9
