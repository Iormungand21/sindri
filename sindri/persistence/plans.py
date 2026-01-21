"""Plan persistence for Plan-First Execution.

This module provides SQLite storage for execution plans and their steps,
supporting the Plan-First Execution feature (ROADMAP.md Item 2).
"""

import json
from datetime import datetime
from typing import Optional
import aiosqlite
import structlog

from sindri.persistence.database import Database
from sindri.core.plan_execution import (
    PersistentPlan,
    PersistentPlanStep,
    PlanStatus,
    StepStatus,
    StepCheckpoint,
    StepResult,
    ApprovalStatus,
)

log = structlog.get_logger()


class PlanStore:
    """Manages persistence of execution plans and steps to SQLite."""

    def __init__(self, database: Optional[Database] = None):
        """Initialize plan store.

        Args:
            database: Database instance (uses default if not provided)
        """
        self.db = database or Database()

    def _get_connection(self):
        """Get an async database connection context manager."""
        return self.db.get_connection()

    # ============== Plan CRUD ==============

    async def save_plan(self, plan: PersistentPlan) -> str:
        """Save a plan to the database.

        Args:
            plan: The plan to save

        Returns:
            The plan ID
        """
        await self.db.initialize()

        async with self._get_connection() as db:
            # Serialize plan to JSON for plan_json column
            plan_json = json.dumps(plan.to_dict())

            await db.execute(
                """
                INSERT OR REPLACE INTO execution_plans (
                    id, session_id, task_id, task_summary, rationale, risks,
                    status, total_estimated_vram_gb, plan_json,
                    created_at, approved_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.id,
                    plan.session_id,
                    plan.task_id,
                    plan.task_summary,
                    plan.rationale,
                    json.dumps(plan.risks),
                    plan.status.value,
                    plan.total_estimated_vram_gb,
                    plan_json,
                    plan.created_at.isoformat(),
                    plan.approved_at.isoformat() if plan.approved_at else None,
                    plan.completed_at.isoformat() if plan.completed_at else None,
                ),
            )

            # Save all steps
            for step in plan.steps:
                step.plan_id = plan.id
                await self._save_step_internal(db, step)

            await db.commit()

        log.info("plan_saved", plan_id=plan.id, steps=len(plan.steps))
        return plan.id

    async def load_plan(self, plan_id: str) -> Optional[PersistentPlan]:
        """Load a plan from the database.

        Args:
            plan_id: The plan ID

        Returns:
            The plan or None if not found
        """
        await self.db.initialize()

        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM execution_plans WHERE id = ?", (plan_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None

                # Parse plan from stored JSON
                plan_dict = json.loads(row["plan_json"])
                plan = PersistentPlan.from_dict(plan_dict)

                # Update with current DB values (may have changed)
                plan.status = PlanStatus(row["status"])
                if row["approved_at"]:
                    plan.approved_at = datetime.fromisoformat(row["approved_at"])
                if row["completed_at"]:
                    plan.completed_at = datetime.fromisoformat(row["completed_at"])

                # Load steps from separate table (may have been updated)
                async with db.execute(
                    "SELECT * FROM plan_steps WHERE plan_id = ? ORDER BY step_number",
                    (plan_id,),
                ) as step_cursor:
                    step_rows = await step_cursor.fetchall()
                    plan.steps = [self._row_to_step(r) for r in step_rows]

        return plan

    async def update_plan_status(
        self,
        plan_id: str,
        status: PlanStatus,
        approved_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ) -> bool:
        """Update a plan's status.

        Args:
            plan_id: The plan ID
            status: New status
            approved_at: When the plan was approved (optional)
            completed_at: When the plan completed (optional)

        Returns:
            True if updated, False if plan not found
        """
        await self.db.initialize()

        async with self._get_connection() as db:
            result = await db.execute(
                """
                UPDATE execution_plans
                SET status = ?, approved_at = ?, completed_at = ?
                WHERE id = ?
                """,
                (
                    status.value,
                    approved_at.isoformat() if approved_at else None,
                    completed_at.isoformat() if completed_at else None,
                    plan_id,
                ),
            )
            await db.commit()
            return result.rowcount > 0

    async def delete_plan(self, plan_id: str) -> bool:
        """Delete a plan and all its steps.

        Args:
            plan_id: The plan ID

        Returns:
            True if deleted, False if plan not found
        """
        await self.db.initialize()

        async with self._get_connection() as db:
            # Delete steps first (foreign key)
            await db.execute("DELETE FROM plan_steps WHERE plan_id = ?", (plan_id,))
            result = await db.execute(
                "DELETE FROM execution_plans WHERE id = ?", (plan_id,)
            )
            await db.commit()
            return result.rowcount > 0

    async def list_plans(
        self,
        status: Optional[PlanStatus] = None,
        task_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[PersistentPlan]:
        """List plans with optional filtering.

        Args:
            status: Filter by status (optional)
            task_id: Filter by task ID (optional)
            limit: Maximum number of plans to return

        Returns:
            List of plans (without full step details for efficiency)
        """
        await self.db.initialize()

        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row

            query = "SELECT * FROM execution_plans WHERE 1=1"
            params = []

            if status:
                query += " AND status = ?"
                params.append(status.value)

            if task_id:
                query += " AND task_id = ?"
                params.append(task_id)

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                plans = []
                for row in rows:
                    plan_dict = json.loads(row["plan_json"])
                    plan = PersistentPlan.from_dict(plan_dict)
                    plan.status = PlanStatus(row["status"])
                    plans.append(plan)
                return plans

    async def list_pending_plans(self) -> list[PersistentPlan]:
        """List all plans awaiting approval.

        Returns:
            List of proposed plans
        """
        return await self.list_plans(status=PlanStatus.PROPOSED)

    async def get_plans_for_task(self, task_id: str) -> list[PersistentPlan]:
        """Get all plans for a specific task.

        Args:
            task_id: The task ID

        Returns:
            List of plans for the task
        """
        return await self.list_plans(task_id=task_id)

    # ============== Step CRUD ==============

    async def _save_step_internal(
        self, db: aiosqlite.Connection, step: PersistentPlanStep
    ):
        """Internal: Save a step within an existing transaction."""
        await db.execute(
            """
            INSERT OR REPLACE INTO plan_steps (
                id, plan_id, step_number, description, agent, status,
                dependencies, tool_hints, estimated_iterations,
                started_at, completed_at, iterations_used,
                child_task_id, session_id, checkpoint_json, result_json, error,
                approval_required, approval_status, approved_at, rejection_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                step.id,
                step.plan_id,
                step.step_number,
                step.description,
                step.agent,
                step.status.value,
                json.dumps(step.dependencies),
                json.dumps(step.tool_hints),
                step.estimated_iterations,
                step.started_at.isoformat() if step.started_at else None,
                step.completed_at.isoformat() if step.completed_at else None,
                step.iterations_used,
                step.child_task_id,
                step.session_id,
                json.dumps(step.checkpoint.to_dict()) if step.checkpoint else None,
                json.dumps(step.result.to_dict()) if step.result else None,
                step.error,
                1 if step.approval_required else 0,
                step.approval_status.value if step.approval_status else None,
                step.approved_at.isoformat() if step.approved_at else None,
                step.rejection_reason,
            ),
        )

    async def save_step(self, step: PersistentPlanStep) -> str:
        """Save a step to the database.

        Args:
            step: The step to save

        Returns:
            The step ID
        """
        await self.db.initialize()

        async with self._get_connection() as db:
            await self._save_step_internal(db, step)
            await db.commit()

        log.debug("step_saved", step_id=step.id, step_number=step.step_number)
        return step.id

    async def load_step(self, step_id: str) -> Optional[PersistentPlanStep]:
        """Load a step from the database.

        Args:
            step_id: The step ID

        Returns:
            The step or None if not found
        """
        await self.db.initialize()

        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM plan_steps WHERE id = ?", (step_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return self._row_to_step(row)

    async def update_step_status(
        self,
        step_id: str,
        status: StepStatus,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        iterations_used: Optional[int] = None,
        error: Optional[str] = None,
    ) -> bool:
        """Update a step's status.

        Args:
            step_id: The step ID
            status: New status
            started_at: When the step started (optional)
            completed_at: When the step completed (optional)
            iterations_used: Number of iterations used (optional)
            error: Error message if failed (optional)

        Returns:
            True if updated, False if step not found
        """
        await self.db.initialize()

        async with self._get_connection() as db:
            # Build dynamic update
            updates = ["status = ?"]
            params = [status.value]

            if started_at is not None:
                updates.append("started_at = ?")
                params.append(started_at.isoformat())

            if completed_at is not None:
                updates.append("completed_at = ?")
                params.append(completed_at.isoformat())

            if iterations_used is not None:
                updates.append("iterations_used = ?")
                params.append(iterations_used)

            if error is not None:
                updates.append("error = ?")
                params.append(error)

            params.append(step_id)

            query = f"UPDATE plan_steps SET {', '.join(updates)} WHERE id = ?"
            result = await db.execute(query, params)
            await db.commit()
            return result.rowcount > 0

    async def save_step_checkpoint(
        self, step_id: str, checkpoint: Optional[StepCheckpoint]
    ) -> bool:
        """Save a step's checkpoint for later resume.

        Args:
            step_id: The step ID
            checkpoint: The checkpoint data (or None to clear)

        Returns:
            True if saved, False if step not found
        """
        await self.db.initialize()

        async with self._get_connection() as db:
            checkpoint_json = json.dumps(checkpoint.to_dict()) if checkpoint else None
            result = await db.execute(
                "UPDATE plan_steps SET checkpoint_json = ? WHERE id = ?",
                (checkpoint_json, step_id),
            )
            await db.commit()
            return result.rowcount > 0

    async def load_step_checkpoint(self, step_id: str) -> Optional[StepCheckpoint]:
        """Load a step's checkpoint.

        Args:
            step_id: The step ID

        Returns:
            The checkpoint or None if not found
        """
        await self.db.initialize()

        async with self._get_connection() as db:
            async with db.execute(
                "SELECT checkpoint_json FROM plan_steps WHERE id = ?", (step_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row or not row[0]:
                    return None
                return StepCheckpoint.from_dict(json.loads(row[0]))

    async def save_step_result(self, step_id: str, result: StepResult) -> bool:
        """Save a step's result.

        Args:
            step_id: The step ID
            result: The result data

        Returns:
            True if saved, False if step not found
        """
        await self.db.initialize()

        async with self._get_connection() as db:
            res = await db.execute(
                "UPDATE plan_steps SET result_json = ? WHERE id = ?",
                (json.dumps(result.to_dict()), step_id),
            )
            await db.commit()
            return res.rowcount > 0

    async def update_step_approval(
        self,
        step_id: str,
        approval_status: ApprovalStatus,
        approved_at: Optional[datetime] = None,
        rejection_reason: Optional[str] = None,
    ) -> bool:
        """Update a step's approval status.

        Args:
            step_id: The step ID
            approval_status: The approval status
            approved_at: When approved (optional)
            rejection_reason: Reason if rejected (optional)

        Returns:
            True if updated, False if step not found
        """
        await self.db.initialize()

        async with self._get_connection() as db:
            result = await db.execute(
                """
                UPDATE plan_steps
                SET approval_status = ?, approved_at = ?, rejection_reason = ?
                WHERE id = ?
                """,
                (
                    approval_status.value,
                    approved_at.isoformat() if approved_at else None,
                    rejection_reason,
                    step_id,
                ),
            )
            await db.commit()
            return result.rowcount > 0

    async def get_steps_for_plan(self, plan_id: str) -> list[PersistentPlanStep]:
        """Get all steps for a plan.

        Args:
            plan_id: The plan ID

        Returns:
            List of steps ordered by step number
        """
        await self.db.initialize()

        async with self._get_connection() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM plan_steps WHERE plan_id = ? ORDER BY step_number",
                (plan_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_step(r) for r in rows]

    def _row_to_step(self, row: aiosqlite.Row) -> PersistentPlanStep:
        """Convert a database row to a PersistentPlanStep."""
        # Parse JSON fields
        dependencies = json.loads(row["dependencies"]) if row["dependencies"] else []
        tool_hints = json.loads(row["tool_hints"]) if row["tool_hints"] else []

        checkpoint = None
        if row["checkpoint_json"]:
            checkpoint = StepCheckpoint.from_dict(json.loads(row["checkpoint_json"]))

        result = None
        if row["result_json"]:
            result = StepResult.from_dict(json.loads(row["result_json"]))

        # Parse datetimes
        started_at = None
        if row["started_at"]:
            started_at = datetime.fromisoformat(row["started_at"])

        completed_at = None
        if row["completed_at"]:
            completed_at = datetime.fromisoformat(row["completed_at"])

        approved_at = None
        if row["approved_at"]:
            approved_at = datetime.fromisoformat(row["approved_at"])

        # Parse enums
        status = StepStatus(row["status"]) if row["status"] else StepStatus.PENDING
        approval_status = (
            ApprovalStatus(row["approval_status"]) if row["approval_status"] else None
        )

        return PersistentPlanStep(
            id=row["id"],
            plan_id=row["plan_id"],
            step_number=row["step_number"],
            description=row["description"],
            agent=row["agent"],
            status=status,
            dependencies=dependencies,
            tool_hints=tool_hints,
            estimated_iterations=row["estimated_iterations"],
            started_at=started_at,
            completed_at=completed_at,
            iterations_used=row["iterations_used"] or 0,
            child_task_id=row["child_task_id"],
            session_id=row["session_id"],
            checkpoint=checkpoint,
            result=result,
            error=row["error"],
            approval_required=bool(row["approval_required"]),
            approval_status=approval_status,
            approved_at=approved_at,
            rejection_reason=row["rejection_reason"],
        )
