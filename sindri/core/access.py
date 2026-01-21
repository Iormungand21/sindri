"""System access control utilities for Sindri.

This module provides access checking and confirmation mechanisms for
system operations, supporting the graduated access levels introduced
in Milestone 5 of the architecture transformation.

Access Levels:
- RESTRICTED: Read-only system info, no modifications
- SUPERVISED: Can modify with confirmation prompts
- FULL: Full autonomous access (for dedicated machine)
"""

from dataclasses import dataclass
from typing import Optional

import click
from rich.console import Console

from sindri.config import SindriConfig, SystemAccessLevel


@dataclass
class AccessCheckResult:
    """Result of an access check.

    Attributes:
        allowed: Whether the operation is allowed
        reason: Human-readable explanation of the decision
        needs_confirmation: Whether the operation requires user confirmation
    """

    allowed: bool
    reason: str
    needs_confirmation: bool = False


def check_system_access(
    config: SindriConfig,
    operation: str,
    service: Optional[str] = None,
    is_modification: bool = False,
) -> AccessCheckResult:
    """Check if an operation is allowed under current access level.

    Args:
        config: Sindri configuration with access settings
        operation: Description of the operation being attempted
        service: Optional service name (e.g., "ollama", "nginx")
        is_modification: Whether the operation modifies system state

    Returns:
        AccessCheckResult with allowed status and reason

    Examples:
        >>> config = SindriConfig(system_access=SystemAccessLevel.RESTRICTED)
        >>> result = check_system_access(config, "restart service", is_modification=True)
        >>> result.allowed
        False

        >>> config = SindriConfig(system_access=SystemAccessLevel.SUPERVISED)
        >>> result = check_system_access(config, "restart ollama", service="ollama", is_modification=True)
        >>> result.needs_confirmation
        True
    """
    level = config.system_access

    # RESTRICTED: Only read operations allowed
    if level == SystemAccessLevel.RESTRICTED:
        if is_modification:
            return AccessCheckResult(
                allowed=False,
                reason=f"System access level is RESTRICTED. Cannot perform: {operation}",
            )
        return AccessCheckResult(allowed=True, reason="Read operation allowed")

    # Check service whitelist for non-restricted modes
    if service and service not in config.allowed_services:
        return AccessCheckResult(
            allowed=False,
            reason=f"Service '{service}' not in allowed_services list. "
            f"Allowed: {', '.join(config.allowed_services)}",
        )

    # SUPERVISED: Modifications require confirmation
    if level == SystemAccessLevel.SUPERVISED and is_modification:
        return AccessCheckResult(
            allowed=True,
            reason="Supervised mode - confirmation required",
            needs_confirmation=True,
        )

    # FULL: All operations allowed
    return AccessCheckResult(allowed=True, reason="Full access granted")


def check_tool_permission(
    config: SindriConfig,
    tool_name: str,
) -> AccessCheckResult:
    """Check if a tool is allowed by the current configuration.

    This function checks tool permissions based on allowlists and blocklists
    configured in SindriConfig. The check order is:
    1. If allowed_tools is set, tool must be in the list
    2. If tool is in blocked_tools, it is rejected
    3. If tool is in tool_approval_required, it needs confirmation

    Args:
        config: Sindri configuration with tool permission settings
        tool_name: Name of the tool to check

    Returns:
        AccessCheckResult with allowed status and reason

    Examples:
        >>> config = SindriConfig(allowed_tools=["read_file", "write_file"])
        >>> result = check_tool_permission(config, "shell")
        >>> result.allowed
        False

        >>> config = SindriConfig(blocked_tools=["shell"])
        >>> result = check_tool_permission(config, "shell")
        >>> result.allowed
        False

        >>> config = SindriConfig(tool_approval_required=["write_file"])
        >>> result = check_tool_permission(config, "write_file")
        >>> result.needs_confirmation
        True
    """
    # Check allowlist (if set)
    if config.allowed_tools is not None:
        if tool_name not in config.allowed_tools:
            return AccessCheckResult(
                allowed=False,
                reason=f"Tool '{tool_name}' not in allowed_tools list",
            )

    # Check blocklist
    if tool_name in config.blocked_tools:
        return AccessCheckResult(
            allowed=False,
            reason=f"Tool '{tool_name}' is blocked",
        )

    # Check if approval required
    needs_approval = tool_name in config.tool_approval_required

    if needs_approval:
        return AccessCheckResult(
            allowed=True,
            needs_confirmation=True,
            reason=f"Tool '{tool_name}' requires approval",
        )

    return AccessCheckResult(
        allowed=True,
        reason="Tool allowed",
    )


def confirm_operation(operation: str, details: str = "") -> bool:
    """Prompt user to confirm a supervised operation.

    Args:
        operation: Description of the operation
        details: Optional additional details to display

    Returns:
        True if user confirmed, False otherwise
    """
    console = Console()

    console.print()
    console.print("[yellow]Supervised Mode - Confirmation Required[/yellow]")
    console.print(f"[bold]Operation:[/bold] {operation}")
    if details:
        console.print(f"[dim]{details}[/dim]")
    console.print()

    return click.confirm("Proceed?", default=False)


def check_and_confirm(
    config: SindriConfig,
    operation: str,
    service: Optional[str] = None,
    is_modification: bool = False,
    details: str = "",
) -> AccessCheckResult:
    """Check access and prompt for confirmation if needed.

    This is a convenience function that combines check_system_access
    and confirm_operation. If the operation requires confirmation,
    it will prompt the user and return the updated result.

    Args:
        config: Sindri configuration with access settings
        operation: Description of the operation being attempted
        service: Optional service name
        is_modification: Whether the operation modifies system state
        details: Optional additional details for confirmation prompt

    Returns:
        AccessCheckResult with final allowed status
    """
    result = check_system_access(config, operation, service, is_modification)

    if not result.allowed:
        return result

    if result.needs_confirmation:
        if confirm_operation(operation, details):
            return AccessCheckResult(
                allowed=True,
                reason="User confirmed operation",
                needs_confirmation=False,
            )
        else:
            return AccessCheckResult(
                allowed=False,
                reason="User cancelled operation",
                needs_confirmation=False,
            )

    return result


def can_modify_self(config: SindriConfig) -> AccessCheckResult:
    """Check if Sindri can modify its own configuration.

    Args:
        config: Sindri configuration

    Returns:
        AccessCheckResult indicating if self-modification is allowed
    """
    if not config.allow_self_modification:
        return AccessCheckResult(
            allowed=False,
            reason="Self-modification is disabled in config. "
            "Set allow_self_modification=true to enable.",
        )

    # Check base access level
    if config.system_access == SystemAccessLevel.RESTRICTED:
        return AccessCheckResult(
            allowed=False,
            reason="Cannot modify config in RESTRICTED access mode",
        )

    if config.system_access == SystemAccessLevel.SUPERVISED:
        return AccessCheckResult(
            allowed=True,
            reason="Self-modification allowed with confirmation",
            needs_confirmation=True,
        )

    return AccessCheckResult(
        allowed=True,
        reason="Self-modification allowed in FULL access mode",
    )
