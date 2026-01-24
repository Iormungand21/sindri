"""Tests for Performance Telemetry Stream (ROADMAP Item 7)."""

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import Mock, MagicMock, AsyncMock

import pytest

from sindri.core.events import EventBus, Event, EventType
from sindri.core.event_schemas import (
    TelemetryTickData,
    TelemetrySnapshotData,
    VRAMSnapshot,
    ConcurrencySnapshot,
    AgentTimingStats,
    ToolTimingStats,
)
from sindri.telemetry.collector import TelemetryCollector, RollingStats
from sindri.telemetry.exporter import TraceExporter


class TestRollingStats:
    """Tests for RollingStats class."""

    def test_add_sample(self):
        """Test adding samples to rolling stats."""
        stats = RollingStats()
        stats.add_sample(100.0)
        stats.add_sample(200.0)
        assert stats.total_count == 2
        assert stats.total_duration_ms == 300.0

    def test_avg_ms(self):
        """Test average calculation."""
        stats = RollingStats()
        stats.add_sample(100.0)
        stats.add_sample(200.0)
        stats.add_sample(300.0)
        assert stats.avg_ms == 200.0

    def test_avg_ms_empty(self):
        """Test average with no samples."""
        stats = RollingStats()
        assert stats.avg_ms == 0.0

    def test_success_rate(self):
        """Test success rate calculation."""
        stats = RollingStats()
        stats.add_sample(100.0, success=True)
        stats.add_sample(100.0, success=False)
        assert stats.success_rate == 0.5

    def test_success_rate_all_success(self):
        """Test success rate with all successes."""
        stats = RollingStats()
        stats.add_sample(100.0, success=True)
        stats.add_sample(100.0, success=True)
        assert stats.success_rate == 1.0

    def test_success_rate_empty(self):
        """Test success rate with no samples."""
        stats = RollingStats()
        assert stats.success_rate == 1.0

    def test_p95_calculation(self):
        """Test 95th percentile calculation."""
        stats = RollingStats()
        for i in range(100):
            stats.add_sample(float(i))
        # 95th percentile should be around 94-95
        assert stats.p95_ms >= 90.0
        assert stats.p95_ms <= 99.0

    def test_p95_insufficient_samples(self):
        """Test p95 with insufficient samples."""
        stats = RollingStats()
        stats.add_sample(100.0)
        stats.add_sample(200.0)
        assert stats.p95_ms is None

    def test_rolling_window(self):
        """Test that samples are limited to window size."""
        stats = RollingStats()
        # Add more than maxlen samples
        for i in range(150):
            stats.add_sample(float(i))
        # Window should only keep last 100
        assert len(stats.samples) == 100
        # Total count should still be 150
        assert stats.total_count == 150


class TestTelemetrySchemas:
    """Tests for telemetry Pydantic schemas."""

    def test_vram_snapshot_serialization(self):
        """Test VRAMSnapshot serialization."""
        vram = VRAMSnapshot(
            total_gb=16.0,
            used_gb=8.0,
            free_gb=8.0,
            loaded_models=["qwen2.5-coder:14b"],
            cache_hit_rate=0.85,
        )
        data = vram.model_dump()
        assert data["total_gb"] == 16.0
        assert data["used_gb"] == 8.0
        assert data["loaded_models"] == ["qwen2.5-coder:14b"]
        assert data["cache_hit_rate"] == 0.85

    def test_vram_snapshot_defaults(self):
        """Test VRAMSnapshot default values."""
        vram = VRAMSnapshot(total_gb=16.0, used_gb=0.0, free_gb=16.0)
        assert vram.loaded_models == []
        assert vram.cache_hit_rate == 0.0

    def test_concurrency_snapshot_serialization(self):
        """Test ConcurrencySnapshot serialization."""
        conc = ConcurrencySnapshot(
            running_tasks=2,
            pending_tasks=3,
            waiting_tasks=1,
            batch_size=2,
        )
        data = conc.model_dump()
        assert data["running_tasks"] == 2
        assert data["pending_tasks"] == 3
        assert data["waiting_tasks"] == 1
        assert data["batch_size"] == 2

    def test_agent_timing_stats(self):
        """Test AgentTimingStats serialization."""
        stats = AgentTimingStats(
            agent_name="huginn",
            model_name="qwen2.5-coder:14b",
            total_iterations=10,
            total_duration_ms=5000.0,
            avg_iteration_ms=500.0,
            p95_iteration_ms=750.0,
        )
        data = stats.model_dump()
        assert data["agent_name"] == "huginn"
        assert data["model_name"] == "qwen2.5-coder:14b"
        assert data["total_iterations"] == 10
        assert data["avg_iteration_ms"] == 500.0

    def test_tool_timing_stats(self):
        """Test ToolTimingStats serialization."""
        stats = ToolTimingStats(
            tool_name="read_file",
            call_count=50,
            total_duration_ms=1000.0,
            avg_duration_ms=20.0,
            success_rate=0.98,
            p95_duration_ms=35.0,
        )
        data = stats.model_dump()
        assert data["tool_name"] == "read_file"
        assert data["call_count"] == 50
        assert data["success_rate"] == 0.98

    def test_telemetry_tick_validation(self):
        """Test TelemetryTickData validation."""
        tick = TelemetryTickData(
            timestamp=time.time(),
            session_id="test-123",
            vram=VRAMSnapshot(total_gb=16.0, used_gb=5.0, free_gb=11.0),
            concurrency=ConcurrencySnapshot(
                running_tasks=2, pending_tasks=3, waiting_tasks=0
            ),
            session_duration_seconds=120.5,
            current_agent="huginn",
            current_iteration=5,
        )
        assert tick.current_agent == "huginn"
        assert tick.current_iteration == 5
        assert tick.session_duration_seconds == 120.5

    def test_telemetry_snapshot_validation(self):
        """Test TelemetrySnapshotData validation."""
        snapshot = TelemetrySnapshotData(
            timestamp=time.time(),
            session_id="test-123",
            session_duration_seconds=300.0,
            vram=VRAMSnapshot(total_gb=16.0, used_gb=8.0, free_gb=8.0),
            concurrency=ConcurrencySnapshot(
                running_tasks=0, pending_tasks=0, waiting_tasks=0
            ),
            agent_stats=[
                AgentTimingStats(agent_name="huginn", total_iterations=10)
            ],
            tool_stats=[ToolTimingStats(tool_name="read_file", call_count=20)],
            total_iterations=10,
            total_tool_calls=20,
            llm_time_seconds=200.0,
            tool_time_seconds=50.0,
        )
        assert snapshot.session_id == "test-123"
        assert len(snapshot.agent_stats) == 1
        assert len(snapshot.tool_stats) == 1
        assert snapshot.llm_time_seconds == 200.0


class TestTelemetryCollector:
    """Tests for TelemetryCollector class."""

    @pytest.fixture
    def event_bus(self):
        """Create an EventBus for testing."""
        return EventBus()

    @pytest.fixture
    def collector(self, event_bus):
        """Create a TelemetryCollector for testing."""
        return TelemetryCollector(event_bus=event_bus, tick_interval=0.1)

    @pytest.mark.asyncio
    async def test_start_stop(self, collector):
        """Test start and stop lifecycle."""
        await collector.start("test-session")
        assert collector.is_running
        assert collector.session_id == "test-session"

        snapshot = await collector.stop()
        assert not collector.is_running
        assert isinstance(snapshot, TelemetrySnapshotData)

    @pytest.mark.asyncio
    async def test_iteration_tracking(self, collector, event_bus):
        """Test tracking of iteration events."""
        await collector.start("test-session")

        # Simulate iteration
        event_bus.emit(
            Event(
                type=EventType.ITERATION_START,
                data={"agent": "huginn", "iteration": 1},
            )
        )
        event_bus.emit(
            Event(
                type=EventType.ITERATION_END,
                data={"agent": "huginn", "duration_ms": 1500.0},
            )
        )

        snapshot = await collector.stop()
        assert any(s.agent_name == "huginn" for s in snapshot.agent_stats)
        huginn_stats = next(s for s in snapshot.agent_stats if s.agent_name == "huginn")
        assert huginn_stats.total_iterations == 1
        assert huginn_stats.total_duration_ms == 1500.0

    @pytest.mark.asyncio
    async def test_tool_tracking(self, collector, event_bus):
        """Test tracking of tool call events."""
        await collector.start("test-session")

        # Simulate tool call
        event_bus.emit(
            Event(
                type=EventType.TOOL_CALLED,
                data={"name": "read_file", "success": True, "duration_ms": 50.0},
            )
        )

        snapshot = await collector.stop()
        assert any(s.tool_name == "read_file" for s in snapshot.tool_stats)
        read_stats = next(s for s in snapshot.tool_stats if s.tool_name == "read_file")
        assert read_stats.call_count == 1
        assert read_stats.success_rate == 1.0

    @pytest.mark.asyncio
    async def test_tick_emission(self, collector, event_bus):
        """Test periodic tick emission."""
        ticks = []

        def on_tick(data):
            if isinstance(data, dict) and "timestamp" in data:
                ticks.append(data)

        event_bus.subscribe(EventType.TELEMETRY_TICK, on_tick)

        await collector.start("test-session")
        await asyncio.sleep(0.25)  # Wait for 2+ ticks
        await collector.stop()

        assert len(ticks) >= 2

    @pytest.mark.asyncio
    async def test_get_tick(self, collector):
        """Test get_tick method."""
        await collector.start("test-session")

        tick = collector.get_tick()
        assert isinstance(tick, TelemetryTickData)
        assert tick.session_id == "test-session"
        assert tick.session_duration_seconds >= 0

        await collector.stop()

    @pytest.mark.asyncio
    async def test_get_snapshot(self, collector):
        """Test get_snapshot method."""
        await collector.start("test-session")

        snapshot = collector.get_snapshot()
        assert isinstance(snapshot, TelemetrySnapshotData)
        assert snapshot.session_id == "test-session"

        await collector.stop()

    @pytest.mark.asyncio
    async def test_callback_registration(self, collector):
        """Test tick callback registration."""
        ticks = []

        def callback(tick):
            ticks.append(tick)

        collector.add_tick_callback(callback)
        await collector.start("test-session")
        await asyncio.sleep(0.25)
        await collector.stop()

        assert len(ticks) >= 2

        # Test removal
        collector.remove_tick_callback(callback)
        assert callback not in collector._tick_callbacks

    @pytest.mark.asyncio
    async def test_vram_history(self, collector):
        """Test VRAM history collection."""
        await collector.start("test-session")
        await asyncio.sleep(0.25)
        await collector.stop()

        history = collector.get_vram_history()
        assert len(history) >= 2
        for ts, vram in history:
            assert isinstance(vram, VRAMSnapshot)

    @pytest.mark.asyncio
    async def test_concurrency_history(self, collector):
        """Test concurrency history collection."""
        await collector.start("test-session")
        await asyncio.sleep(0.25)
        await collector.stop()

        history = collector.get_concurrency_history()
        assert len(history) >= 2
        for ts, conc in history:
            assert isinstance(conc, ConcurrencySnapshot)

    @pytest.mark.asyncio
    async def test_multiple_agents(self, collector, event_bus):
        """Test tracking multiple agents."""
        await collector.start("test-session")

        # Simulate iterations from multiple agents
        for agent in ["huginn", "muninn", "brokkr"]:
            event_bus.emit(
                Event(
                    type=EventType.ITERATION_END,
                    data={"agent": agent, "duration_ms": 1000.0},
                )
            )

        snapshot = await collector.stop()
        assert len(snapshot.agent_stats) == 3
        agent_names = {s.agent_name for s in snapshot.agent_stats}
        assert agent_names == {"huginn", "muninn", "brokkr"}

    @pytest.mark.asyncio
    async def test_tool_failure_tracking(self, collector, event_bus):
        """Test tracking of failed tool calls."""
        await collector.start("test-session")

        # Simulate mix of successes and failures
        event_bus.emit(
            Event(
                type=EventType.TOOL_CALLED,
                data={"name": "write_file", "success": True, "duration_ms": 50.0},
            )
        )
        event_bus.emit(
            Event(
                type=EventType.TOOL_CALLED,
                data={"name": "write_file", "success": False, "duration_ms": 10.0},
            )
        )

        snapshot = await collector.stop()
        write_stats = next(s for s in snapshot.tool_stats if s.tool_name == "write_file")
        assert write_stats.call_count == 2
        assert write_stats.success_rate == 0.5


class TestTraceExporter:
    """Tests for TraceExporter class."""

    @pytest.mark.asyncio
    async def test_export_session_trace(self, tmp_path):
        """Test exporting a session trace."""
        exporter = TraceExporter()
        output = tmp_path / "trace.json"

        # Will have empty data for non-existent session
        trace = await exporter.export_session_trace(
            "nonexistent-session",
            output_path=output,
        )

        assert trace["format"] == "sindri-trace"
        assert trace["version"] == "1.0.0"
        assert trace["session_id"] == "nonexistent-session"
        assert output.exists()

        # Verify JSON is valid
        with open(output) as f:
            loaded = json.load(f)
        assert loaded["session_id"] == "nonexistent-session"

    @pytest.mark.asyncio
    async def test_compare_traces(self, tmp_path):
        """Test comparing two traces."""
        baseline = tmp_path / "baseline.json"
        current = tmp_path / "current.json"

        # Create mock traces
        baseline.write_text(
            json.dumps(
                {
                    "session_id": "baseline-123",
                    "metrics": {
                        "start_time": 0,
                        "end_time": 100,
                        "tasks": [{"iterations": [{"tool_executions": [{}, {}]}]}],
                    },
                }
            )
        )
        current.write_text(
            json.dumps(
                {
                    "session_id": "current-456",
                    "metrics": {
                        "start_time": 0,
                        "end_time": 120,
                        "tasks": [{"iterations": [{"tool_executions": [{}, {}, {}]}]}],
                    },
                }
            )
        )

        exporter = TraceExporter()
        result = await exporter.compare_traces(baseline, current)

        assert result["baseline_session"] == "baseline-123"
        assert result["current_session"] == "current-456"
        assert result["duration_delta"]["baseline"] == 100
        assert result["duration_delta"]["current"] == 120
        assert result["duration_delta"]["change_percent"] == 20.0

    @pytest.mark.asyncio
    async def test_compare_traces_regression_detection(self, tmp_path):
        """Test regression detection in trace comparison."""
        baseline = tmp_path / "baseline.json"
        current = tmp_path / "current.json"

        # Create traces with significant slowdown
        baseline.write_text(
            json.dumps(
                {
                    "session_id": "baseline-123",
                    "metrics": {"start_time": 0, "end_time": 100, "tasks": []},
                }
            )
        )
        current.write_text(
            json.dumps(
                {
                    "session_id": "current-456",
                    "metrics": {"start_time": 0, "end_time": 150, "tasks": []},
                }
            )
        )

        exporter = TraceExporter()
        result = await exporter.compare_traces(baseline, current)

        assert len(result["regressions"]) > 0
        assert result["regressions"][0]["type"] == "duration"
        assert "slower" in result["regressions"][0]["message"]

    @pytest.mark.asyncio
    async def test_compare_traces_improvement_detection(self, tmp_path):
        """Test improvement detection in trace comparison."""
        baseline = tmp_path / "baseline.json"
        current = tmp_path / "current.json"

        # Create traces with significant speedup
        baseline.write_text(
            json.dumps(
                {
                    "session_id": "baseline-123",
                    "metrics": {"start_time": 0, "end_time": 100, "tasks": []},
                }
            )
        )
        current.write_text(
            json.dumps(
                {
                    "session_id": "current-456",
                    "metrics": {"start_time": 0, "end_time": 80, "tasks": []},
                }
            )
        )

        exporter = TraceExporter()
        result = await exporter.compare_traces(baseline, current)

        assert len(result["improvements"]) > 0
        assert result["improvements"][0]["type"] == "duration"
        assert "faster" in result["improvements"][0]["message"]

    def test_load_trace(self, tmp_path):
        """Test loading a trace from file."""
        trace_file = tmp_path / "trace.json"
        trace_data = {"session_id": "test-123", "format": "sindri-trace"}
        trace_file.write_text(json.dumps(trace_data))

        loaded = TraceExporter.load_trace(trace_file)
        assert loaded["session_id"] == "test-123"

    def test_get_trace_summary(self):
        """Test getting a trace summary."""
        trace = {
            "session_id": "test-123",
            "exported_at": "2024-01-01T00:00:00",
            "metrics": {
                "start_time": 0,
                "end_time": 100,
                "tasks": [
                    {
                        "iterations": [
                            {"tool_executions": [{}, {}]},
                            {"tool_executions": [{}]},
                        ]
                    }
                ],
            },
            "environment": {"model_metadata": {"name": "qwen2.5-coder:14b"}},
            "audit_log": [{}, {}, {}],
        }

        summary = TraceExporter.get_trace_summary(trace)
        assert summary["session_id"] == "test-123"
        assert summary["duration_seconds"] == 100
        assert summary["total_iterations"] == 2
        assert summary["total_tool_calls"] == 3
        assert summary["audit_entries"] == 3
        assert summary["model_name"] == "qwen2.5-coder:14b"
        assert summary["has_metrics"] is True
        assert summary["has_environment"] is True


class TestEventTypeRegistration:
    """Tests for telemetry event type registration."""

    def test_telemetry_tick_event_type_exists(self):
        """Test TELEMETRY_TICK event type exists."""
        assert hasattr(EventType, "TELEMETRY_TICK")

    def test_telemetry_snapshot_event_type_exists(self):
        """Test TELEMETRY_SNAPSHOT event type exists."""
        assert hasattr(EventType, "TELEMETRY_SNAPSHOT")

    def test_event_payload_models_registered(self):
        """Test that telemetry payload models are registered."""
        from sindri.core.event_schemas import EVENT_PAYLOAD_MODELS

        assert "TELEMETRY_TICK" in EVENT_PAYLOAD_MODELS
        assert "TELEMETRY_SNAPSHOT" in EVENT_PAYLOAD_MODELS
        assert EVENT_PAYLOAD_MODELS["TELEMETRY_TICK"] == TelemetryTickData
        assert EVENT_PAYLOAD_MODELS["TELEMETRY_SNAPSHOT"] == TelemetrySnapshotData


class TestModelLoadedEvent:
    """Tests for MODEL_LOADED event handling by TelemetryCollector."""

    @pytest.fixture
    def event_bus(self):
        """Create an EventBus for testing."""
        return EventBus()

    @pytest.fixture
    def collector(self, event_bus):
        """Create a TelemetryCollector for testing."""
        return TelemetryCollector(event_bus=event_bus, tick_interval=0.1)

    @pytest.mark.asyncio
    async def test_model_loaded_populates_agent_models(self, collector, event_bus):
        """MODEL_LOADED event should populate agent→model tracking."""
        await collector.start("test-session")

        # Emit MODEL_LOADED event
        event_bus.emit(
            Event(
                type=EventType.MODEL_LOADED,
                data={
                    "model": "qwen2.5-coder:14b",
                    "task_id": "task-123",
                    "agent": "huginn",
                    "vram_gb": 9.0,
                },
            )
        )

        # Verify agent→model is tracked
        assert collector._agent_models.get("huginn") == "qwen2.5-coder:14b"

        await collector.stop()

    @pytest.mark.asyncio
    async def test_model_loaded_reflects_in_snapshot(self, collector, event_bus):
        """MODEL_LOADED event should be reflected in snapshot agent stats."""
        await collector.start("test-session")

        # Emit MODEL_LOADED event
        event_bus.emit(
            Event(
                type=EventType.MODEL_LOADED,
                data={
                    "model": "qwen2.5-coder:7b",
                    "task_id": "task-456",
                    "agent": "brokkr",
                    "vram_gb": 5.0,
                },
            )
        )

        # Also emit an iteration to have stats for this agent
        event_bus.emit(
            Event(
                type=EventType.ITERATION_END,
                data={"agent": "brokkr", "duration_ms": 1000.0},
            )
        )

        snapshot = await collector.stop()

        # Verify model_name is in agent stats
        brokkr_stats = next(
            (s for s in snapshot.agent_stats if s.agent_name == "brokkr"), None
        )
        assert brokkr_stats is not None
        assert brokkr_stats.model_name == "qwen2.5-coder:7b"

    @pytest.mark.asyncio
    async def test_model_loaded_without_agent(self, collector, event_bus):
        """MODEL_LOADED event without agent should not crash."""
        await collector.start("test-session")

        # Emit MODEL_LOADED event without agent field
        event_bus.emit(
            Event(
                type=EventType.MODEL_LOADED,
                data={
                    "model": "qwen2.5-coder:14b",
                    "task_id": "task-789",
                    # No "agent" field
                },
            )
        )

        # Should not crash and agent_models should be empty
        assert len(collector._agent_models) == 0

        await collector.stop()

    @pytest.mark.asyncio
    async def test_model_loaded_updates_existing_agent(self, collector, event_bus):
        """MODEL_LOADED for same agent should update the tracked model."""
        await collector.start("test-session")

        # First model load
        event_bus.emit(
            Event(
                type=EventType.MODEL_LOADED,
                data={
                    "model": "qwen2.5-coder:14b",
                    "agent": "huginn",
                    "vram_gb": 9.0,
                },
            )
        )
        assert collector._agent_models.get("huginn") == "qwen2.5-coder:14b"

        # Second model load (e.g., fallback)
        event_bus.emit(
            Event(
                type=EventType.MODEL_LOADED,
                data={
                    "model": "qwen2.5-coder:7b",
                    "agent": "huginn",
                    "vram_gb": 5.0,
                },
            )
        )
        # Should be updated to new model
        assert collector._agent_models.get("huginn") == "qwen2.5-coder:7b"

        await collector.stop()


class TestEventBusUnsubscribe:
    """Tests for EventBus unsubscribe functionality."""

    def test_unsubscribe_handler(self):
        """Test unsubscribing a handler."""
        bus = EventBus()
        calls = []

        def handler(data):
            calls.append(data)

        bus.subscribe(EventType.TOOL_CALLED, handler)
        bus.emit(Event(type=EventType.TOOL_CALLED, data={"test": 1}))
        assert len(calls) == 1

        bus.unsubscribe(EventType.TOOL_CALLED, handler)
        bus.emit(Event(type=EventType.TOOL_CALLED, data={"test": 2}))
        assert len(calls) == 1  # Should not have received second event

    def test_unsubscribe_nonexistent_handler(self):
        """Test unsubscribing a handler that was never subscribed."""
        bus = EventBus()

        def handler(data):
            pass

        # Should not raise an error
        bus.unsubscribe(EventType.TOOL_CALLED, handler)

    def test_unsubscribe_event_handler(self):
        """Test unsubscribing a full event handler."""
        bus = EventBus()
        calls = []

        def handler(event):
            calls.append(event)

        bus.subscribe_event(handler)
        bus.emit(Event(type=EventType.TOOL_CALLED, data={"test": 1}))
        assert len(calls) == 1

        bus.unsubscribe_event(handler)
        bus.emit(Event(type=EventType.TOOL_CALLED, data={"test": 2}))
        assert len(calls) == 1  # Should not have received second event
