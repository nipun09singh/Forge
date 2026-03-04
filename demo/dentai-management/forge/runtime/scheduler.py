"""Task scheduler — recurring and scheduled task execution."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class TaskSchedule:
    """A scheduled task definition."""
    id: str = field(default_factory=lambda: f"sched-{uuid.uuid4().hex[:8]}")
    name: str = ""
    task: str = ""
    team: str = ""
    interval_seconds: int = 3600  # Default: hourly
    enabled: bool = True
    context: dict[str, Any] = field(default_factory=dict)
    last_run: str = ""
    next_run: str = ""
    run_count: int = 0
    last_result: str = ""
    last_success: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "id": self.id,
            "name": self.name,
            "task": self.task,
            "team": self.team,
            "interval_seconds": self.interval_seconds,
            "enabled": self.enabled,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "run_count": self.run_count,
            "last_success": self.last_success,
        }


class Scheduler:
    """
    Task scheduler for recurring agency operations.

    Supports interval-based scheduling (every N seconds).
    Runs as an asyncio background task alongside the API server.

    Usage:
        scheduler = Scheduler(agency)
        scheduler.add(TaskSchedule(
            name="Daily Report",
            task="Generate a daily performance report",
            team="Analytics",
            interval_seconds=86400,
        ))
        await scheduler.start()  # Runs in background
    """

    def __init__(self, execute_fn: Callable[..., Awaitable[Any]] | None = None):
        self._schedules: dict[str, TaskSchedule] = {}
        self._execute_fn = execute_fn
        self._running = False
        self._task: asyncio.Task | None = None

    def add(self, schedule: TaskSchedule) -> str:
        """Add a scheduled task. Returns the schedule ID."""
        self._schedules[schedule.id] = schedule
        # Set initial next_run
        if not schedule.next_run:
            schedule.next_run = datetime.now(timezone.utc).isoformat()
        logger.info(f"Scheduled task '{schedule.name}' every {schedule.interval_seconds}s")
        return schedule.id

    def remove(self, schedule_id: str) -> bool:
        """Remove a scheduled task."""
        if schedule_id in self._schedules:
            del self._schedules[schedule_id]
            return True
        return False

    def get(self, schedule_id: str) -> TaskSchedule | None:
        """Get a schedule by ID."""
        return self._schedules.get(schedule_id)

    def list_schedules(self) -> list[dict[str, Any]]:
        """List all scheduled tasks."""
        return [s.to_dict() for s in self._schedules.values()]

    def enable(self, schedule_id: str) -> bool:
        """Enable a scheduled task."""
        s = self._schedules.get(schedule_id)
        if s:
            s.enabled = True
            return True
        return False

    def disable(self, schedule_id: str) -> bool:
        """Disable a scheduled task."""
        s = self._schedules.get(schedule_id)
        if s:
            s.enabled = False
            return True
        return False

    async def start(self) -> None:
        """Start the scheduler loop as a background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"Scheduler started with {len(self._schedules)} tasks")

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped")

    async def _run_loop(self) -> None:
        """Main scheduler loop — checks for due tasks every second."""
        while self._running:
            now = datetime.now(timezone.utc)
            now_iso = now.isoformat()

            for schedule in list(self._schedules.values()):
                if not schedule.enabled:
                    continue
                if not schedule.next_run or schedule.next_run <= now_iso:
                    # Task is due
                    asyncio.create_task(self._execute_schedule(schedule))
                    # Set next run
                    from datetime import timedelta
                    next_dt = now + timedelta(seconds=schedule.interval_seconds)
                    schedule.next_run = next_dt.isoformat()

            await asyncio.sleep(1)  # Check every second

    async def _execute_schedule(self, schedule: TaskSchedule) -> None:
        """Execute a single scheduled task."""
        logger.info(f"Executing scheduled task: {schedule.name}")
        schedule.last_run = datetime.now(timezone.utc).isoformat()
        schedule.run_count += 1

        try:
            if self._execute_fn:
                result = await self._execute_fn(
                    task=schedule.task,
                    team_name=schedule.team or None,
                    context=schedule.context or None,
                )
                schedule.last_success = result.success if hasattr(result, 'success') else True
                schedule.last_result = str(result.output if hasattr(result, 'output') else result)[:500]
            else:
                schedule.last_result = "No execute function configured"
                schedule.last_success = False
        except Exception as e:
            logger.error(f"Scheduled task '{schedule.name}' failed: {e}")
            schedule.last_success = False
            schedule.last_result = f"Error: {e}"

    def __repr__(self) -> str:
        active = sum(1 for s in self._schedules.values() if s.enabled)
        return f"Scheduler(tasks={len(self._schedules)}, active={active}, running={self._running})"
