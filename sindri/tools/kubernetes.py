"""Kubernetes tools for Sindri.

Provides tools for interacting with Kubernetes clusters using kubectl.
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

# Check kubectl availability
KUBECTL_AVAILABLE = shutil.which("kubectl") is not None


async def _run_kubectl(
    *args: str,
    timeout: int = 300,
    input_data: str | None = None,
) -> tuple[int, str, str]:
    """Run a kubectl command asynchronously.

    Args:
        *args: kubectl command arguments (e.g., "get", "pods")
        timeout: Command timeout in seconds
        input_data: Optional stdin data (for apply -f -)

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    if not KUBECTL_AVAILABLE:
        return (-1, "", "kubectl not found. Please install kubectl.")

    cmd = ["kubectl"] + list(args)
    log.debug("kubectl_command", cmd=cmd)

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
        return (-1, "", f"kubectl command timed out after {timeout}s")
    except Exception as e:
        return (-1, "", f"kubectl command failed: {str(e)}")


class K8sApplyTool(Tool):
    """Apply Kubernetes manifest."""

    name = "k8s_apply"
    description = """Apply a Kubernetes manifest to create or update resources.

Examples:
- k8s_apply(manifest="deployment.yaml") - Apply from file
- k8s_apply(manifest="apiVersion: v1...", inline=true) - Apply inline YAML
- k8s_apply(manifest="deployment.yaml", namespace="production")
- k8s_apply(manifest="deployment.yaml", dry_run=true) - Preview changes"""

    parameters = {
        "type": "object",
        "properties": {
            "manifest": {
                "type": "string",
                "description": "Path to manifest file, or inline YAML if inline=true",
            },
            "namespace": {
                "type": "string",
                "description": "Kubernetes namespace. Default: 'default'",
            },
            "inline": {
                "type": "boolean",
                "description": "If true, treat manifest as inline YAML content. Default: false",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Perform a dry run without making changes. Default: false",
            },
        },
        "required": ["manifest"],
    }

    async def execute(
        self,
        manifest: str,
        namespace: str = "default",
        inline: bool = False,
        dry_run: bool = False,
        **kwargs,
    ) -> ToolResult:
        if not KUBECTL_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="kubectl not found. Please install kubectl.",
                suggestion="Install kubectl: https://kubernetes.io/docs/tasks/tools/",
            )

        args = ["apply"]

        if namespace:
            args.extend(["-n", namespace])

        if dry_run:
            args.append("--dry-run=client")

        input_data = None
        if inline:
            # Apply from stdin
            args.extend(["-f", "-"])
            input_data = manifest
        else:
            # Apply from file
            manifest_path = self._resolve_path(manifest)
            if not manifest_path.exists():
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Manifest file not found: {manifest_path}",
                )
            args.extend(["-f", str(manifest_path)])

        returncode, stdout, stderr = await _run_kubectl(*args, input_data=input_data)

        if returncode != 0:
            log.error("k8s_apply_failed", error=stderr)
            return ToolResult(
                success=False,
                output=stdout,
                error=f"Apply failed: {stderr}",
            )

        log.info("k8s_apply_completed", namespace=namespace, dry_run=dry_run)
        return ToolResult(
            success=True,
            output=stdout if stdout else "Resources applied successfully.",
            metadata={
                "namespace": namespace,
                "dry_run": dry_run,
                "inline": inline,
            },
        )


class K8sGetPodsTool(Tool):
    """List Kubernetes pods."""

    name = "k8s_get_pods"
    description = """List pods in a Kubernetes cluster.

Examples:
- k8s_get_pods() - List pods in default namespace
- k8s_get_pods(namespace="production") - List pods in specific namespace
- k8s_get_pods(all_namespaces=true) - List pods in all namespaces
- k8s_get_pods(selector="app=nginx") - Filter by label selector"""

    parameters = {
        "type": "object",
        "properties": {
            "namespace": {
                "type": "string",
                "description": "Kubernetes namespace. Default: 'default'",
            },
            "all_namespaces": {
                "type": "boolean",
                "description": "List pods across all namespaces. Default: false",
            },
            "selector": {
                "type": "string",
                "description": "Label selector (e.g., 'app=nginx,env=prod')",
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
        namespace: str = "default",
        all_namespaces: bool = False,
        selector: Optional[str] = None,
        output_format: str = "table",
        **kwargs,
    ) -> ToolResult:
        if not KUBECTL_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="kubectl not found. Please install kubectl.",
                suggestion="Install kubectl: https://kubernetes.io/docs/tasks/tools/",
            )

        args = ["get", "pods"]

        if all_namespaces:
            args.append("-A")
        elif namespace:
            args.extend(["-n", namespace])

        if selector:
            args.extend(["-l", selector])

        if output_format == "json":
            args.extend(["-o", "json"])

        returncode, stdout, stderr = await _run_kubectl(*args)

        if returncode != 0:
            log.error("k8s_get_pods_failed", error=stderr)
            return ToolResult(
                success=False,
                output="",
                error=f"Get pods failed: {stderr}",
            )

        # Count pods
        pod_count = 0
        if output_format == "json":
            try:
                data = json.loads(stdout)
                pod_count = len(data.get("items", []))
            except json.JSONDecodeError:
                pass
        else:
            lines = [l for l in stdout.strip().split("\n") if l.strip()]
            pod_count = max(0, len(lines) - 1)  # Subtract header

        log.info("k8s_get_pods_completed", namespace=namespace, pod_count=pod_count)
        return ToolResult(
            success=True,
            output=stdout if stdout.strip() else "No pods found.",
            metadata={
                "namespace": namespace if not all_namespaces else "all",
                "selector": selector,
                "pod_count": pod_count,
                "output_format": output_format,
            },
        )


class K8sLogsTool(Tool):
    """Get logs from a Kubernetes pod."""

    name = "k8s_logs"
    description = """Get logs from a Kubernetes pod.

Examples:
- k8s_logs(pod="nginx-pod") - Get logs from pod
- k8s_logs(pod="nginx-pod", container="nginx") - Get logs from specific container
- k8s_logs(pod="nginx-pod", tail=100) - Get last 100 lines
- k8s_logs(pod="nginx-pod", previous=true) - Get logs from previous container instance"""

    parameters = {
        "type": "object",
        "properties": {
            "pod": {
                "type": "string",
                "description": "Pod name",
            },
            "namespace": {
                "type": "string",
                "description": "Kubernetes namespace. Default: 'default'",
            },
            "container": {
                "type": "string",
                "description": "Container name (required for multi-container pods)",
            },
            "tail": {
                "type": "integer",
                "description": "Number of lines from end to show. Default: all",
            },
            "previous": {
                "type": "boolean",
                "description": "Get logs from previous container instance. Default: false",
            },
            "since": {
                "type": "string",
                "description": "Show logs since duration (e.g., '5m', '1h', '24h')",
            },
        },
        "required": ["pod"],
    }

    async def execute(
        self,
        pod: str,
        namespace: str = "default",
        container: Optional[str] = None,
        tail: Optional[int] = None,
        previous: bool = False,
        since: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        if not KUBECTL_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="kubectl not found. Please install kubectl.",
                suggestion="Install kubectl: https://kubernetes.io/docs/tasks/tools/",
            )

        args = ["logs", pod]

        if namespace:
            args.extend(["-n", namespace])

        if container:
            args.extend(["-c", container])

        if tail is not None:
            args.extend(["--tail", str(tail)])

        if previous:
            args.append("--previous")

        if since:
            args.extend(["--since", since])

        returncode, stdout, stderr = await _run_kubectl(*args)

        if returncode != 0:
            log.error("k8s_logs_failed", pod=pod, error=stderr)
            return ToolResult(
                success=False,
                output="",
                error=f"Get logs failed: {stderr}",
            )

        # Count lines
        line_count = len(stdout.strip().split("\n")) if stdout.strip() else 0

        log.info("k8s_logs_completed", pod=pod, line_count=line_count)
        return ToolResult(
            success=True,
            output=stdout if stdout.strip() else "No logs found.",
            metadata={
                "pod": pod,
                "namespace": namespace,
                "container": container,
                "line_count": line_count,
                "tail": tail,
            },
        )


class K8sGetServicesTool(Tool):
    """List Kubernetes services."""

    name = "k8s_get_services"
    description = """List services in a Kubernetes cluster.

Examples:
- k8s_get_services() - List services in default namespace
- k8s_get_services(namespace="production") - List services in specific namespace
- k8s_get_services(all_namespaces=true) - List services in all namespaces"""

    parameters = {
        "type": "object",
        "properties": {
            "namespace": {
                "type": "string",
                "description": "Kubernetes namespace. Default: 'default'",
            },
            "all_namespaces": {
                "type": "boolean",
                "description": "List services across all namespaces. Default: false",
            },
            "selector": {
                "type": "string",
                "description": "Label selector (e.g., 'app=nginx')",
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
        namespace: str = "default",
        all_namespaces: bool = False,
        selector: Optional[str] = None,
        output_format: str = "table",
        **kwargs,
    ) -> ToolResult:
        if not KUBECTL_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="kubectl not found. Please install kubectl.",
                suggestion="Install kubectl: https://kubernetes.io/docs/tasks/tools/",
            )

        args = ["get", "services"]

        if all_namespaces:
            args.append("-A")
        elif namespace:
            args.extend(["-n", namespace])

        if selector:
            args.extend(["-l", selector])

        if output_format == "json":
            args.extend(["-o", "json"])

        returncode, stdout, stderr = await _run_kubectl(*args)

        if returncode != 0:
            log.error("k8s_get_services_failed", error=stderr)
            return ToolResult(
                success=False,
                output="",
                error=f"Get services failed: {stderr}",
            )

        # Count services
        service_count = 0
        if output_format == "json":
            try:
                data = json.loads(stdout)
                service_count = len(data.get("items", []))
            except json.JSONDecodeError:
                pass
        else:
            lines = [l for l in stdout.strip().split("\n") if l.strip()]
            service_count = max(0, len(lines) - 1)  # Subtract header

        log.info("k8s_get_services_completed", namespace=namespace, service_count=service_count)
        return ToolResult(
            success=True,
            output=stdout if stdout.strip() else "No services found.",
            metadata={
                "namespace": namespace if not all_namespaces else "all",
                "selector": selector,
                "service_count": service_count,
                "output_format": output_format,
            },
        )


class K8sDescribeTool(Tool):
    """Describe a Kubernetes resource."""

    name = "k8s_describe"
    description = """Describe a Kubernetes resource in detail.

Examples:
- k8s_describe(resource_type="pod", name="nginx-pod")
- k8s_describe(resource_type="deployment", name="web-app", namespace="production")
- k8s_describe(resource_type="service", name="api-service")"""

    parameters = {
        "type": "object",
        "properties": {
            "resource_type": {
                "type": "string",
                "description": "Resource type (e.g., 'pod', 'deployment', 'service', 'node', 'configmap')",
            },
            "name": {
                "type": "string",
                "description": "Resource name",
            },
            "namespace": {
                "type": "string",
                "description": "Kubernetes namespace. Default: 'default'",
            },
        },
        "required": ["resource_type", "name"],
    }

    async def execute(
        self,
        resource_type: str,
        name: str,
        namespace: str = "default",
        **kwargs,
    ) -> ToolResult:
        if not KUBECTL_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="kubectl not found. Please install kubectl.",
                suggestion="Install kubectl: https://kubernetes.io/docs/tasks/tools/",
            )

        args = ["describe", resource_type, name]

        if namespace:
            args.extend(["-n", namespace])

        returncode, stdout, stderr = await _run_kubectl(*args)

        if returncode != 0:
            log.error("k8s_describe_failed", resource_type=resource_type, name=name, error=stderr)
            return ToolResult(
                success=False,
                output="",
                error=f"Describe failed: {stderr}",
            )

        log.info("k8s_describe_completed", resource_type=resource_type, name=name)
        return ToolResult(
            success=True,
            output=stdout,
            metadata={
                "resource_type": resource_type,
                "name": name,
                "namespace": namespace,
            },
        )


class K8sDeleteTool(Tool):
    """Delete a Kubernetes resource."""

    name = "k8s_delete"
    description = """Delete a Kubernetes resource.

Examples:
- k8s_delete(resource_type="pod", name="nginx-pod")
- k8s_delete(resource_type="deployment", name="web-app", namespace="production")
- k8s_delete(resource_type="pod", name="stuck-pod", force=true, grace_period=0)"""

    parameters = {
        "type": "object",
        "properties": {
            "resource_type": {
                "type": "string",
                "description": "Resource type (e.g., 'pod', 'deployment', 'service')",
            },
            "name": {
                "type": "string",
                "description": "Resource name",
            },
            "namespace": {
                "type": "string",
                "description": "Kubernetes namespace. Default: 'default'",
            },
            "force": {
                "type": "boolean",
                "description": "Force deletion. Default: false",
            },
            "grace_period": {
                "type": "integer",
                "description": "Grace period in seconds before force kill. Default: -1 (use default)",
            },
        },
        "required": ["resource_type", "name"],
    }

    async def execute(
        self,
        resource_type: str,
        name: str,
        namespace: str = "default",
        force: bool = False,
        grace_period: int = -1,
        **kwargs,
    ) -> ToolResult:
        if not KUBECTL_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="kubectl not found. Please install kubectl.",
                suggestion="Install kubectl: https://kubernetes.io/docs/tasks/tools/",
            )

        args = ["delete", resource_type, name]

        if namespace:
            args.extend(["-n", namespace])

        if force:
            args.append("--force")

        if grace_period >= 0:
            args.extend(["--grace-period", str(grace_period)])

        returncode, stdout, stderr = await _run_kubectl(*args)

        if returncode != 0:
            log.error("k8s_delete_failed", resource_type=resource_type, name=name, error=stderr)
            return ToolResult(
                success=False,
                output=stdout,
                error=f"Delete failed: {stderr}",
            )

        log.info("k8s_delete_completed", resource_type=resource_type, name=name)
        return ToolResult(
            success=True,
            output=stdout if stdout else f"{resource_type}/{name} deleted.",
            metadata={
                "resource_type": resource_type,
                "name": name,
                "namespace": namespace,
                "force": force,
                "grace_period": grace_period if grace_period >= 0 else "default",
            },
        )
