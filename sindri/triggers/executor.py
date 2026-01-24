"""TriggerExecutor for Triggers & Automations (ROADMAP Item 9).

Executes tasks when triggers fire, creating orchestrator sessions
and recording run history.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import structlog

from sindri.core.events import EventBus, Event, EventType
from sindri.triggers.models import TriggerDefinition, TriggerRun
from sindri.triggers.notifications import NotificationService
from sindri.triggers.store import TriggerStore

log = structlog.get_logger()


class TriggerExecutor:
    """Executes tasks triggered by triggers."""

    def __init__(
        self,
        store: TriggerStore,
        notification_service: Optional[NotificationService] = None,
        event_bus: Optional[EventBus] = None,
        vram_gb: float = 16.0,
    ):
        """Initialize trigger executor.

        Args:
            store: TriggerStore for persistence
            notification_service: NotificationService for notifications
            event_bus: EventBus for emitting events
            vram_gb: Total VRAM available for task execution
        """
        self.store = store
        self.notifications = notification_service or NotificationService()
        self.event_bus = event_bus
        self.vram_gb = vram_gb

    async def execute_trigger(
        self,
        trigger: TriggerDefinition,
        context: Optional[dict[str, Any]] = None,
    ) -> TriggerRun:
        """Execute a trigger by creating and running a task.

        Args:
            trigger: The trigger to execute
            context: Optional context (webhook payload, event data, etc.)

        Returns:
            The TriggerRun record
        """
        run = TriggerRun(
            trigger_id=trigger.id,
            trigger_name=trigger.name,
        )

        start_time = time.time()

        # Emit TRIGGER_STARTED event
        self._emit_event(
            EventType.TRIGGER_STARTED,
            {
                "trigger_id": trigger.id,
                "trigger_name": trigger.name,
                "trigger_type": trigger.trigger_type.value,
                "run_id": run.id,
            },
        )

        log.info(
            "trigger_execution_started",
            trigger_id=trigger.id,
            trigger_name=trigger.name,
            run_id=run.id,
        )

        try:
            # Import orchestrator lazily to avoid circular imports
            from sindri.core.orchestrator import Orchestrator
            from sindri.core.loop import LoopConfig

            # Build task description with context
            task_description = trigger.task_description
            if context:
                task_description += f"\n\n--- Trigger Context ---\n{json.dumps(context, indent=2)}"

            # Configure the orchestrator
            config = LoopConfig(max_iterations=trigger.max_iterations)
            work_dir = Path(trigger.work_dir) if trigger.work_dir else None

            orchestrator = Orchestrator(
                config=config,
                total_vram_gb=self.vram_gb,
                enable_memory=True,
                work_dir=work_dir,
                event_bus=self.event_bus,
            )

            # Run the task with the trigger's specified agent
            result = await orchestrator.run(
                task_description, root_agent=trigger.agent
            )

            # Extract result data
            run.task_id = result.get("task_id")
            run.session_id = result.get("session_id")
            run.success = result.get("success", False)
            # Normalize result to string (may be dict or other type)
            raw_result = result.get("result", "")
            if not isinstance(raw_result, str):
                raw_result = json.dumps(raw_result)
            run.result_summary = self._truncate(raw_result, 500)
            run.error = result.get("error")

        except Exception as e:
            log.error(
                "trigger_execution_failed",
                trigger_id=trigger.id,
                error=str(e),
            )
            run.success = False
            run.error = str(e)

        # Complete the run
        run.completed_at = datetime.now(timezone.utc)
        run.duration_ms = (time.time() - start_time) * 1000

        # Update context if provided
        if context:
            if "webhook_payload" in context:
                run.webhook_payload = context["webhook_payload"]
            if "webhook_headers" in context:
                run.webhook_headers = context["webhook_headers"]
            if "event_type" in context:
                run.event_type = context["event_type"]
            if "event_data" in context:
                run.event_data = context["event_data"]

        # Save run record
        await self.store.save_run(run)

        # Update trigger stats
        await self.store.increment_run_count(
            trigger.id, run.success, run.started_at
        )

        # Send notifications
        try:
            await self.notifications.notify(trigger, run)
        except Exception as e:
            log.warning(
                "notification_dispatch_failed",
                trigger_id=trigger.id,
                error=str(e),
            )

        # Emit completion event
        event_type = (
            EventType.TRIGGER_COMPLETED if run.success else EventType.TRIGGER_FAILED
        )
        self._emit_event(
            event_type,
            {
                "trigger_id": trigger.id,
                "trigger_name": trigger.name,
                "run_id": run.id,
                "task_id": run.task_id,
                "success": run.success,
                "error": run.error,
                "duration_ms": run.duration_ms,
            },
        )

        log.info(
            "trigger_execution_completed",
            trigger_id=trigger.id,
            trigger_name=trigger.name,
            run_id=run.id,
            success=run.success,
            duration_ms=run.duration_ms,
        )

        return run

    async def execute_trigger_by_id(
        self,
        trigger_id: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Optional[TriggerRun]:
        """Execute a trigger by its ID.

        Args:
            trigger_id: The trigger ID
            context: Optional context

        Returns:
            The TriggerRun record, or None if trigger not found
        """
        trigger = await self.store.load_trigger(trigger_id)
        if not trigger:
            log.warning("trigger_not_found", trigger_id=trigger_id)
            return None

        return await self.execute_trigger(trigger, context)

    def _emit_event(self, event_type: EventType, data: dict) -> None:
        """Emit an event if event bus is available."""
        if self.event_bus:
            try:
                self.event_bus.emit(
                    Event(type=event_type, data=data, timestamp=time.time())
                )
            except Exception as e:
                log.warning("event_emit_failed", error=str(e))

    def _truncate(self, text: str, max_length: int) -> str:
        """Truncate text to max length with ellipsis."""
        if not text:
            return ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."
