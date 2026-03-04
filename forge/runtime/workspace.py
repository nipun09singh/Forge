"""Workspace management — isolated directories for agent task execution."""

from __future__ import annotations

import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Workspace:
    """
    An isolated workspace for a task.
    
    Each task gets its own directory where agents can create files,
    run commands, and store outputs without interfering with other tasks.
    """

    def __init__(self, task_id: str, base_dir: str = "./workspace"):
        self.task_id = task_id
        self.path = Path(base_dir).resolve() / task_id
        self.path.mkdir(parents=True, exist_ok=True)
        self.created_at = datetime.now(timezone.utc).isoformat()
        self._files_created: list[str] = []

    def get_path(self, relative: str = "") -> str:
        """Get absolute path within this workspace."""
        if relative:
            return str(self.path / relative)
        return str(self.path)

    def list_files(self) -> list[dict[str, Any]]:
        """List all files in this workspace."""
        files = []
        for f in sorted(self.path.rglob("*")):
            if f.is_file():
                rel = str(f.relative_to(self.path))
                files.append({
                    "path": rel,
                    "size": f.stat().st_size,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
                })
        return files

    def file_count(self) -> int:
        """Count files in workspace."""
        return sum(1 for _ in self.path.rglob("*") if _.is_file())

    def total_size(self) -> int:
        """Total size of workspace in bytes."""
        return sum(f.stat().st_size for f in self.path.rglob("*") if f.is_file())

    def cleanup(self) -> None:
        """Remove the workspace directory."""
        if self.path.exists():
            shutil.rmtree(str(self.path), ignore_errors=True)
            logger.info(f"Cleaned up workspace: {self.task_id}")

    def __repr__(self) -> str:
        return f"Workspace(id={self.task_id}, path={self.path}, files={self.file_count()})"


class WorkspaceManager:
    """
    Manages isolated workspaces for agent task execution.
    
    Each task gets its own directory. Old workspaces are cleaned up
    based on retention policy.
    """

    def __init__(self, base_dir: str = "./workspace", max_workspaces: int = 50):
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.max_workspaces = max_workspaces
        self._workspaces: dict[str, Workspace] = {}

    def create(self, task_id: str | None = None) -> Workspace:
        """Create a new workspace for a task."""
        if not task_id:
            task_id = f"task-{uuid.uuid4().hex[:8]}"
        
        workspace = Workspace(task_id=task_id, base_dir=str(self.base_dir))
        self._workspaces[task_id] = workspace
        
        # Enforce max workspaces
        if len(self._workspaces) > self.max_workspaces:
            self._cleanup_oldest()
        
        logger.info(f"Created workspace: {workspace}")
        return workspace

    def get(self, task_id: str) -> Workspace | None:
        """Get an existing workspace."""
        return self._workspaces.get(task_id)

    def get_or_create(self, task_id: str) -> Workspace:
        """Get existing or create new workspace."""
        if task_id in self._workspaces:
            return self._workspaces[task_id]
        return self.create(task_id)

    def list_workspaces(self) -> list[dict[str, Any]]:
        """List all active workspaces."""
        result = []
        for tid, ws in self._workspaces.items():
            result.append({
                "task_id": tid,
                "path": str(ws.path),
                "files": ws.file_count(),
                "size_bytes": ws.total_size(),
                "created_at": ws.created_at,
            })
        return result

    def cleanup(self, task_id: str) -> bool:
        """Clean up a specific workspace."""
        ws = self._workspaces.pop(task_id, None)
        if ws:
            ws.cleanup()
            return True
        return False

    def cleanup_all(self) -> int:
        """Clean up all workspaces."""
        count = len(self._workspaces)
        for ws in self._workspaces.values():
            ws.cleanup()
        self._workspaces.clear()
        return count

    def _cleanup_oldest(self) -> None:
        """Remove oldest workspaces beyond the limit."""
        sorted_ws = sorted(self._workspaces.items(), key=lambda x: x[1].created_at)
        while len(self._workspaces) > self.max_workspaces:
            tid, ws = sorted_ws.pop(0)
            ws.cleanup()
            del self._workspaces[tid]

    def get_default_workdir(self) -> str:
        """Get the base workspace directory path."""
        return str(self.base_dir)

    def __repr__(self) -> str:
        return f"WorkspaceManager(base={self.base_dir}, active={len(self._workspaces)})"
