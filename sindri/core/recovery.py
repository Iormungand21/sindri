"""Session recovery after crashes."""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
import structlog

log = structlog.get_logger()


class RecoveryManager:
    """Manages crash recovery and session restoration.

    Saves checkpoints during task execution to allow recovery after
    unexpected termination (Ctrl+C, crash, etc.).
    """

    def __init__(self, state_dir: str = "~/.sindri/state"):
        self.state_dir = Path(state_dir).expanduser()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        log.info("recovery_manager_initialized", state_dir=str(self.state_dir))

    def save_checkpoint(self, session_id: str, state: dict):
        """Save checkpoint for crash recovery.

        Args:
            session_id: Unique session identifier
            state: Session state to save
        """
        checkpoint_path = self.state_dir / f"{session_id}.checkpoint.json"

        checkpoint = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "state": state
        }

        # Atomic write (write to temp, then rename)
        temp_path = checkpoint_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(checkpoint, indent=2))
        temp_path.replace(checkpoint_path)

        log.debug("checkpoint_saved", session_id=session_id)

    def has_checkpoint(self, session_id: str) -> bool:
        """Check if session has a recoverable checkpoint.

        Args:
            session_id: Session to check

        Returns:
            True if checkpoint exists
        """
        return (self.state_dir / f"{session_id}.checkpoint.json").exists()

    def load_checkpoint(self, session_id: str) -> Optional[dict]:
        """Load checkpoint if available.

        Args:
            session_id: Session to load

        Returns:
            Session state or None if not found
        """
        checkpoint_path = self.state_dir / f"{session_id}.checkpoint.json"

        if not checkpoint_path.exists():
            log.warning("checkpoint_not_found", session_id=session_id)
            return None

        try:
            data = json.loads(checkpoint_path.read_text())
            log.info(
                "checkpoint_loaded",
                session_id=session_id,
                saved_at=data.get("timestamp")
            )
            return data.get("state")
        except Exception as e:
            log.error("checkpoint_load_failed", session_id=session_id, error=str(e))
            return None

    def clear_checkpoint(self, session_id: str):
        """Remove checkpoint after successful completion.

        Args:
            session_id: Session to clear
        """
        checkpoint_path = self.state_dir / f"{session_id}.checkpoint.json"
        if checkpoint_path.exists():
            checkpoint_path.unlink()
            log.debug("checkpoint_cleared", session_id=session_id)

    def list_recoverable_sessions(self) -> list[dict]:
        """List all sessions that can be recovered.

        Returns:
            List of recoverable session info dicts
        """
        sessions = []

        for checkpoint_path in self.state_dir.glob("*.checkpoint.json"):
            try:
                data = json.loads(checkpoint_path.read_text())
                sessions.append({
                    "session_id": data.get("session_id"),
                    "timestamp": data.get("timestamp"),
                    "task": data.get("state", {}).get("task", "Unknown"),
                    "iterations": data.get("state", {}).get("iterations", 0)
                })
            except Exception as e:
                log.warning("checkpoint_parse_failed", path=str(checkpoint_path), error=str(e))
                continue

        # Sort by timestamp, most recent first
        return sorted(sessions, key=lambda s: s.get("timestamp", ""), reverse=True)

    def cleanup_old_checkpoints(self, keep: int = None, max_age_days: int = None):
        """Remove old checkpoints.

        Args:
            keep: Keep only N most recent checkpoints (mutually exclusive with max_age_days)
            max_age_days: Remove checkpoints older than N days
        """
        if keep is not None:
            # Keep N most recent, delete the rest
            sessions = self.list_recoverable_sessions()  # Already sorted by timestamp desc

            if len(sessions) <= keep:
                return  # Nothing to clean up

            # Delete older ones
            to_delete = sessions[keep:]
            for session in to_delete:
                checkpoint_path = self.state_dir / f"{session['session_id']}.checkpoint.json"
                if checkpoint_path.exists():
                    checkpoint_path.unlink()

            log.info("old_checkpoints_removed", count=len(to_delete), kept=keep)

        elif max_age_days is not None:
            # Remove checkpoints older than specified age
            from datetime import timedelta

            cutoff = datetime.now() - timedelta(days=max_age_days)
            removed = 0

            for checkpoint_path in self.state_dir.glob("*.checkpoint.json"):
                try:
                    data = json.loads(checkpoint_path.read_text())
                    timestamp_str = data.get("timestamp")
                    if timestamp_str:
                        timestamp = datetime.fromisoformat(timestamp_str)
                        if timestamp < cutoff:
                            checkpoint_path.unlink()
                            removed += 1
                except Exception:
                    continue

            if removed > 0:
                log.info("old_checkpoints_removed", count=removed, max_age_days=max_age_days)
