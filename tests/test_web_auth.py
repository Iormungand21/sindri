"""Tests for Sindri Web API Authentication.

Web/API Hardening PRD - Epic B: API Authentication tests.
"""

import os
import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient

from sindri.web.server import create_app, verify_auth_token
from sindri.config import ApiConfig


# ===== Fixtures =====


@pytest.fixture
def app_no_auth():
    """Create test application with auth disabled."""
    return create_app(vram_gb=16.0, auth_enabled=False)


@pytest.fixture
def app_with_auth():
    """Create test application with auth enabled."""
    return create_app(
        vram_gb=16.0,
        auth_enabled=True,
        static_tokens=["test-token-12345678", "another-valid-token"],
    )


@pytest.fixture
def client_no_auth(app_no_auth):
    """Create test client with auth disabled."""
    return TestClient(app_no_auth)


@pytest.fixture
def client_with_auth(app_with_auth):
    """Create test client with auth enabled."""
    return TestClient(app_with_auth)


# ===== ApiConfig Auth Tests =====


class TestApiConfigAuth:
    """Tests for ApiConfig authentication fields."""

    def test_api_config_defaults(self):
        """Test default auth configuration."""
        config = ApiConfig()
        assert config.auth_enabled is False
        assert config.static_tokens is None

    def test_api_config_auth_enabled(self):
        """Test auth_enabled field."""
        config = ApiConfig(auth_enabled=True, static_tokens=["my-token"])
        assert config.auth_enabled is True
        assert config.static_tokens == ["my-token"]

    def test_api_config_validate_auth_no_tokens(self):
        """Test validation fails when auth enabled but no tokens."""
        config = ApiConfig(auth_enabled=True, static_tokens=None)
        with pytest.raises(ValueError, match="no static_tokens configured"):
            config.validate_auth_config()

    def test_api_config_validate_auth_empty_tokens(self):
        """Test validation fails when auth enabled but tokens list empty."""
        config = ApiConfig(auth_enabled=True, static_tokens=[])
        with pytest.raises(ValueError, match="no static_tokens configured"):
            config.validate_auth_config()

    def test_api_config_validate_auth_with_tokens(self):
        """Test validation passes when auth enabled with tokens."""
        config = ApiConfig(auth_enabled=True, static_tokens=["my-token-123456789"])
        # Should not raise
        config.validate_auth_config()

    def test_api_config_get_effective_tokens(self):
        """Test get_effective_tokens returns configured tokens."""
        config = ApiConfig(static_tokens=["token1", "token2"])
        tokens = config.get_effective_tokens()
        assert "token1" in tokens
        assert "token2" in tokens

    def test_api_config_get_effective_tokens_returns_static(self, monkeypatch):
        """Test get_effective_tokens returns only static_tokens.

        Note: Environment variable tokens are resolved at initialization time
        in create_app() or CLI, not at runtime by get_effective_tokens().
        """
        # Even with env var set, get_effective_tokens only returns static_tokens
        monkeypatch.setenv("SINDRI_API_TOKENS", "env-token-1,env-token-2")
        config = ApiConfig(static_tokens=["config-token"])
        tokens = config.get_effective_tokens()
        assert tokens == ["config-token"]
        assert "env-token-1" not in tokens
        assert "env-token-2" not in tokens


# ===== Auth Disabled Tests =====


class TestAuthDisabled:
    """Tests for API when authentication is disabled."""

    def test_health_no_auth(self, client_no_auth):
        """Test health endpoint accessible without auth."""
        response = client_no_auth.get("/health")
        assert response.status_code == 200

    def test_agents_no_auth(self, client_no_auth):
        """Test agents endpoint accessible without auth."""
        response = client_no_auth.get("/api/agents")
        assert response.status_code == 200

    def test_version_no_auth(self, client_no_auth):
        """Test version endpoint accessible without auth."""
        response = client_no_auth.get("/api/version")
        assert response.status_code == 200

    def test_delete_trigger_no_auth(self, client_no_auth):
        """Test delete trigger endpoint works without auth when disabled."""
        response = client_no_auth.delete("/api/triggers/nonexistent-id")
        # Should be 404 (not found) not 401/403 (auth error)
        assert response.status_code == 404

    def test_approve_plan_no_auth(self, client_no_auth):
        """Test approve plan endpoint works without auth when disabled."""
        response = client_no_auth.post("/api/plans/nonexistent-id/approve")
        # Should be 404 (not found) not 401/403 (auth error)
        assert response.status_code == 404


# ===== Auth Enabled - Public Endpoints Tests =====


class TestAuthEnabledPublicEndpoints:
    """Tests for public endpoints when auth is enabled."""

    def test_health_public(self, client_with_auth):
        """Test health endpoint is always public."""
        response = client_with_auth.get("/health")
        assert response.status_code == 200

    def test_api_health_public(self, client_with_auth):
        """Test /api/health endpoint is always public."""
        response = client_with_auth.get("/api/health")
        assert response.status_code == 200

    def test_version_public(self, client_with_auth):
        """Test version endpoint is always public."""
        response = client_with_auth.get("/api/version")
        assert response.status_code == 200

    def test_schema_public(self, client_with_auth):
        """Test schema endpoint is always public."""
        response = client_with_auth.get("/api/schema")
        assert response.status_code == 200

    def test_agents_list_public(self, client_with_auth):
        """Test agents list endpoint is public."""
        response = client_with_auth.get("/api/agents")
        assert response.status_code == 200

    def test_agents_detail_public(self, client_with_auth):
        """Test agents detail endpoint is public."""
        response = client_with_auth.get("/api/agents/brokkr")
        assert response.status_code == 200

    def test_sessions_list_public(self, client_with_auth):
        """Test sessions list endpoint is public."""
        response = client_with_auth.get("/api/sessions")
        assert response.status_code == 200

    def test_tasks_list_public(self, client_with_auth):
        """Test tasks list endpoint is public."""
        response = client_with_auth.get("/api/tasks")
        assert response.status_code == 200

    def test_metrics_public(self, client_with_auth):
        """Test metrics endpoint is public."""
        response = client_with_auth.get("/api/metrics")
        assert response.status_code == 200

    def test_triggers_list_public(self, client_with_auth):
        """Test triggers list endpoint is public."""
        response = client_with_auth.get("/api/triggers")
        assert response.status_code == 200


# ===== Auth Enabled - Blocked Without Token Tests =====


class TestAuthEnabledBlocksWithoutToken:
    """Tests for mutation endpoints blocked without token when auth enabled."""

    def test_create_task_blocked(self, client_with_auth):
        """Test create task requires auth."""
        response = client_with_auth.post(
            "/api/tasks",
            json={"description": "Test task", "agent": "brokkr"},
        )
        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]

    def test_create_trigger_blocked(self, client_with_auth):
        """Test create trigger requires auth."""
        response = client_with_auth.post(
            "/api/triggers",
            json={
                "name": "test",
                "trigger_type": "cron",
                "task_description": "test",
                "cron_expression": "0 * * * *",
            },
        )
        assert response.status_code == 401

    def test_delete_trigger_blocked(self, client_with_auth):
        """Test delete trigger requires auth."""
        response = client_with_auth.delete("/api/triggers/some-id")
        assert response.status_code == 401

    def test_update_trigger_blocked(self, client_with_auth):
        """Test update trigger requires auth."""
        response = client_with_auth.put(
            "/api/triggers/some-id",
            json={"name": "updated"},
        )
        assert response.status_code == 401

    def test_enable_trigger_blocked(self, client_with_auth):
        """Test enable trigger requires auth."""
        response = client_with_auth.post("/api/triggers/some-id/enable")
        assert response.status_code == 401

    def test_disable_trigger_blocked(self, client_with_auth):
        """Test disable trigger requires auth."""
        response = client_with_auth.post("/api/triggers/some-id/disable")
        assert response.status_code == 401

    def test_run_trigger_blocked(self, client_with_auth):
        """Test run trigger requires auth."""
        response = client_with_auth.post("/api/triggers/some-id/run")
        assert response.status_code == 401

    def test_approve_plan_blocked(self, client_with_auth):
        """Test approve plan requires auth."""
        response = client_with_auth.post("/api/plans/some-id/approve")
        assert response.status_code == 401

    def test_reject_plan_blocked(self, client_with_auth):
        """Test reject plan requires auth."""
        response = client_with_auth.post("/api/plans/some-id/reject")
        assert response.status_code == 401

    def test_approve_step_blocked(self, client_with_auth):
        """Test approve step requires auth."""
        response = client_with_auth.post("/api/plans/some-id/steps/1/approve")
        assert response.status_code == 401

    def test_reject_step_blocked(self, client_with_auth):
        """Test reject step requires auth."""
        response = client_with_auth.post("/api/plans/some-id/steps/1/reject")
        assert response.status_code == 401

    def test_accept_step_blocked(self, client_with_auth):
        """Test accept step requires auth."""
        response = client_with_auth.post("/api/plans/some-id/steps/1/accept")
        assert response.status_code == 401

    def test_rerun_step_blocked(self, client_with_auth):
        """Test rerun step requires auth."""
        response = client_with_auth.post("/api/plans/some-id/steps/1/rerun")
        assert response.status_code == 401

    def test_import_coverage_blocked(self, client_with_auth):
        """Test import coverage requires auth."""
        response = client_with_auth.post(
            "/api/sessions/some-id/coverage",
            json={"coverage_path": "/tmp/coverage.xml"},
        )
        assert response.status_code == 401

    def test_delete_coverage_blocked(self, client_with_auth):
        """Test delete coverage requires auth."""
        response = client_with_auth.delete("/api/sessions/some-id/coverage")
        assert response.status_code == 401


# ===== Auth Enabled - Valid Token Tests =====


class TestAuthEnabledValidToken:
    """Tests for mutation endpoints with valid token.

    Note: We test auth using endpoints that complete quickly without
    requiring external services. Endpoints like create_task require
    Ollama and would hang in tests.
    """

    def test_delete_trigger_with_x_sindri_token(self, client_with_auth):
        """Test delete trigger with X-Sindri-Token header."""
        response = client_with_auth.delete(
            "/api/triggers/nonexistent-id",
            headers={"X-Sindri-Token": "test-token-12345678"},
        )
        # Should be 404 (not found) not 401/403 (auth error)
        assert response.status_code == 404

    def test_delete_trigger_with_bearer_token(self, client_with_auth):
        """Test delete trigger with Authorization: Bearer header."""
        response = client_with_auth.delete(
            "/api/triggers/nonexistent-id",
            headers={"Authorization": "Bearer test-token-12345678"},
        )
        # Should be 404 (not found) not 401/403 (auth error)
        assert response.status_code == 404

    def test_delete_trigger_with_alternative_token(self, client_with_auth):
        """Test delete trigger with alternative valid token."""
        response = client_with_auth.delete(
            "/api/triggers/nonexistent-id",
            headers={"X-Sindri-Token": "another-valid-token"},
        )
        # Should be 404 (not found) not 401/403 (auth error)
        assert response.status_code == 404

    def test_approve_plan_with_token(self, client_with_auth):
        """Test approve plan with valid token (will 404 but not 401/403)."""
        response = client_with_auth.post(
            "/api/plans/nonexistent-id/approve",
            headers={"X-Sindri-Token": "test-token-12345678"},
        )
        # Should be 404 (not found) not 401/403 (auth error)
        assert response.status_code == 404

    def test_enable_trigger_with_token(self, client_with_auth):
        """Test enable trigger with valid token (will 404 but not 401/403)."""
        response = client_with_auth.post(
            "/api/triggers/nonexistent-id/enable",
            headers={"X-Sindri-Token": "test-token-12345678"},
        )
        # Should be 404 (not found) not 401/403 (auth error)
        assert response.status_code == 404

    def test_delete_coverage_with_token(self, client_with_auth):
        """Test delete coverage with valid token (will 404 but not 401/403)."""
        response = client_with_auth.delete(
            "/api/sessions/nonexistent-id/coverage",
            headers={"X-Sindri-Token": "test-token-12345678"},
        )
        # Should be 404 (not found) not 401/403 (auth error)
        assert response.status_code == 404


# ===== Auth Enabled - Invalid Token Tests =====


class TestAuthEnabledInvalidToken:
    """Tests for mutation endpoints with invalid token."""

    def test_create_task_invalid_token(self, client_with_auth):
        """Test create task with invalid token returns 403."""
        response = client_with_auth.post(
            "/api/tasks",
            json={"description": "Test task", "agent": "brokkr"},
            headers={"X-Sindri-Token": "wrong-token"},
        )
        assert response.status_code == 403
        assert "Invalid API token" in response.json()["detail"]

    def test_create_task_invalid_bearer_token(self, client_with_auth):
        """Test create task with invalid bearer token returns 403."""
        response = client_with_auth.post(
            "/api/tasks",
            json={"description": "Test task", "agent": "brokkr"},
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert response.status_code == 403

    def test_create_trigger_invalid_token(self, client_with_auth):
        """Test create trigger with invalid token returns 403."""
        response = client_with_auth.post(
            "/api/triggers",
            json={
                "name": "test",
                "trigger_type": "cron",
                "task_description": "test",
                "cron_expression": "0 * * * *",
            },
            headers={"X-Sindri-Token": "bad-token"},
        )
        assert response.status_code == 403


# ===== WebSocket Auth Tests =====


class TestWebSocketAuth:
    """Tests for WebSocket authentication."""

    def test_websocket_no_auth_when_disabled(self, app_no_auth):
        """Test WebSocket connects without token when auth disabled."""
        client = TestClient(app_no_auth)
        with client.websocket_connect("/ws") as websocket:
            data = websocket.receive_json()
            assert data["type"] == "connected"

    def test_websocket_requires_token_when_enabled(self, app_with_auth):
        """Test WebSocket requires token when auth enabled."""
        client = TestClient(app_with_auth)
        # Without token, should fail to connect
        with pytest.raises(Exception):
            with client.websocket_connect("/ws"):
                pass

    def test_websocket_connects_with_valid_token(self, app_with_auth):
        """Test WebSocket connects with valid token in query param."""
        client = TestClient(app_with_auth)
        with client.websocket_connect("/ws?token=test-token-12345678") as websocket:
            data = websocket.receive_json()
            assert data["type"] == "connected"

    def test_websocket_rejects_invalid_token(self, app_with_auth):
        """Test WebSocket rejects invalid token."""
        client = TestClient(app_with_auth)
        with pytest.raises(Exception):
            with client.websocket_connect("/ws?token=bad-token"):
                pass


# ===== Create App Auth Configuration Tests =====


class TestTokenPrecedence:
    """Tests for token precedence: CLI > config > env.

    Both CLI and create_app follow the same precedence:
    1. Explicit tokens (--token or static_tokens param) override everything
    2. Config file tokens override env var
    3. SINDRI_API_TOKENS env var is fallback only
    """

    def test_explicit_tokens_override_env(self, monkeypatch):
        """Explicit static_tokens should completely override env tokens."""
        monkeypatch.setenv("SINDRI_API_TOKENS", "env-token-ignored")
        app = create_app(
            vram_gb=16.0,
            auth_enabled=True,
            static_tokens=["explicit-only"],
        )
        client = TestClient(app)

        # Env token should NOT work
        response = client.delete(
            "/api/triggers/x",
            headers={"X-Sindri-Token": "env-token-ignored"},
        )
        assert response.status_code == 403

        # Explicit token should work
        response = client.delete(
            "/api/triggers/x",
            headers={"X-Sindri-Token": "explicit-only"},
        )
        assert response.status_code == 404

    def test_env_tokens_used_when_no_explicit(self, monkeypatch):
        """Env tokens should be used when no explicit tokens provided."""
        monkeypatch.setenv("SINDRI_AUTH_ENABLED", "1")
        monkeypatch.setenv("SINDRI_API_TOKENS", "env-token-works")
        app = create_app(vram_gb=16.0)
        client = TestClient(app)

        # Env token should work
        response = client.delete(
            "/api/triggers/x",
            headers={"X-Sindri-Token": "env-token-works"},
        )
        assert response.status_code == 404


class TestCreateAppAuth:
    """Tests for create_app auth configuration."""

    def test_create_app_no_auth_default(self):
        """Test create_app defaults to no auth."""
        app = create_app(vram_gb=16.0)
        client = TestClient(app)
        # Use an endpoint that completes quickly
        response = client.delete("/api/triggers/nonexistent-id")
        # Should be 404, not 401/403 (no auth required)
        assert response.status_code == 404

    def test_create_app_with_auth_enabled(self):
        """Test create_app with auth enabled."""
        app = create_app(
            vram_gb=16.0,
            auth_enabled=True,
            static_tokens=["my-secret-token123"],
        )
        client = TestClient(app)
        # Should require auth for mutations
        response = client.delete("/api/triggers/nonexistent-id")
        assert response.status_code == 401

    def test_create_app_auth_enabled_no_tokens_raises(self):
        """Test create_app with auth enabled but no tokens raises error."""
        with pytest.raises(ValueError, match="no static_tokens configured"):
            create_app(vram_gb=16.0, auth_enabled=True, static_tokens=None)

    def test_create_app_auth_from_env(self, monkeypatch):
        """Test create_app reads auth config from environment variables."""
        monkeypatch.setenv("SINDRI_AUTH_ENABLED", "1")
        monkeypatch.setenv("SINDRI_API_TOKENS", "env-token-12345678")
        app = create_app(vram_gb=16.0)
        client = TestClient(app)

        # Should require auth
        response = client.delete("/api/triggers/nonexistent-id")
        assert response.status_code == 401

        # Should work with token
        response = client.delete(
            "/api/triggers/nonexistent-id",
            headers={"X-Sindri-Token": "env-token-12345678"},
        )
        assert response.status_code == 404  # Not 401, so auth worked

    def test_create_app_explicit_false_overrides_env(self, monkeypatch):
        """Test that explicit auth_enabled=False overrides SINDRI_AUTH_ENABLED=1."""
        monkeypatch.setenv("SINDRI_AUTH_ENABLED", "1")
        monkeypatch.setenv("SINDRI_API_TOKENS", "env-token-12345678")

        # Explicitly disable auth - should override env var
        app = create_app(vram_gb=16.0, auth_enabled=False)
        client = TestClient(app)

        # Should NOT require auth (explicit False overrides env)
        response = client.delete("/api/triggers/nonexistent-id")
        assert response.status_code == 404  # Not 401

    def test_create_app_explicit_true_without_env_tokens(self, monkeypatch):
        """Test that explicit auth_enabled=True with explicit tokens ignores env."""
        monkeypatch.setenv("SINDRI_API_TOKENS", "env-token-should-be-ignored")

        # Explicitly enable auth with specific tokens
        app = create_app(
            vram_gb=16.0,
            auth_enabled=True,
            static_tokens=["explicit-token-123"],
        )
        client = TestClient(app)

        # Should require auth
        response = client.delete("/api/triggers/nonexistent-id")
        assert response.status_code == 401

        # Env token should NOT work (explicit tokens override)
        response = client.delete(
            "/api/triggers/nonexistent-id",
            headers={"X-Sindri-Token": "env-token-should-be-ignored"},
        )
        assert response.status_code == 403  # Invalid token

        # Explicit token should work
        response = client.delete(
            "/api/triggers/nonexistent-id",
            headers={"X-Sindri-Token": "explicit-token-123"},
        )
        assert response.status_code == 404  # Auth worked


# ===== All Mutation Endpoints Parametrized Test =====


# Mutation endpoints that complete quickly (don't require external services)
# Excludes: /api/tasks (requires Ollama), /api/triggers (create/run require execution)
QUICK_MUTATION_ENDPOINTS = [
    ("POST", "/api/plans/test-id/approve", None),
    ("POST", "/api/plans/test-id/reject", None),
    ("POST", "/api/plans/test-id/steps/1/approve", None),
    ("POST", "/api/plans/test-id/steps/1/reject", None),
    ("POST", "/api/plans/test-id/steps/1/accept", None),
    ("POST", "/api/plans/test-id/steps/1/rerun", None),
    ("POST", "/api/sessions/test-id/coverage", {"coverage_path": "/tmp/cov.xml"}),
    ("DELETE", "/api/sessions/test-id/coverage", None),
    ("PUT", "/api/triggers/test-id", {"name": "updated"}),
    ("DELETE", "/api/triggers/test-id", None),
    ("POST", "/api/triggers/test-id/enable", None),
    ("POST", "/api/triggers/test-id/disable", None),
]


class TestAllMutationEndpointsGated:
    """Parametrized tests to ensure all mutation endpoints are auth-gated."""

    @pytest.mark.parametrize("method,endpoint,body", QUICK_MUTATION_ENDPOINTS)
    def test_mutation_endpoint_requires_auth(self, client_with_auth, method, endpoint, body):
        """Test that mutation endpoint requires authentication."""
        if method == "POST":
            response = client_with_auth.post(endpoint, json=body)
        elif method == "PUT":
            response = client_with_auth.put(endpoint, json=body)
        elif method == "DELETE":
            response = client_with_auth.delete(endpoint)
        else:
            pytest.fail(f"Unknown method: {method}")

        assert response.status_code == 401, f"{method} {endpoint} should require auth"

    @pytest.mark.parametrize("method,endpoint,body", QUICK_MUTATION_ENDPOINTS)
    def test_mutation_endpoint_works_with_token(self, client_with_auth, method, endpoint, body):
        """Test that mutation endpoint works with valid token."""
        headers = {"X-Sindri-Token": "test-token-12345678"}
        if method == "POST":
            response = client_with_auth.post(endpoint, json=body, headers=headers)
        elif method == "PUT":
            response = client_with_auth.put(endpoint, json=body, headers=headers)
        elif method == "DELETE":
            response = client_with_auth.delete(endpoint, headers=headers)
        else:
            pytest.fail(f"Unknown method: {method}")

        # Should not be 401 or 403 - may be 404 or 400 for other reasons
        assert response.status_code not in (401, 403), (
            f"{method} {endpoint} should not reject valid token"
        )

    def test_create_task_requires_auth(self, client_with_auth):
        """Test that create task requires authentication (separate due to complexity)."""
        response = client_with_auth.post(
            "/api/tasks",
            json={"description": "Test", "agent": "brokkr"},
        )
        assert response.status_code == 401

    def test_create_trigger_requires_auth(self, client_with_auth):
        """Test that create trigger requires authentication."""
        response = client_with_auth.post(
            "/api/triggers",
            json={
                "name": "test",
                "trigger_type": "cron",
                "task_description": "test",
                "cron_expression": "0 * * * *",
            },
        )
        assert response.status_code == 401

    def test_run_trigger_requires_auth(self, client_with_auth):
        """Test that run trigger requires authentication."""
        response = client_with_auth.post("/api/triggers/test-id/run")
        assert response.status_code == 401
