"""AWS tools for Sindri.

Provides tools for interacting with AWS services including S3, CloudWatch Logs,
EC2, and Lambda. Uses the AWS CLI for all operations.
"""

import asyncio
import json
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()

# Check AWS CLI availability
AWS_AVAILABLE = shutil.which("aws") is not None


async def _run_aws(
    *args: str,
    timeout: int = 300,
    input_data: str | None = None,
) -> tuple[int, str, str]:
    """Run an AWS CLI command asynchronously.

    Args:
        *args: AWS CLI command arguments (e.g., "s3", "ls")
        timeout: Command timeout in seconds
        input_data: Optional stdin data

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    if not AWS_AVAILABLE:
        return (-1, "", "AWS CLI not found. Please install: pip install awscli")

    cmd = ["aws"] + list(args)
    log.debug("aws_command", cmd=cmd)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if input_data else None,
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input_data.encode() if input_data else None),
            timeout=timeout,
        )

        return (proc.returncode or 0, stdout.decode(), stderr.decode())
    except asyncio.TimeoutError:
        return (-1, "", f"AWS command timed out after {timeout}s")
    except Exception as e:
        return (-1, "", f"AWS command failed: {str(e)}")


class AwsS3ListTool(Tool):
    """List S3 buckets or objects in a bucket."""

    name = "aws_s3_list"
    description = """List S3 buckets or objects in a bucket.

Examples:
- aws_s3_list() - List all buckets
- aws_s3_list(bucket="mybucket") - List objects in bucket
- aws_s3_list(bucket="mybucket", prefix="logs/") - List objects with prefix
- aws_s3_list(bucket="mybucket", recursive=true) - List all objects recursively"""

    parameters = {
        "type": "object",
        "properties": {
            "bucket": {
                "type": "string",
                "description": "S3 bucket name. If not specified, lists all buckets.",
            },
            "prefix": {
                "type": "string",
                "description": "Object key prefix to filter results (e.g., 'logs/')",
            },
            "recursive": {
                "type": "boolean",
                "description": "List objects recursively. Default: false",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        bucket: Optional[str] = None,
        prefix: str = "",
        recursive: bool = False,
        **kwargs,
    ) -> ToolResult:
        if not AWS_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="AWS CLI not found. Please install: pip install awscli",
                suggestion="Install AWS CLI: pip install awscli && aws configure",
            )

        args = ["s3", "ls"]

        if bucket:
            s3_path = f"s3://{bucket}"
            if prefix:
                s3_path = f"{s3_path}/{prefix.lstrip('/')}"
            args.append(s3_path)

        if recursive:
            args.append("--recursive")

        returncode, stdout, stderr = await _run_aws(*args)

        if returncode != 0:
            log.error("aws_s3_list_failed", error=stderr)
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to list S3: {stderr}",
            )

        # Count items
        lines = [l for l in stdout.strip().split("\n") if l.strip()]
        item_count = len(lines)

        log.info("aws_s3_list_completed", bucket=bucket, item_count=item_count)
        return ToolResult(
            success=True,
            output=stdout if stdout.strip() else "No items found.",
            metadata={
                "bucket": bucket,
                "prefix": prefix,
                "recursive": recursive,
                "item_count": item_count,
            },
        )


class AwsS3UploadTool(Tool):
    """Upload files to S3."""

    name = "aws_s3_upload"
    description = """Upload files or directories to S3.

Examples:
- aws_s3_upload(source="file.txt", destination="s3://mybucket/file.txt")
- aws_s3_upload(source="./data/", destination="s3://mybucket/data/", recursive=true)"""

    parameters = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "Local file or directory path to upload",
            },
            "destination": {
                "type": "string",
                "description": "S3 destination (e.g., 's3://mybucket/path/file.txt')",
            },
            "recursive": {
                "type": "boolean",
                "description": "Upload directory recursively. Default: false",
            },
        },
        "required": ["source", "destination"],
    }

    async def execute(
        self,
        source: str,
        destination: str,
        recursive: bool = False,
        **kwargs,
    ) -> ToolResult:
        if not AWS_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="AWS CLI not found. Please install: pip install awscli",
                suggestion="Install AWS CLI: pip install awscli && aws configure",
            )

        source_path = self._resolve_path(source)
        if not source_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Source path not found: {source_path}",
            )

        # Ensure destination starts with s3://
        if not destination.startswith("s3://"):
            destination = f"s3://{destination}"

        args = ["s3", "cp", str(source_path), destination]
        if recursive:
            args.append("--recursive")

        returncode, stdout, stderr = await _run_aws(*args, timeout=600)

        if returncode != 0:
            log.error("aws_s3_upload_failed", source=str(source_path), error=stderr)
            return ToolResult(
                success=False,
                output=stdout,
                error=f"Upload failed: {stderr}",
            )

        log.info("aws_s3_upload_completed", source=str(source_path), destination=destination)
        return ToolResult(
            success=True,
            output=f"Uploaded {source_path} to {destination}\n\n{stdout}",
            metadata={
                "source": str(source_path),
                "destination": destination,
                "recursive": recursive,
            },
        )


class AwsS3DownloadTool(Tool):
    """Download files from S3."""

    name = "aws_s3_download"
    description = """Download files or directories from S3.

Examples:
- aws_s3_download(source="s3://mybucket/file.txt", destination="./file.txt")
- aws_s3_download(source="s3://mybucket/data/", destination="./data/", recursive=true)"""

    parameters = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "S3 source (e.g., 's3://mybucket/path/file.txt')",
            },
            "destination": {
                "type": "string",
                "description": "Local destination path",
            },
            "recursive": {
                "type": "boolean",
                "description": "Download directory recursively. Default: false",
            },
        },
        "required": ["source", "destination"],
    }

    async def execute(
        self,
        source: str,
        destination: str,
        recursive: bool = False,
        **kwargs,
    ) -> ToolResult:
        if not AWS_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="AWS CLI not found. Please install: pip install awscli",
                suggestion="Install AWS CLI: pip install awscli && aws configure",
            )

        # Ensure source starts with s3://
        if not source.startswith("s3://"):
            source = f"s3://{source}"

        dest_path = self._resolve_path(destination)

        args = ["s3", "cp", source, str(dest_path)]
        if recursive:
            args.append("--recursive")

        returncode, stdout, stderr = await _run_aws(*args, timeout=600)

        if returncode != 0:
            log.error("aws_s3_download_failed", source=source, error=stderr)
            return ToolResult(
                success=False,
                output=stdout,
                error=f"Download failed: {stderr}",
            )

        log.info("aws_s3_download_completed", source=source, destination=str(dest_path))
        return ToolResult(
            success=True,
            output=f"Downloaded {source} to {dest_path}\n\n{stdout}",
            metadata={
                "source": source,
                "destination": str(dest_path),
                "recursive": recursive,
            },
        )


class AwsLogsQueryTool(Tool):
    """Query CloudWatch Logs."""

    name = "aws_logs_query"
    description = """Query CloudWatch Logs for log events.

Examples:
- aws_logs_query(log_group="/aws/lambda/myfunction")
- aws_logs_query(log_group="/aws/lambda/myfunction", filter_pattern="ERROR")
- aws_logs_query(log_group="/aws/lambda/myfunction", start_time="1h", limit=100)"""

    parameters = {
        "type": "object",
        "properties": {
            "log_group": {
                "type": "string",
                "description": "CloudWatch Log group name (e.g., '/aws/lambda/myfunction')",
            },
            "filter_pattern": {
                "type": "string",
                "description": "Filter pattern to search for (e.g., 'ERROR', 'status=500')",
            },
            "start_time": {
                "type": "string",
                "description": "Start time: Unix timestamp (ms), ISO date, or relative (e.g., '1h', '30m', '1d'). Default: 1h",
            },
            "end_time": {
                "type": "string",
                "description": "End time: Unix timestamp (ms), ISO date, or 'now'. Default: now",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of events to return. Default: 50",
            },
        },
        "required": ["log_group"],
    }

    async def execute(
        self,
        log_group: str,
        filter_pattern: Optional[str] = None,
        start_time: str = "1h",
        end_time: str = "now",
        limit: int = 50,
        **kwargs,
    ) -> ToolResult:
        if not AWS_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="AWS CLI not found. Please install: pip install awscli",
                suggestion="Install AWS CLI: pip install awscli && aws configure",
            )

        args = [
            "logs",
            "filter-log-events",
            "--log-group-name",
            log_group,
            "--limit",
            str(limit),
        ]

        # Handle relative time
        import time

        now_ms = int(time.time() * 1000)

        def parse_time(t: str) -> int:
            if t == "now":
                return now_ms
            if t.endswith("h"):
                return now_ms - int(t[:-1]) * 3600 * 1000
            if t.endswith("m"):
                return now_ms - int(t[:-1]) * 60 * 1000
            if t.endswith("d"):
                return now_ms - int(t[:-1]) * 86400 * 1000
            # Assume it's already a timestamp
            return int(t)

        try:
            start_ms = parse_time(start_time)
            end_ms = parse_time(end_time)
            args.extend(["--start-time", str(start_ms), "--end-time", str(end_ms)])
        except ValueError:
            pass  # Skip time args if parsing fails

        if filter_pattern:
            args.extend(["--filter-pattern", filter_pattern])

        returncode, stdout, stderr = await _run_aws(*args)

        if returncode != 0:
            log.error("aws_logs_query_failed", log_group=log_group, error=stderr)
            return ToolResult(
                success=False,
                output="",
                error=f"Log query failed: {stderr}",
            )

        # Parse JSON output
        try:
            result = json.loads(stdout)
            events = result.get("events", [])
            event_count = len(events)

            # Format output
            output_lines = []
            for event in events:
                ts = event.get("timestamp", "")
                msg = event.get("message", "").strip()
                output_lines.append(f"[{ts}] {msg}")

            formatted_output = "\n".join(output_lines) if output_lines else "No events found."
        except json.JSONDecodeError:
            formatted_output = stdout
            event_count = 0

        log.info("aws_logs_query_completed", log_group=log_group, event_count=event_count)
        return ToolResult(
            success=True,
            output=formatted_output,
            metadata={
                "log_group": log_group,
                "filter_pattern": filter_pattern,
                "event_count": event_count,
                "limit": limit,
            },
        )


class AwsEc2ListTool(Tool):
    """List EC2 instances."""

    name = "aws_ec2_list"
    description = """List EC2 instances with filtering options.

Examples:
- aws_ec2_list() - List all instances
- aws_ec2_list(state="running") - List running instances only
- aws_ec2_list(filters={"tag:Environment": "production"})"""

    parameters = {
        "type": "object",
        "properties": {
            "state": {
                "type": "string",
                "description": "Filter by instance state: 'running', 'stopped', 'all'. Default: 'all'",
                "enum": ["running", "stopped", "all"],
            },
            "filters": {
                "type": "object",
                "description": "Additional filters as key-value pairs (e.g., {'tag:Name': 'web-*'})",
            },
            "output_format": {
                "type": "string",
                "description": "Output format: 'table' or 'json'. Default: 'table'",
                "enum": ["table", "json"],
            },
        },
        "required": [],
    }

    async def execute(
        self,
        state: str = "all",
        filters: Optional[dict] = None,
        output_format: str = "table",
        **kwargs,
    ) -> ToolResult:
        if not AWS_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="AWS CLI not found. Please install: pip install awscli",
                suggestion="Install AWS CLI: pip install awscli && aws configure",
            )

        args = ["ec2", "describe-instances"]

        # Build filters
        filter_args = []
        if state != "all":
            filter_args.append(f"Name=instance-state-name,Values={state}")
        if filters:
            for key, value in filters.items():
                filter_args.append(f"Name={key},Values={value}")

        if filter_args:
            args.extend(["--filters"] + filter_args)

        args.extend(["--output", "json"])

        returncode, stdout, stderr = await _run_aws(*args)

        if returncode != 0:
            log.error("aws_ec2_list_failed", error=stderr)
            return ToolResult(
                success=False,
                output="",
                error=f"EC2 list failed: {stderr}",
            )

        # Parse and format output
        try:
            data = json.loads(stdout)
            instances = []
            for reservation in data.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    inst_info = {
                        "InstanceId": instance.get("InstanceId"),
                        "InstanceType": instance.get("InstanceType"),
                        "State": instance.get("State", {}).get("Name"),
                        "PublicIp": instance.get("PublicIpAddress", "N/A"),
                        "PrivateIp": instance.get("PrivateIpAddress", "N/A"),
                    }
                    # Get Name tag
                    for tag in instance.get("Tags", []):
                        if tag.get("Key") == "Name":
                            inst_info["Name"] = tag.get("Value")
                            break
                    instances.append(inst_info)

            instance_count = len(instances)

            if output_format == "json":
                formatted_output = json.dumps(instances, indent=2)
            else:
                # Table format
                if instances:
                    lines = ["ID\tType\tState\tPublic IP\tName"]
                    for inst in instances:
                        lines.append(
                            f"{inst.get('InstanceId')}\t{inst.get('InstanceType')}\t"
                            f"{inst.get('State')}\t{inst.get('PublicIp')}\t"
                            f"{inst.get('Name', 'N/A')}"
                        )
                    formatted_output = "\n".join(lines)
                else:
                    formatted_output = "No instances found."
        except json.JSONDecodeError:
            formatted_output = stdout
            instance_count = 0

        log.info("aws_ec2_list_completed", instance_count=instance_count)
        return ToolResult(
            success=True,
            output=formatted_output,
            metadata={
                "state_filter": state,
                "instance_count": instance_count,
                "output_format": output_format,
            },
        )


class AwsLambdaInvokeTool(Tool):
    """Invoke an AWS Lambda function."""

    name = "aws_lambda_invoke"
    description = """Invoke an AWS Lambda function.

Examples:
- aws_lambda_invoke(function_name="my-function")
- aws_lambda_invoke(function_name="my-function", payload='{"key": "value"}')
- aws_lambda_invoke(function_name="my-function", invocation_type="async")"""

    parameters = {
        "type": "object",
        "properties": {
            "function_name": {
                "type": "string",
                "description": "Lambda function name or ARN",
            },
            "payload": {
                "type": "string",
                "description": "JSON payload to send to the function",
            },
            "invocation_type": {
                "type": "string",
                "description": "Invocation type: 'sync' (RequestResponse), 'async' (Event), 'dry_run' (DryRun). Default: 'sync'",
                "enum": ["sync", "async", "dry_run"],
            },
            "log_type": {
                "type": "string",
                "description": "Log type: 'Tail' to include execution logs, 'None' to skip. Default: 'Tail'",
                "enum": ["Tail", "None"],
            },
        },
        "required": ["function_name"],
    }

    async def execute(
        self,
        function_name: str,
        payload: Optional[str] = None,
        invocation_type: str = "sync",
        log_type: str = "Tail",
        **kwargs,
    ) -> ToolResult:
        if not AWS_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="AWS CLI not found. Please install: pip install awscli",
                suggestion="Install AWS CLI: pip install awscli && aws configure",
            )

        # Map invocation type
        inv_type_map = {
            "sync": "RequestResponse",
            "async": "Event",
            "dry_run": "DryRun",
        }
        aws_invocation_type = inv_type_map.get(invocation_type, "RequestResponse")

        # Create temp file for response
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            output_file = f.name

        try:
            args = [
                "lambda",
                "invoke",
                "--function-name",
                function_name,
                "--invocation-type",
                aws_invocation_type,
                "--log-type",
                log_type,
                output_file,
            ]

            if payload:
                args.extend(["--payload", payload])

            returncode, stdout, stderr = await _run_aws(*args)

            if returncode != 0:
                log.error("aws_lambda_invoke_failed", function=function_name, error=stderr)
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Lambda invocation failed: {stderr}",
                )

            # Read response from output file
            response_content = ""
            try:
                response_content = Path(output_file).read_text()
            except Exception:
                pass

            # Parse invoke metadata
            try:
                metadata = json.loads(stdout)
                status_code = metadata.get("StatusCode", 0)
                function_error = metadata.get("FunctionError")
                log_result = metadata.get("LogResult", "")

                # Decode base64 logs if present
                if log_result:
                    import base64

                    try:
                        log_result = base64.b64decode(log_result).decode()
                    except Exception:
                        pass
            except json.JSONDecodeError:
                status_code = 0
                function_error = None
                log_result = ""

            # Format output
            output_parts = [f"Status Code: {status_code}"]
            if function_error:
                output_parts.append(f"Function Error: {function_error}")
            if response_content:
                output_parts.append(f"\nResponse:\n{response_content}")
            if log_result:
                output_parts.append(f"\nLogs:\n{log_result}")

            formatted_output = "\n".join(output_parts)

            success = returncode == 0 and not function_error

            log.info(
                "aws_lambda_invoke_completed",
                function=function_name,
                status_code=status_code,
                success=success,
            )
            return ToolResult(
                success=success,
                output=formatted_output,
                error=f"Function error: {function_error}" if function_error else None,
                metadata={
                    "function_name": function_name,
                    "status_code": status_code,
                    "invocation_type": invocation_type,
                    "has_error": bool(function_error),
                },
            )
        finally:
            # Clean up temp file
            try:
                Path(output_file).unlink()
            except Exception:
                pass
