"""Tests for Kubernetes tools."""

import pytest
from unittest.mock import patch, AsyncMock

from sindri.tools.kubernetes import (
    KUBECTL_AVAILABLE,
    K8sApplyTool,
    K8sGetPodsTool,
    K8sLogsTool,
    K8sGetServicesTool,
    K8sDescribeTool,
    K8sDeleteTool,
)


class TestKubectlAvailability:
    """Tests for kubectl availability detection."""

    def test_kubectl_available_is_boolean(self):
        """KUBECTL_AVAILABLE should be a boolean."""
        assert isinstance(KUBECTL_AVAILABLE, bool)


class TestK8sApplyTool:
    """Tests for K8sApplyTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        return K8sApplyTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_cli_not_available(self, tool):
        """Test behavior when kubectl is not installed."""
        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", False):
            result = await tool.execute(manifest="deployment.yaml")
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_manifest_file_not_found(self, tool):
        """Test handling of missing manifest file."""
        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            result = await tool.execute(manifest="nonexistent.yaml")
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_apply_success(self, tool, tmp_path):
        """Test successful manifest apply."""
        manifest_file = tmp_path / "deployment.yaml"
        manifest_file.write_text("apiVersion: v1\nkind: Pod")

        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(0, "pod/test-pod created", ""))):
                result = await tool.execute(manifest=str(manifest_file))

        assert result.success is True
        assert "created" in result.output

    @pytest.mark.asyncio
    async def test_apply_with_namespace(self, tool, tmp_path):
        """Test apply with namespace specified."""
        manifest_file = tmp_path / "deployment.yaml"
        manifest_file.write_text("apiVersion: v1\nkind: Pod")

        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(0, "", ""))) as mock:
                result = await tool.execute(manifest=str(manifest_file), namespace="production")

        assert result.success is True
        assert result.metadata["namespace"] == "production"
        call_args = mock.call_args[0]
        assert "-n" in call_args
        assert "production" in call_args

    @pytest.mark.asyncio
    async def test_apply_dry_run(self, tool, tmp_path):
        """Test dry run mode."""
        manifest_file = tmp_path / "deployment.yaml"
        manifest_file.write_text("apiVersion: v1\nkind: Pod")

        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(0, "", ""))) as mock:
                result = await tool.execute(manifest=str(manifest_file), dry_run=True)

        assert result.success is True
        assert result.metadata["dry_run"] is True
        call_args = mock.call_args[0]
        assert "--dry-run=client" in call_args

    @pytest.mark.asyncio
    async def test_apply_inline_yaml(self, tool):
        """Test applying inline YAML content."""
        inline_yaml = "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test"

        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(0, "pod/test created", ""))) as mock:
                result = await tool.execute(manifest=inline_yaml, inline=True)

        assert result.success is True
        assert result.metadata["inline"] is True
        # Check stdin was used
        call_kwargs = mock.call_args[1]
        assert call_kwargs.get("input_data") == inline_yaml

    @pytest.mark.asyncio
    async def test_apply_failure(self, tool, tmp_path):
        """Test handling of apply errors."""
        manifest_file = tmp_path / "invalid.yaml"
        manifest_file.write_text("invalid: yaml: content")

        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(1, "", "error: invalid yaml"))):
                result = await tool.execute(manifest=str(manifest_file))

        assert result.success is False
        assert "invalid yaml" in result.error.lower()


class TestK8sGetPodsTool:
    """Tests for K8sGetPodsTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        return K8sGetPodsTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_cli_not_available(self, tool):
        """Test behavior when kubectl is not installed."""
        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", False):
            result = await tool.execute()
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_get_pods_success(self, tool):
        """Test successful pod listing."""
        mock_output = """NAME                    READY   STATUS    RESTARTS   AGE
nginx-pod-1             1/1     Running   0          1d
nginx-pod-2             1/1     Running   0          1d"""

        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(0, mock_output, ""))):
                result = await tool.execute()

        assert result.success is True
        assert "nginx-pod-1" in result.output
        assert result.metadata["pod_count"] == 2

    @pytest.mark.asyncio
    async def test_get_pods_all_namespaces(self, tool):
        """Test listing pods across all namespaces."""
        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(0, "NAME STATUS\n", ""))) as mock:
                result = await tool.execute(all_namespaces=True)

        assert result.success is True
        assert result.metadata["namespace"] == "all"
        call_args = mock.call_args[0]
        assert "-A" in call_args

    @pytest.mark.asyncio
    async def test_get_pods_with_selector(self, tool):
        """Test filtering pods by label selector."""
        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(0, "", ""))) as mock:
                result = await tool.execute(selector="app=nginx")

        assert result.success is True
        assert result.metadata["selector"] == "app=nginx"
        call_args = mock.call_args[0]
        assert "-l" in call_args
        assert "app=nginx" in call_args

    @pytest.mark.asyncio
    async def test_get_pods_json_output(self, tool):
        """Test JSON output format."""
        mock_output = '{"items": [{"metadata": {"name": "pod1"}}, {"metadata": {"name": "pod2"}}]}'

        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(0, mock_output, ""))) as mock:
                result = await tool.execute(output_format="json")

        assert result.success is True
        assert result.metadata["output_format"] == "json"
        assert result.metadata["pod_count"] == 2
        call_args = mock.call_args[0]
        assert "-o" in call_args
        assert "json" in call_args

    @pytest.mark.asyncio
    async def test_get_pods_failure(self, tool):
        """Test handling of API errors."""
        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(1, "", "error: namespace not found"))):
                result = await tool.execute(namespace="nonexistent")

        assert result.success is False
        assert "namespace not found" in result.error.lower()


class TestK8sLogsTool:
    """Tests for K8sLogsTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        return K8sLogsTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_cli_not_available(self, tool):
        """Test behavior when kubectl is not installed."""
        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", False):
            result = await tool.execute(pod="my-pod")
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_get_logs_success(self, tool):
        """Test successful log retrieval."""
        mock_output = """2024-01-01 12:00:00 Starting server
2024-01-01 12:00:01 Server ready on port 8080"""

        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(0, mock_output, ""))):
                result = await tool.execute(pod="my-pod")

        assert result.success is True
        assert "Starting server" in result.output
        assert result.metadata["pod"] == "my-pod"
        assert result.metadata["line_count"] == 2

    @pytest.mark.asyncio
    async def test_get_logs_with_container(self, tool):
        """Test getting logs from a specific container."""
        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(0, "logs", ""))) as mock:
                result = await tool.execute(pod="my-pod", container="nginx")

        assert result.success is True
        assert result.metadata["container"] == "nginx"
        call_args = mock.call_args[0]
        assert "-c" in call_args
        assert "nginx" in call_args

    @pytest.mark.asyncio
    async def test_get_logs_with_tail(self, tool):
        """Test limiting log lines with tail."""
        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(0, "", ""))) as mock:
                result = await tool.execute(pod="my-pod", tail=100)

        assert result.success is True
        assert result.metadata["tail"] == 100
        call_args = mock.call_args[0]
        assert "--tail" in call_args
        assert "100" in call_args

    @pytest.mark.asyncio
    async def test_get_logs_previous(self, tool):
        """Test getting logs from previous container instance."""
        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(0, "", ""))) as mock:
                result = await tool.execute(pod="my-pod", previous=True)

        assert result.success is True
        call_args = mock.call_args[0]
        assert "--previous" in call_args

    @pytest.mark.asyncio
    async def test_get_logs_since(self, tool):
        """Test getting logs since a duration."""
        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(0, "", ""))) as mock:
                result = await tool.execute(pod="my-pod", since="5m")

        assert result.success is True
        call_args = mock.call_args[0]
        assert "--since" in call_args
        assert "5m" in call_args

    @pytest.mark.asyncio
    async def test_get_logs_failure(self, tool):
        """Test handling of log retrieval errors."""
        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(1, "", "error: pod not found"))):
                result = await tool.execute(pod="nonexistent")

        assert result.success is False
        assert "pod not found" in result.error.lower()


class TestK8sGetServicesTool:
    """Tests for K8sGetServicesTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        return K8sGetServicesTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_cli_not_available(self, tool):
        """Test behavior when kubectl is not installed."""
        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", False):
            result = await tool.execute()
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_get_services_success(self, tool):
        """Test successful service listing."""
        mock_output = """NAME         TYPE        CLUSTER-IP       EXTERNAL-IP   PORT(S)
kubernetes   ClusterIP   10.96.0.1        <none>        443/TCP
nginx        LoadBalancer 10.96.0.100     1.2.3.4       80:30080/TCP"""

        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(0, mock_output, ""))):
                result = await tool.execute()

        assert result.success is True
        assert "kubernetes" in result.output
        assert "nginx" in result.output
        assert result.metadata["service_count"] == 2

    @pytest.mark.asyncio
    async def test_get_services_all_namespaces(self, tool):
        """Test listing services across all namespaces."""
        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(0, "NAME TYPE\n", ""))) as mock:
                result = await tool.execute(all_namespaces=True)

        assert result.success is True
        call_args = mock.call_args[0]
        assert "-A" in call_args

    @pytest.mark.asyncio
    async def test_get_services_json_output(self, tool):
        """Test JSON output format."""
        mock_output = '{"items": [{"metadata": {"name": "svc1"}}]}'

        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(0, mock_output, ""))):
                result = await tool.execute(output_format="json")

        assert result.success is True
        assert result.metadata["output_format"] == "json"
        assert result.metadata["service_count"] == 1


class TestK8sDescribeTool:
    """Tests for K8sDescribeTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        return K8sDescribeTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_cli_not_available(self, tool):
        """Test behavior when kubectl is not installed."""
        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", False):
            result = await tool.execute(resource_type="pod", name="my-pod")
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_describe_pod_success(self, tool):
        """Test successful pod description."""
        mock_output = """Name:         nginx-pod
Namespace:    default
Node:         worker-1
Status:       Running
Events:
  Type     Reason     Age   Message
  Normal   Scheduled  1m    Successfully assigned"""

        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(0, mock_output, ""))):
                result = await tool.execute(resource_type="pod", name="nginx-pod")

        assert result.success is True
        assert "nginx-pod" in result.output
        assert "Running" in result.output
        assert result.metadata["resource_type"] == "pod"
        assert result.metadata["name"] == "nginx-pod"

    @pytest.mark.asyncio
    async def test_describe_with_namespace(self, tool):
        """Test describe with namespace."""
        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(0, "", ""))) as mock:
                result = await tool.execute(resource_type="deployment", name="web-app", namespace="production")

        assert result.success is True
        assert result.metadata["namespace"] == "production"
        call_args = mock.call_args[0]
        assert "-n" in call_args
        assert "production" in call_args

    @pytest.mark.asyncio
    async def test_describe_failure(self, tool):
        """Test handling of describe errors."""
        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(1, "", "Error: resource not found"))):
                result = await tool.execute(resource_type="pod", name="nonexistent")

        assert result.success is False
        assert "not found" in result.error.lower()


class TestK8sDeleteTool:
    """Tests for K8sDeleteTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        return K8sDeleteTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_cli_not_available(self, tool):
        """Test behavior when kubectl is not installed."""
        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", False):
            result = await tool.execute(resource_type="pod", name="my-pod")
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_delete_success(self, tool):
        """Test successful resource deletion."""
        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(0, 'pod "my-pod" deleted', ""))):
                result = await tool.execute(resource_type="pod", name="my-pod")

        assert result.success is True
        assert "deleted" in result.output
        assert result.metadata["resource_type"] == "pod"
        assert result.metadata["name"] == "my-pod"

    @pytest.mark.asyncio
    async def test_delete_with_namespace(self, tool):
        """Test delete with namespace."""
        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(0, "", ""))) as mock:
                result = await tool.execute(resource_type="deployment", name="web", namespace="production")

        assert result.success is True
        call_args = mock.call_args[0]
        assert "-n" in call_args
        assert "production" in call_args

    @pytest.mark.asyncio
    async def test_delete_force(self, tool):
        """Test force deletion."""
        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(0, "", ""))) as mock:
                result = await tool.execute(resource_type="pod", name="stuck-pod", force=True)

        assert result.success is True
        assert result.metadata["force"] is True
        call_args = mock.call_args[0]
        assert "--force" in call_args

    @pytest.mark.asyncio
    async def test_delete_grace_period(self, tool):
        """Test deletion with grace period."""
        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(0, "", ""))) as mock:
                result = await tool.execute(resource_type="pod", name="my-pod", grace_period=0)

        assert result.success is True
        assert result.metadata["grace_period"] == 0
        call_args = mock.call_args[0]
        assert "--grace-period" in call_args
        assert "0" in call_args

    @pytest.mark.asyncio
    async def test_delete_failure(self, tool):
        """Test handling of delete errors."""
        with patch("sindri.tools.kubernetes.KUBECTL_AVAILABLE", True):
            with patch("sindri.tools.kubernetes._run_kubectl", AsyncMock(return_value=(1, "", 'Error: pod "nonexistent" not found'))):
                result = await tool.execute(resource_type="pod", name="nonexistent")

        assert result.success is False
        assert "not found" in result.error.lower()


class TestK8sToolRegistry:
    """Tests for Kubernetes tool registration."""

    def test_tools_registered(self, tmp_path):
        """Test that all Kubernetes tools are registered in the registry."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default(work_dir=tmp_path)

        # Check all K8s tools are registered
        k8s_tools = [
            "k8s_apply",
            "k8s_get_pods",
            "k8s_logs",
            "k8s_get_services",
            "k8s_describe",
            "k8s_delete",
        ]

        for tool_name in k8s_tools:
            assert registry.get_tool(tool_name) is not None, f"Tool {tool_name} not registered"
