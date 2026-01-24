"""NotificationService for Triggers & Automations (ROADMAP Item 9).

Sends notifications to various targets (desktop, log, webhook) on trigger outcomes.
"""

import asyncio
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

from sindri.triggers.models import (
    NotificationHook,
    NotificationTarget,
    TriggerDefinition,
    TriggerRun,
)

log = structlog.get_logger()


class NotificationService:
    """Sends notifications for trigger outcomes."""

    def __init__(self, default_log_path: Optional[Path] = None):
        """Initialize notification service.

        Args:
            default_log_path: Default path for log notifications.
                              Defaults to ~/.sindri/triggers.log
        """
        self.default_log_path = default_log_path or (
            Path.home() / ".sindri" / "triggers.log"
        )

    async def notify(
        self, trigger: TriggerDefinition, run: TriggerRun
    ) -> list[dict]:
        """Send notifications based on trigger configuration.

        Args:
            trigger: The trigger definition
            run: The completed run

        Returns:
            List of notification results (target, success, error)
        """
        results = []

        for hook in trigger.notifications:
            should_notify = (
                (run.success and hook.on_success)
                or (not run.success and hook.on_failure)
            )
            if not should_notify:
                continue

            result = {"target": hook.target.value, "success": False, "error": None}

            try:
                if hook.target == NotificationTarget.DESKTOP:
                    await self._send_desktop(trigger, run, hook)
                    result["success"] = True
                elif hook.target == NotificationTarget.LOG:
                    await self._send_log(trigger, run, hook)
                    result["success"] = True
                elif hook.target == NotificationTarget.WEBHOOK:
                    await self._send_webhook(trigger, run, hook)
                    result["success"] = True
            except Exception as e:
                result["error"] = str(e)
                log.error(
                    "notification_failed",
                    target=hook.target.value,
                    trigger_id=trigger.id,
                    error=str(e),
                )

            results.append(result)

        return results

    async def _send_desktop(
        self, trigger: TriggerDefinition, run: TriggerRun, hook: NotificationHook
    ) -> None:
        """Send desktop notification via notify-send (Linux).

        Args:
            trigger: The trigger definition
            run: The completed run
            hook: The notification hook configuration
        """
        title = f"Sindri: {trigger.name}"
        status = "Success" if run.success else "Failed"
        body = f"{status}"
        if run.error:
            # Truncate long errors
            error_preview = run.error[:100]
            if len(run.error) > 100:
                error_preview += "..."
            body += f": {error_preview}"
        elif run.result_summary:
            summary_preview = run.result_summary[:100]
            if len(run.result_summary) > 100:
                summary_preview += "..."
            body += f"\n{summary_preview}"

        # Map urgency
        urgency = hook.urgency
        if urgency not in ("low", "normal", "critical"):
            urgency = "normal"

        # Run notify-send asynchronously
        try:
            proc = await asyncio.create_subprocess_exec(
                "notify-send",
                "-u", urgency,
                "-a", "Sindri",
                title,
                body,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()

            if proc.returncode != 0:
                stderr = await proc.stderr.read()
                raise RuntimeError(
                    f"notify-send failed: {stderr.decode().strip()}"
                )

            log.debug(
                "desktop_notification_sent",
                trigger_id=trigger.id,
                title=title,
            )

        except FileNotFoundError:
            # notify-send not available
            log.warning(
                "notify_send_not_available",
                trigger_id=trigger.id,
            )
            raise RuntimeError("notify-send not found; install libnotify")

    async def _send_log(
        self, trigger: TriggerDefinition, run: TriggerRun, hook: NotificationHook
    ) -> None:
        """Append notification to log file.

        Args:
            trigger: The trigger definition
            run: The completed run
            hook: The notification hook configuration
        """
        log_path = Path(hook.log_path) if hook.log_path else self.default_log_path

        # Ensure parent directory exists
        log_path.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trigger_id": trigger.id,
            "trigger_name": trigger.name,
            "run_id": run.id,
            "task_id": run.task_id,
            "success": run.success,
            "error": run.error,
            "result_summary": run.result_summary,
            "duration_ms": run.duration_ms,
        }

        # Write to file (use sync I/O since it's a single line append)
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

        log.debug(
            "log_notification_written",
            trigger_id=trigger.id,
            log_path=str(log_path),
        )

    async def _send_webhook(
        self, trigger: TriggerDefinition, run: TriggerRun, hook: NotificationHook
    ) -> None:
        """Send outbound webhook notification.

        Args:
            trigger: The trigger definition
            run: The completed run
            hook: The notification hook configuration
        """
        if not hook.webhook_url:
            raise ValueError("webhook_url is required for webhook notifications")

        try:
            import httpx
        except ImportError:
            raise RuntimeError("httpx not installed for webhook notifications")

        payload = {
            "event": "trigger_run_completed",
            "trigger": {
                "id": trigger.id,
                "name": trigger.name,
                "type": trigger.trigger_type.value,
            },
            "run": {
                "id": run.id,
                "task_id": run.task_id,
                "success": run.success,
                "error": run.error,
                "result_summary": run.result_summary,
                "duration_ms": run.duration_ms,
                "started_at": run.started_at.isoformat(),
                "completed_at": (
                    run.completed_at.isoformat() if run.completed_at else None
                ),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                hook.webhook_url,
                json=payload,
                headers=hook.webhook_headers,
                timeout=10.0,
            )

            if response.status_code >= 400:
                raise RuntimeError(
                    f"Webhook failed with status {response.status_code}: "
                    f"{response.text[:200]}"
                )

        log.debug(
            "webhook_notification_sent",
            trigger_id=trigger.id,
            webhook_url=hook.webhook_url,
            status_code=response.status_code,
        )

    async def send_test_notification(
        self, target: NotificationTarget, **kwargs
    ) -> bool:
        """Send a test notification to verify configuration.

        Args:
            target: The notification target to test
            **kwargs: Target-specific settings (log_path, webhook_url, etc.)

        Returns:
            True if successful
        """
        # Create mock trigger and run for testing
        from sindri.triggers.models import TriggerType, TriggerStatus

        mock_trigger = TriggerDefinition(
            name="Test Notification",
            trigger_type=TriggerType.CRON,
            task_description="Test task",
        )

        mock_run = TriggerRun(
            trigger_id=mock_trigger.id,
            trigger_name=mock_trigger.name,
            success=True,
            result_summary="This is a test notification from Sindri.",
            duration_ms=100.0,
            completed_at=datetime.now(timezone.utc),
        )

        hook = NotificationHook(
            target=target,
            on_success=True,
            on_failure=True,
            **kwargs,
        )

        if target == NotificationTarget.DESKTOP:
            await self._send_desktop(mock_trigger, mock_run, hook)
        elif target == NotificationTarget.LOG:
            await self._send_log(mock_trigger, mock_run, hook)
        elif target == NotificationTarget.WEBHOOK:
            await self._send_webhook(mock_trigger, mock_run, hook)

        return True
