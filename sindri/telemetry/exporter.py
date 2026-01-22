"""Trace export for profiling and regression checks.

ROADMAP Item 7: Performance Telemetry Stream
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
import structlog

log = structlog.get_logger()


class TraceExporter:
    """Export session traces for profiling and analysis.

    Exports include:
    - Session metrics (iterations, tool calls, timing)
    - Environment snapshot (versions, model metadata)
    - Tool audit log
    """

    def __init__(
        self,
        metrics_store=None,
        snapshot_store=None,
        audit_store=None,
    ):
        """Initialize the TraceExporter.

        Args:
            metrics_store: Optional MetricsStore instance
            snapshot_store: Optional SnapshotStore instance
            audit_store: Optional AuditStore instance
        """
        self._metrics_store = metrics_store
        self._snapshot_store = snapshot_store
        self._audit_store = audit_store

    def _get_metrics_store(self):
        """Lazy-load MetricsStore."""
        if self._metrics_store is None:
            from sindri.persistence.metrics import MetricsStore

            self._metrics_store = MetricsStore()
        return self._metrics_store

    def _get_snapshot_store(self):
        """Lazy-load SnapshotStore."""
        if self._snapshot_store is None:
            from sindri.persistence.snapshots import SnapshotStore

            self._snapshot_store = SnapshotStore()
        return self._snapshot_store

    def _get_audit_store(self):
        """Lazy-load AuditStore."""
        if self._audit_store is None:
            from sindri.persistence.audit import AuditStore

            self._audit_store = AuditStore()
        return self._audit_store

    async def export_session_trace(
        self,
        session_id: str,
        output_path: Optional[Path] = None,
        include_tool_outputs: bool = False,
    ) -> dict[str, Any]:
        """Export complete trace for a session.

        Args:
            session_id: Session to export
            output_path: Optional path to write JSON file
            include_tool_outputs: Include full tool outputs (can be large)

        Returns:
            Trace dictionary with all session data
        """
        trace = {
            "version": "1.0.0",
            "format": "sindri-trace",
            "session_id": session_id,
            "exported_at": datetime.now().isoformat(),
            "metrics": None,
            "environment": None,
            "audit_log": None,
        }

        # Load metrics
        try:
            metrics_store = self._get_metrics_store()
            metrics = await metrics_store.get_metrics(session_id)
            if metrics:
                trace["metrics"] = metrics.to_dict()
        except Exception as e:
            log.warning("trace_export_metrics_error", session_id=session_id, error=str(e))

        # Load environment snapshot
        try:
            snapshot_store = self._get_snapshot_store()
            snapshot = await snapshot_store.load_snapshot(session_id)
            if snapshot:
                trace["environment"] = snapshot.to_dict()
        except Exception as e:
            log.warning("trace_export_snapshot_error", session_id=session_id, error=str(e))

        # Load audit log
        try:
            audit_store = self._get_audit_store()
            audit_entries = await audit_store.list_entries(
                session_id=session_id, limit=1000
            )
            if audit_entries:
                trace["audit_log"] = [
                    {
                        "tool_name": e.tool_name,
                        "success": e.success,
                        "duration_ms": e.duration_ms,
                        "created_at": e.created_at.isoformat() if e.created_at else None,
                        "dry_run": e.dry_run,
                    }
                    for e in audit_entries
                ]
        except Exception as e:
            log.warning("trace_export_audit_error", session_id=session_id, error=str(e))

        # Write to file if path provided
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(trace, f, indent=2, default=str)
            log.info("trace_exported", session_id=session_id, path=str(output_path))

        return trace

    async def compare_traces(
        self,
        trace1_path: Path,
        trace2_path: Path,
    ) -> dict[str, Any]:
        """Compare two traces for regression checking.

        Args:
            trace1_path: Path to baseline trace
            trace2_path: Path to comparison trace

        Returns:
            Comparison results with deltas and detected regressions
        """
        with open(trace1_path) as f:
            baseline = json.load(f)
        with open(trace2_path) as f:
            current = json.load(f)

        comparison = {
            "baseline_session": baseline.get("session_id"),
            "current_session": current.get("session_id"),
            "compared_at": datetime.now().isoformat(),
            "duration_delta": None,
            "iteration_delta": None,
            "tool_call_delta": None,
            "regressions": [],
            "improvements": [],
        }

        # Compare metrics
        b_metrics = baseline.get("metrics", {})
        c_metrics = current.get("metrics", {})

        if b_metrics and c_metrics:
            # Duration comparison
            b_duration = (b_metrics.get("end_time") or 0) - (b_metrics.get("start_time") or 0)
            c_duration = (c_metrics.get("end_time") or 0) - (c_metrics.get("start_time") or 0)

            if b_duration > 0:
                change_percent = (c_duration - b_duration) / b_duration * 100
            else:
                change_percent = 0.0

            comparison["duration_delta"] = {
                "baseline": b_duration,
                "current": c_duration,
                "change_percent": change_percent,
            }

            # Iteration count
            b_iter = sum(len(t.get("iterations", [])) for t in b_metrics.get("tasks", []))
            c_iter = sum(len(t.get("iterations", [])) for t in c_metrics.get("tasks", []))
            comparison["iteration_delta"] = {
                "baseline": b_iter,
                "current": c_iter,
                "change": c_iter - b_iter,
            }

            # Tool call count
            b_tools = sum(
                sum(len(i.get("tool_executions", [])) for i in t.get("iterations", []))
                for t in b_metrics.get("tasks", [])
            )
            c_tools = sum(
                sum(len(i.get("tool_executions", [])) for i in t.get("iterations", []))
                for t in c_metrics.get("tasks", [])
            )
            comparison["tool_call_delta"] = {
                "baseline": b_tools,
                "current": c_tools,
                "change": c_tools - b_tools,
            }

            # Detect regressions (>20% slower)
            if comparison["duration_delta"]["change_percent"] > 20:
                comparison["regressions"].append(
                    {
                        "type": "duration",
                        "message": f"Session {comparison['duration_delta']['change_percent']:.1f}% slower",
                        "baseline_value": b_duration,
                        "current_value": c_duration,
                    }
                )

            # Detect improvements (>10% faster)
            if comparison["duration_delta"]["change_percent"] < -10:
                comparison["improvements"].append(
                    {
                        "type": "duration",
                        "message": f"Session {abs(comparison['duration_delta']['change_percent']):.1f}% faster",
                        "baseline_value": b_duration,
                        "current_value": c_duration,
                    }
                )

            # Check for iteration increase (potential regression)
            if comparison["iteration_delta"]["change"] > 5:
                comparison["regressions"].append(
                    {
                        "type": "iterations",
                        "message": f"Required {comparison['iteration_delta']['change']} more iterations",
                        "baseline_value": b_iter,
                        "current_value": c_iter,
                    }
                )

            # Check for iteration decrease (improvement)
            if comparison["iteration_delta"]["change"] < -3:
                comparison["improvements"].append(
                    {
                        "type": "iterations",
                        "message": f"Required {abs(comparison['iteration_delta']['change'])} fewer iterations",
                        "baseline_value": b_iter,
                        "current_value": c_iter,
                    }
                )

        return comparison

    @staticmethod
    def load_trace(trace_path: Path) -> dict[str, Any]:
        """Load a trace from file.

        Args:
            trace_path: Path to trace JSON file

        Returns:
            Trace dictionary
        """
        with open(trace_path) as f:
            return json.load(f)

    @staticmethod
    def get_trace_summary(trace: dict[str, Any]) -> dict[str, Any]:
        """Get a summary of a trace.

        Args:
            trace: Trace dictionary

        Returns:
            Summary dictionary with key metrics
        """
        metrics = trace.get("metrics", {})
        environment = trace.get("environment", {})
        audit_log = trace.get("audit_log", [])

        # Calculate duration
        duration = 0.0
        if metrics:
            start = metrics.get("start_time")
            end = metrics.get("end_time")
            if start is not None and end is not None:
                duration = end - start

        # Count iterations and tool calls
        total_iterations = 0
        total_tool_calls = 0
        if metrics:
            for task in metrics.get("tasks", []):
                iterations = task.get("iterations", [])
                total_iterations += len(iterations)
                for iteration in iterations:
                    total_tool_calls += len(iteration.get("tool_executions", []))

        # Get model info
        model_name = ""
        if environment:
            model_meta = environment.get("model_metadata", {})
            model_name = model_meta.get("name", "")

        return {
            "session_id": trace.get("session_id"),
            "exported_at": trace.get("exported_at"),
            "duration_seconds": duration,
            "total_iterations": total_iterations,
            "total_tool_calls": total_tool_calls,
            "audit_entries": len(audit_log),
            "model_name": model_name,
            "has_metrics": metrics is not None,
            "has_environment": environment is not None,
        }
