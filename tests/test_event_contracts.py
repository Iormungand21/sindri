"""Contract tests for event schemas and API versioning.

These tests ensure:
1. All EventType enum values have corresponding payload schemas
2. Event payloads validate correctly against their schemas
3. API schema endpoints return valid JSON Schema
4. API version headers are present
"""

import pytest
from pydantic import ValidationError

from sindri.core.events import EventType
from sindri.core.event_schemas import (
    API_VERSION,
    EVENT_PAYLOAD_MODELS,
    get_event_schema,
    get_all_event_schemas,
    validate_event_data,
    TaskCreatedData,
    TaskStatusChangedData,
    AgentOutputData,
    ToolCalledData,
    DelegationStartData,
    DelegationCompleteData,
    DelegationFailedData,
    ModelLoadedData,
    ModelUnloadedData,
    ModelDegradedData,
    ErrorData,
    IterationStartData,
    IterationEndData,
    IterationWarningData,
    ParallelBatchStartData,
    ParallelBatchEndData,
    StreamingStartData,
    StreamingTokenData,
    StreamingEndData,
    PlanProposedData,
    PlanApprovedData,
    PlanRejectedData,
    PatternLearnedData,
    MetricsUpdatedData,
)


class TestEventSchemaCompleteness:
    """Test that all event types have corresponding schemas."""

    def test_all_event_types_have_schema(self):
        """Every EventType enum should have a corresponding payload model."""
        for event_type in EventType:
            assert event_type.name in EVENT_PAYLOAD_MODELS, (
                f"Missing schema for EventType.{event_type.name}"
            )

    def test_schema_count_matches_event_types(self):
        """Number of schemas should match number of event types."""
        assert len(EVENT_PAYLOAD_MODELS) == len(EventType)

    def test_get_all_event_schemas_returns_all(self):
        """get_all_event_schemas should return schema for every event type."""
        schemas = get_all_event_schemas()
        assert len(schemas) == len(EventType)
        for event_type in EventType:
            assert event_type.name in schemas


class TestEventSchemaValidation:
    """Test that event data validates correctly against schemas."""

    @pytest.mark.parametrize(
        "event_type,valid_data",
        [
            ("TASK_CREATED", {"task_id": "t1", "task": "Do something"}),
            ("TASK_STATUS_CHANGED", {"task_id": "t1", "status": "running"}),
            ("AGENT_OUTPUT", {"task_id": "t1", "agent": "huginn", "text": "Hello"}),
            ("TOOL_CALLED", {"task_id": "t1", "name": "read_file", "success": True, "duration_ms": 42.5}),
            (
                "DELEGATION_START",
                {
                    "task_id": "t2",
                    "parent_task_id": "t1",
                    "parent_agent": "brokkr",
                    "child_agent": "huginn",
                    "task": "Write code",
                },
            ),
            (
                "DELEGATION_COMPLETE",
                {
                    "task_id": "t2",
                    "parent_task_id": "t1",
                    "parent_agent": "brokkr",
                    "child_agent": "huginn",
                    "status": "complete",
                },
            ),
            (
                "DELEGATION_FAILED",
                {
                    "task_id": "t2",
                    "parent_task_id": "t1",
                    "parent_agent": "brokkr",
                    "child_agent": "huginn",
                },
            ),
            ("MODEL_LOADED", {"model": "qwen2.5:7b"}),
            ("MODEL_UNLOADED", {"model": "qwen2.5:7b"}),
            (
                "MODEL_DEGRADED",
                {
                    "task_id": "t1",
                    "agent": "huginn",
                    "primary_model": "qwen2.5:14b",
                    "fallback_model": "qwen2.5:7b",
                },
            ),
            ("ERROR", {"error": "Something went wrong"}),
            ("ITERATION_START", {"task_id": "t1", "iteration": 1, "agent": "huginn"}),
            ("ITERATION_END", {"task_id": "t1", "iteration": 1}),
            ("ITERATION_WARNING", {"task_id": "t1", "remaining": 5, "message": "Low iterations"}),
            ("PARALLEL_BATCH_START", {"batch_id": "b1", "task_ids": ["t1", "t2"], "count": 2}),
            ("PARALLEL_BATCH_END", {"batch_id": "b1", "completed": 2, "failed": 0}),
            ("STREAMING_START", {"task_id": "t1", "agent": "huginn", "model": "qwen2.5:7b"}),
            ("STREAMING_TOKEN", {"task_id": "t1", "agent": "huginn", "token": "Hello"}),
            ("STREAMING_END", {"task_id": "t1", "agent": "huginn", "content_length": 100}),
            (
                "PLAN_PROPOSED",
                {
                    "task_id": "t1",
                    "agent": "brokkr",
                    "plan": {"steps": []},
                    "formatted": "Plan text",
                    "step_count": 3,
                },
            ),
            ("PLAN_APPROVED", {"task_id": "t1"}),
            ("PLAN_REJECTED", {"task_id": "t1"}),
            (
                "PATTERN_LEARNED",
                {
                    "task_id": "t1",
                    "pattern_id": "p1",
                    "agent": "huginn",
                    "iterations": 5,
                    "tools": ["read_file", "write_file"],
                },
            ),
            (
                "METRICS_UPDATED",
                {
                    "task_id": "t1",
                    "session_id": "s1",
                    "iteration": 1,
                    "duration_seconds": 5.0,
                },
            ),
        ],
    )
    def test_valid_event_data_validates(self, event_type, valid_data):
        """Valid event data should pass schema validation."""
        model_class = EVENT_PAYLOAD_MODELS[event_type]
        instance = model_class(**valid_data)
        assert instance is not None

    @pytest.mark.parametrize(
        "event_type,invalid_data,missing_field",
        [
            ("TASK_CREATED", {}, "task_id"),
            ("TASK_STATUS_CHANGED", {"task_id": "t1"}, "status"),
            ("AGENT_OUTPUT", {"task_id": "t1", "agent": "huginn"}, "text"),
            ("TOOL_CALLED", {"task_id": "t1", "name": "read_file"}, "success"),
            ("DELEGATION_START", {"task_id": "t1"}, "parent_task_id"),
            ("ITERATION_START", {"task_id": "t1"}, "iteration"),
            ("STREAMING_TOKEN", {"task_id": "t1"}, "token"),
            ("PATTERN_LEARNED", {"task_id": "t1"}, "pattern_id"),
        ],
    )
    def test_invalid_event_data_fails(self, event_type, invalid_data, missing_field):
        """Invalid event data should fail validation."""
        model_class = EVENT_PAYLOAD_MODELS[event_type]
        with pytest.raises(ValidationError) as exc_info:
            model_class(**invalid_data)
        # Verify the error is about the missing field
        errors = exc_info.value.errors()
        field_names = [e["loc"][0] for e in errors]
        assert missing_field in field_names


class TestValidateEventDataFunction:
    """Test the validate_event_data helper function."""

    def test_validate_valid_data(self):
        """validate_event_data should return model instance for valid data."""
        result = validate_event_data("TASK_CREATED", {"task_id": "t1"})
        assert isinstance(result, TaskCreatedData)
        assert result.task_id == "t1"

    def test_validate_invalid_type(self):
        """validate_event_data should raise KeyError for unknown event type."""
        with pytest.raises(KeyError):
            validate_event_data("UNKNOWN_EVENT", {})

    def test_validate_invalid_data(self):
        """validate_event_data should raise ValidationError for invalid data."""
        with pytest.raises(ValidationError):
            validate_event_data("TASK_STATUS_CHANGED", {"task_id": "t1"})  # Missing status


class TestGetEventSchema:
    """Test JSON Schema generation functions."""

    def test_get_event_schema_returns_valid_json_schema(self):
        """get_event_schema should return valid JSON Schema."""
        schema = get_event_schema("TASK_CREATED")

        assert "type" in schema
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "task_id" in schema["properties"]

    def test_get_event_schema_unknown_type(self):
        """get_event_schema should raise KeyError for unknown type."""
        with pytest.raises(KeyError):
            get_event_schema("UNKNOWN_EVENT")

    def test_all_schemas_have_required_fields(self):
        """All schemas should have type and properties fields."""
        schemas = get_all_event_schemas()
        for event_type, schema in schemas.items():
            assert "type" in schema, f"{event_type} schema missing 'type'"
            assert schema["type"] == "object", f"{event_type} schema type should be 'object'"
            assert "properties" in schema, f"{event_type} schema missing 'properties'"


class TestAPIVersioning:
    """Test API version constants and compatibility."""

    def test_api_version_format(self):
        """API version should follow semantic versioning format."""
        parts = API_VERSION.split(".")
        assert len(parts) == 3, "API version should have major.minor.patch format"
        for part in parts:
            assert part.isdigit(), "Version parts should be numeric"

    def test_api_version_is_1_0_0(self):
        """Initial API version should be 1.0.0."""
        assert API_VERSION == "1.0.0"


class TestSchemaAPIEndpoints:
    """Test the /api/schema endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from fastapi.testclient import TestClient
        from sindri.web.server import create_app

        app = create_app(vram_gb=16.0)
        return TestClient(app)

    def test_api_version_endpoint(self, client):
        """GET /api/version should return version info."""
        response = client.get("/api/version")
        assert response.status_code == 200

        data = response.json()
        assert "version" in data
        assert data["version"] == API_VERSION
        assert "compatible_versions" in data
        assert API_VERSION in data["compatible_versions"]

    def test_api_schema_endpoint(self, client):
        """GET /api/schema should return all event schemas."""
        response = client.get("/api/schema")
        assert response.status_code == 200

        data = response.json()
        assert "version" in data
        assert data["version"] == API_VERSION
        assert "event_types" in data
        assert "event_type_list" in data

        # Should have all 24 event types
        assert len(data["event_types"]) == len(EventType)
        assert len(data["event_type_list"]) == len(EventType)

    def test_api_schema_event_endpoint(self, client):
        """GET /api/schema/events/{event_type} should return specific schema."""
        response = client.get("/api/schema/events/TASK_CREATED")
        assert response.status_code == 200

        data = response.json()
        assert "event_type" in data
        assert data["event_type"] == "TASK_CREATED"
        assert "schema" in data
        assert "properties" in data["schema"]

    def test_api_schema_event_unknown(self, client):
        """GET /api/schema/events/{unknown} should return 404."""
        response = client.get("/api/schema/events/UNKNOWN_EVENT")
        assert response.status_code == 404

    def test_api_version_header(self, client):
        """All responses should include X-Sindri-API-Version header."""
        response = client.get("/api/version")
        assert "X-Sindri-API-Version" in response.headers
        assert response.headers["X-Sindri-API-Version"] == API_VERSION

        # Test on other endpoints too
        response = client.get("/health")
        assert "X-Sindri-API-Version" in response.headers

        response = client.get("/api/agents")
        assert "X-Sindri-API-Version" in response.headers


class TestWebSocketEventContract:
    """Test WebSocket event message format."""

    def test_websocket_message_structure(self):
        """WebSocket messages should have expected structure."""
        from sindri.core.events import Event

        event = Event(
            type=EventType.TASK_CREATED,
            data={"task_id": "t1", "task": "Test"},
            task_id="t1",
        )

        # Validate the data payload
        model = EVENT_PAYLOAD_MODELS["TASK_CREATED"]
        validated = model(**event.data)
        assert validated.task_id == "t1"

    def test_event_serialization_for_websocket(self):
        """Events should serialize correctly for WebSocket transmission."""
        import json
        from sindri.core.events import Event

        event = Event(
            type=EventType.AGENT_OUTPUT,
            data={"task_id": "t1", "agent": "huginn", "text": "Hello"},
            task_id="t1",
        )

        # Simulate WebSocket message format
        message = {
            "type": event.type.name,
            "data": event.data,
            "timestamp": event.timestamp,
            "task_id": event.task_id,
        }

        # Should be JSON serializable
        json_str = json.dumps(message)
        assert json_str is not None

        # Parsed message should validate
        parsed = json.loads(json_str)
        model = EVENT_PAYLOAD_MODELS[parsed["type"]]
        validated = model(**parsed["data"])
        assert validated.text == "Hello"
