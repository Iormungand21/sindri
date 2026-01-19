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
