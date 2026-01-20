"""Tests for AWS tools."""

import pytest
from unittest.mock import patch, AsyncMock

from sindri.tools.aws import (
    AWS_AVAILABLE,
    AwsS3ListTool,
    AwsS3UploadTool,
    AwsS3DownloadTool,
    AwsLogsQueryTool,
    AwsEc2ListTool,
    AwsLambdaInvokeTool,
)


class TestAwsAvailability:
    """Tests for AWS CLI availability detection."""

    def test_aws_available_is_boolean(self):
        """AWS_AVAILABLE should be a boolean."""
        assert isinstance(AWS_AVAILABLE, bool)


class TestAwsS3ListTool:
    """Tests for AwsS3ListTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        return AwsS3ListTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_cli_not_available(self, tool):
        """Test behavior when AWS CLI is not installed."""
        with patch("sindri.tools.aws.AWS_AVAILABLE", False):
            result = await tool.execute()
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_list_buckets_success(self, tool):
        """Test listing all S3 buckets."""
        mock_output = "2024-01-01 12:00:00 mybucket\n2024-01-02 12:00:00 otherbucket"
        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            with patch("sindri.tools.aws._run_aws", AsyncMock(return_value=(0, mock_output, ""))):
                result = await tool.execute()

        assert result.success is True
        assert "mybucket" in result.output
        assert "otherbucket" in result.output
        assert result.metadata["item_count"] == 2

    @pytest.mark.asyncio
    async def test_list_objects_in_bucket(self, tool):
        """Test listing objects in a specific bucket."""
        mock_output = """2024-01-01 12:00:00       1024 file1.txt
2024-01-01 12:00:00       2048 file2.txt"""
        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            with patch("sindri.tools.aws._run_aws", AsyncMock(return_value=(0, mock_output, ""))) as mock:
                result = await tool.execute(bucket="mybucket", prefix="data/")

        assert result.success is True
        assert result.metadata["bucket"] == "mybucket"
        assert result.metadata["prefix"] == "data/"
        # Verify s3:// path was constructed
        call_args = mock.call_args[0]
        assert "s3://mybucket/data/" in call_args

    @pytest.mark.asyncio
    async def test_list_recursive(self, tool):
        """Test recursive listing."""
        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            with patch("sindri.tools.aws._run_aws", AsyncMock(return_value=(0, "", ""))) as mock:
                result = await tool.execute(bucket="mybucket", recursive=True)

        assert result.success is True
        assert result.metadata["recursive"] is True
        call_args = mock.call_args[0]
        assert "--recursive" in call_args

    @pytest.mark.asyncio
    async def test_list_failure(self, tool):
        """Test handling of AWS CLI errors."""
        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            with patch("sindri.tools.aws._run_aws", AsyncMock(return_value=(1, "", "Access Denied"))):
                result = await tool.execute(bucket="mybucket")

        assert result.success is False
        assert "Access Denied" in result.error


class TestAwsS3UploadTool:
    """Tests for AwsS3UploadTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        return AwsS3UploadTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_cli_not_available(self, tool):
        """Test behavior when AWS CLI is not installed."""
        with patch("sindri.tools.aws.AWS_AVAILABLE", False):
            result = await tool.execute(source="file.txt", destination="s3://bucket/file.txt")
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_source_not_found(self, tool, tmp_path):
        """Test handling of nonexistent source file."""
        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            result = await tool.execute(source="nonexistent.txt", destination="s3://bucket/file.txt")
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_upload_success(self, tool, tmp_path):
        """Test successful file upload."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            with patch("sindri.tools.aws._run_aws", AsyncMock(return_value=(0, "upload: test.txt to s3://bucket/test.txt", ""))):
                result = await tool.execute(source=str(test_file), destination="s3://bucket/test.txt")

        assert result.success is True
        assert result.metadata["destination"] == "s3://bucket/test.txt"

    @pytest.mark.asyncio
    async def test_upload_recursive(self, tool, tmp_path):
        """Test recursive directory upload."""
        test_dir = tmp_path / "data"
        test_dir.mkdir()
        (test_dir / "file1.txt").write_text("content1")

        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            with patch("sindri.tools.aws._run_aws", AsyncMock(return_value=(0, "", ""))) as mock:
                result = await tool.execute(source=str(test_dir), destination="s3://bucket/data/", recursive=True)

        assert result.success is True
        assert result.metadata["recursive"] is True
        call_args = mock.call_args[0]
        assert "--recursive" in call_args

    @pytest.mark.asyncio
    async def test_upload_adds_s3_prefix(self, tool, tmp_path):
        """Test that s3:// is added if missing from destination."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")

        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            with patch("sindri.tools.aws._run_aws", AsyncMock(return_value=(0, "", ""))) as mock:
                result = await tool.execute(source=str(test_file), destination="bucket/test.txt")

        call_args = mock.call_args[0]
        assert "s3://bucket/test.txt" in call_args


class TestAwsS3DownloadTool:
    """Tests for AwsS3DownloadTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        return AwsS3DownloadTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_cli_not_available(self, tool):
        """Test behavior when AWS CLI is not installed."""
        with patch("sindri.tools.aws.AWS_AVAILABLE", False):
            result = await tool.execute(source="s3://bucket/file.txt", destination="file.txt")
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_download_success(self, tool, tmp_path):
        """Test successful file download."""
        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            with patch("sindri.tools.aws._run_aws", AsyncMock(return_value=(0, "download: s3://bucket/file.txt to file.txt", ""))):
                result = await tool.execute(source="s3://bucket/file.txt", destination=str(tmp_path / "file.txt"))

        assert result.success is True
        assert result.metadata["source"] == "s3://bucket/file.txt"

    @pytest.mark.asyncio
    async def test_download_adds_s3_prefix(self, tool, tmp_path):
        """Test that s3:// is added if missing from source."""
        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            with patch("sindri.tools.aws._run_aws", AsyncMock(return_value=(0, "", ""))) as mock:
                result = await tool.execute(source="bucket/file.txt", destination=str(tmp_path / "file.txt"))

        call_args = mock.call_args[0]
        assert "s3://bucket/file.txt" in call_args

    @pytest.mark.asyncio
    async def test_download_failure(self, tool, tmp_path):
        """Test handling of download errors."""
        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            with patch("sindri.tools.aws._run_aws", AsyncMock(return_value=(1, "", "Not Found"))):
                result = await tool.execute(source="s3://bucket/nonexistent.txt", destination=str(tmp_path / "file.txt"))

        assert result.success is False
        assert "Not Found" in result.error


class TestAwsLogsQueryTool:
    """Tests for AwsLogsQueryTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        return AwsLogsQueryTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_cli_not_available(self, tool):
        """Test behavior when AWS CLI is not installed."""
        with patch("sindri.tools.aws.AWS_AVAILABLE", False):
            result = await tool.execute(log_group="/aws/lambda/myfunction")
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_query_logs_success(self, tool):
        """Test successful log query."""
        mock_output = '{"events": [{"timestamp": 1704067200000, "message": "test log message"}]}'
        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            with patch("sindri.tools.aws._run_aws", AsyncMock(return_value=(0, mock_output, ""))):
                result = await tool.execute(log_group="/aws/lambda/myfunction")

        assert result.success is True
        assert result.metadata["event_count"] == 1
        assert "test log message" in result.output

    @pytest.mark.asyncio
    async def test_query_with_filter(self, tool):
        """Test log query with filter pattern."""
        mock_output = '{"events": []}'
        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            with patch("sindri.tools.aws._run_aws", AsyncMock(return_value=(0, mock_output, ""))) as mock:
                result = await tool.execute(log_group="/aws/lambda/fn", filter_pattern="ERROR")

        assert result.success is True
        call_args = mock.call_args[0]
        assert "--filter-pattern" in call_args
        assert "ERROR" in call_args

    @pytest.mark.asyncio
    async def test_query_with_time_range(self, tool):
        """Test log query with time range."""
        mock_output = '{"events": []}'
        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            with patch("sindri.tools.aws._run_aws", AsyncMock(return_value=(0, mock_output, ""))) as mock:
                result = await tool.execute(log_group="/aws/lambda/fn", start_time="1h", limit=100)

        assert result.success is True
        assert result.metadata["limit"] == 100
        call_args = mock.call_args[0]
        assert "--limit" in call_args
        assert "100" in call_args

    @pytest.mark.asyncio
    async def test_query_failure(self, tool):
        """Test handling of log query errors."""
        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            with patch("sindri.tools.aws._run_aws", AsyncMock(return_value=(1, "", "ResourceNotFoundException"))):
                result = await tool.execute(log_group="/aws/lambda/nonexistent")

        assert result.success is False
        assert "ResourceNotFoundException" in result.error


class TestAwsEc2ListTool:
    """Tests for AwsEc2ListTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        return AwsEc2ListTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_cli_not_available(self, tool):
        """Test behavior when AWS CLI is not installed."""
        with patch("sindri.tools.aws.AWS_AVAILABLE", False):
            result = await tool.execute()
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_list_instances_success(self, tool):
        """Test successful instance listing."""
        mock_output = """{
            "Reservations": [{
                "Instances": [{
                    "InstanceId": "i-1234567890abcdef0",
                    "InstanceType": "t3.micro",
                    "State": {"Name": "running"},
                    "PublicIpAddress": "1.2.3.4",
                    "PrivateIpAddress": "10.0.0.1",
                    "Tags": [{"Key": "Name", "Value": "web-server"}]
                }]
            }]
        }"""
        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            with patch("sindri.tools.aws._run_aws", AsyncMock(return_value=(0, mock_output, ""))):
                result = await tool.execute()

        assert result.success is True
        assert result.metadata["instance_count"] == 1
        assert "i-1234567890abcdef0" in result.output
        assert "web-server" in result.output

    @pytest.mark.asyncio
    async def test_list_running_instances(self, tool):
        """Test filtering by running state."""
        mock_output = '{"Reservations": []}'
        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            with patch("sindri.tools.aws._run_aws", AsyncMock(return_value=(0, mock_output, ""))) as mock:
                result = await tool.execute(state="running")

        assert result.success is True
        call_args = mock.call_args[0]
        assert "--filters" in call_args
        assert "Name=instance-state-name,Values=running" in call_args

    @pytest.mark.asyncio
    async def test_list_json_output(self, tool):
        """Test JSON output format."""
        mock_output = '{"Reservations": []}'
        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            with patch("sindri.tools.aws._run_aws", AsyncMock(return_value=(0, mock_output, ""))):
                result = await tool.execute(output_format="json")

        assert result.success is True
        assert result.metadata["output_format"] == "json"

    @pytest.mark.asyncio
    async def test_list_failure(self, tool):
        """Test handling of EC2 API errors."""
        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            with patch("sindri.tools.aws._run_aws", AsyncMock(return_value=(1, "", "UnauthorizedOperation"))):
                result = await tool.execute()

        assert result.success is False
        assert "UnauthorizedOperation" in result.error


class TestAwsLambdaInvokeTool:
    """Tests for AwsLambdaInvokeTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        return AwsLambdaInvokeTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_cli_not_available(self, tool):
        """Test behavior when AWS CLI is not installed."""
        with patch("sindri.tools.aws.AWS_AVAILABLE", False):
            result = await tool.execute(function_name="my-function")
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_invoke_success(self, tool, tmp_path):
        """Test successful Lambda invocation."""
        mock_output = '{"StatusCode": 200}'
        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            with patch("sindri.tools.aws._run_aws", AsyncMock(return_value=(0, mock_output, ""))):
                # Mock the temp file reading
                with patch("pathlib.Path.read_text", return_value='{"result": "success"}'):
                    with patch("pathlib.Path.unlink"):
                        result = await tool.execute(function_name="my-function")

        assert result.success is True
        assert result.metadata["function_name"] == "my-function"
        assert result.metadata["status_code"] == 200

    @pytest.mark.asyncio
    async def test_invoke_with_payload(self, tool, tmp_path):
        """Test Lambda invocation with payload."""
        mock_output = '{"StatusCode": 200}'
        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            with patch("sindri.tools.aws._run_aws", AsyncMock(return_value=(0, mock_output, ""))) as mock:
                with patch("pathlib.Path.read_text", return_value='{}'):
                    with patch("pathlib.Path.unlink"):
                        result = await tool.execute(
                            function_name="my-function",
                            payload='{"key": "value"}'
                        )

        assert result.success is True
        call_args = mock.call_args[0]
        assert "--payload" in call_args

    @pytest.mark.asyncio
    async def test_invoke_async_type(self, tool, tmp_path):
        """Test async Lambda invocation."""
        mock_output = '{"StatusCode": 202}'
        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            with patch("sindri.tools.aws._run_aws", AsyncMock(return_value=(0, mock_output, ""))) as mock:
                with patch("pathlib.Path.read_text", return_value=''):
                    with patch("pathlib.Path.unlink"):
                        result = await tool.execute(
                            function_name="my-function",
                            invocation_type="async"
                        )

        assert result.success is True
        assert result.metadata["invocation_type"] == "async"
        call_args = mock.call_args[0]
        assert "--invocation-type" in call_args
        assert "Event" in call_args

    @pytest.mark.asyncio
    async def test_invoke_with_function_error(self, tool, tmp_path):
        """Test handling of Lambda function errors."""
        mock_output = '{"StatusCode": 200, "FunctionError": "Unhandled"}'
        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            with patch("sindri.tools.aws._run_aws", AsyncMock(return_value=(0, mock_output, ""))):
                with patch("pathlib.Path.read_text", return_value='{"errorMessage": "Error"}'):
                    with patch("pathlib.Path.unlink"):
                        result = await tool.execute(function_name="my-function")

        assert result.success is False
        assert result.metadata["has_error"] is True

    @pytest.mark.asyncio
    async def test_invoke_failure(self, tool):
        """Test handling of invocation errors."""
        with patch("sindri.tools.aws.AWS_AVAILABLE", True):
            with patch("sindri.tools.aws._run_aws", AsyncMock(return_value=(1, "", "Function not found"))):
                result = await tool.execute(function_name="nonexistent")

        assert result.success is False
        assert "Function not found" in result.error


class TestAwsToolRegistry:
    """Tests for AWS tool registration."""

    def test_tools_registered(self, tmp_path):
        """Test that all AWS tools are registered in the registry."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default(work_dir=tmp_path)

        # Check all AWS tools are registered
        aws_tools = [
            "aws_s3_list",
            "aws_s3_upload",
            "aws_s3_download",
            "aws_logs_query",
            "aws_ec2_list",
            "aws_lambda_invoke",
        ]

        for tool_name in aws_tools:
            assert registry.get_tool(tool_name) is not None, f"Tool {tool_name} not registered"


class TestTyrAgentRegistration:
    """Tests for Tyr agent registration."""

    def test_tyr_agent_exists(self):
        """Test that Tyr agent is defined in registry."""
        from sindri.agents.registry import AGENTS

        assert "tyr" in AGENTS

    def test_tyr_has_aws_tools(self):
        """Test that Tyr agent has AWS tools assigned."""
        from sindri.agents.registry import AGENTS

        tyr = AGENTS["tyr"]
        aws_tools = ["aws_s3_list", "aws_s3_upload", "aws_s3_download", "aws_logs_query", "aws_ec2_list", "aws_lambda_invoke"]
        for tool in aws_tools:
            assert tool in tyr.tools, f"Tyr missing AWS tool: {tool}"

    def test_tyr_has_k8s_tools(self):
        """Test that Tyr agent has Kubernetes tools assigned."""
        from sindri.agents.registry import AGENTS

        tyr = AGENTS["tyr"]
        k8s_tools = ["k8s_apply", "k8s_get_pods", "k8s_logs", "k8s_get_services", "k8s_describe", "k8s_delete"]
        for tool in k8s_tools:
            assert tool in tyr.tools, f"Tyr missing K8s tool: {tool}"

    def test_brokkr_can_delegate_to_tyr(self):
        """Test that Brokkr can delegate to Tyr."""
        from sindri.agents.registry import AGENTS

        brokkr = AGENTS["brokkr"]
        assert "tyr" in brokkr.delegate_to
