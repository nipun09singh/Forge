"""Task scheduler — recurring and scheduled task execution with cron support and SQLite persistence."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cron helpers – prefer croniter, fall back to a basic built-in parser
# ---------------------------------------------------------------------------

try:
    from croniter import croniter as _croniter  # type: ignore[import-untyped]

    def _cron_next(expression: str, base: datetime) -> datetime:
        """Return the next fire time after *base* for a cron expression."""
        return _croniter(expression, base).get_next(datetime)

    def _cron_valid(expression: str) -> bool:
        try:
            _croniter(expression)
            return True
        except (ValueError, KeyError, TypeError):
            return False

except ImportError:
    # Minimal fallback supporting common patterns
    logger.debug("croniter not installed – using built-in cron parser (limited)")

    _DOW_MAP = {
        "SUN": 0, "MON": 1, "TUE": 2, "WED": 3,
        "THU": 4, "FRI": 5, "SAT": 6,
    }

    def _parse_field(field_str: str, lo: int, hi: int) -> set[int]:
        """Parse a single cron field into a set of valid integer values."""
        values: set[int] = set()
        for part in field_str.split(","):
            part = part.strip()
            # Replace day-of-week names
            for name, num in _DOW_MAP.items():
                part = part.replace(name, str(num))
            # Handle ranges with optional step (e.g. 1-5/2, MON-FRI)
            range_step = re.match(r"^(\d+)-(\d+)(?:/(\d+))?$", part)
            if range_step:
                start, end, step = int(range_step[1]), int(range_step[2]), int(range_step[3] or 1)
                values.update(range(start, end + 1, step))
                continue
            # */N
            m = re.match(r"^\*/(\d+)$", part)
            if m:
                values.update(range(lo, hi + 1, int(m[1])))
                continue
            # plain *
            if part == "*":
                values.update(range(lo, hi + 1))
                continue
            # literal number
            if part.isdigit():
                values.add(int(part))
                continue
            raise ValueError(f"Unsupported cron token: {part}")
        return values

    def _cron_next(expression: str, base: datetime) -> datetime:
        parts = expression.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Cron expression must have 5 fields, got {len(parts)}: {expression}")
        minutes = _parse_field(parts[0], 0, 59)
        hours = _parse_field(parts[1], 0, 23)
        days = _parse_field(parts[2], 1, 31)
        months = _parse_field(parts[3], 1, 12)
        dows = _parse_field(parts[4], 0, 6)

        candidate = base.replace(second=0, microsecond=0) + timedelta(minutes=1)
        # Search up to 366 days ahead
        limit = base + timedelta(days=366)
        while candidate < limit:
            if (candidate.month in months
                    and candidate.day in days
                    and candidate.hour in hours
                    and candidate.minute in minutes
                    and candidate.weekday() in {(d - 1) % 7 for d in dows}  # cron 0=Sun -> Python 6=Sun
                    ):
                return candidate
            candidate += timedelta(minutes=1)
        raise ValueError(f"No next run found within 366 days for: {expression}")

    def _cron_valid(expression: str) -> bool:
        try:
            _cron_next(expression, datetime.now(timezone.utc))
            return True
        except (ValueError, KeyError, TypeError):
            return False


# ---------------------------------------------------------------------------
# TaskSchedule dataclass
# ---------------------------------------------------------------------------

@dataclass
class TaskSchedule:
    """A scheduled task definition."""
    id: str = field(default_factory=lambda: f"sched-{uuid.uuid4().hex[:8]}")
    name: str = ""
    task: str = ""
    team: str = ""
    cron_expression: str | None = None
    interval_seconds: int = 3600  # Default: hourly
    enabled: bool = True
    context: dict[str, Any] = field(default_factory=dict)
    last_run: str = ""
    next_run: str = ""
    run_count: int = 0
    last_result: str = ""
    last_success: bool = True
    catch_up: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "id": self.id,
            "name": self.name,
            "task": self.task,
            "team": self.team,
            "cron_expression": self.cron_expression,
            "interval_seconds": self.interval_seconds,
            "enabled": self.enabled,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "run_count": self.run_count,
            "last_success": self.last_success,
            "catch_up": self.catch_up,
            "created_at": self.created_at,
        }

    def compute_next_run(self, after: datetime | None = None) -> str:
        """Compute and return the next run time as an ISO-8601 string."""
        base = after or datetime.now(timezone.utc)
        if self.cron_expression:
            return _cron_next(self.cron_expression, base).replace(tzinfo=timezone.utc).isoformat()
        return (base + timedelta(seconds=self.interval_seconds)).isoformat()


# ---------------------------------------------------------------------------
# ScheduleStore — SQLite persistence
# ---------------------------------------------------------------------------

_DEFAULT_DB_PATH = os.path.join(Path.home(), ".forge", "schedules.db")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS schedules (
    id              TEXT PRIMARY KEY,
    name            TEXT,
    task            TEXT,
    team            TEXT,
    cron            TEXT,
    interval_seconds INT,
    enabled         INT,
    context         JSON,
    last_run        TEXT,
    next_run        TEXT,
    run_count       INT,
    last_result     TEXT,
    last_success    INT,
    catch_up        INT DEFAULT 0,
    created_at      TEXT
)
"""


class ScheduleStore:
    """Persist schedules to a SQLite database."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or _DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()

    # -- CRUD ---------------------------------------------------------------

    def save(self, s: TaskSchedule) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO schedules
               (id, name, task, team, cron, interval_seconds, enabled,
                context, last_run, next_run, run_count, last_result,
                last_success, catch_up, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                s.id, s.name, s.task, s.team,
                s.cron_expression, s.interval_seconds, int(s.enabled),
                json.dumps(s.context), s.last_run, s.next_run,
                s.run_count, s.last_result, int(s.last_success),
                int(s.catch_up), s.created_at,
            ),
        )
        self._conn.commit()

    def delete(self, schedule_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def load_all(self) -> list[TaskSchedule]:
        rows = self._conn.execute("SELECT * FROM schedules").fetchall()
        return [self._row_to_schedule(r) for r in rows]

    def close(self) -> None:
        self._conn.close()

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _row_to_schedule(row: sqlite3.Row) -> TaskSchedule:
        ctx = row["context"]
        return TaskSchedule(
            id=row["id"],
            name=row["name"] or "",
            task=row["task"] or "",
            team=row["team"] or "",
            cron_expression=row["cron"] or None,
            interval_seconds=row["interval_seconds"] or 3600,
            enabled=bool(row["enabled"]),
            context=json.loads(ctx) if ctx else {},
            last_run=row["last_run"] or "",
            next_run=row["next_run"] or "",
            run_count=row["run_count"] or 0,
            last_result=row["last_result"] or "",
            last_success=bool(row["last_success"]) if row["last_success"] is not None else True,
            catch_up=bool(row["catch_up"]) if row["catch_up"] is not None else False,
            created_at=row["created_at"] or "",
        )


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class Scheduler:
    """
    Task scheduler for recurring agency operations.

    Supports interval-based scheduling (every N seconds) **and** cron
    expressions.  Optionally persists schedules to SQLite so they survive
    restarts.

    Usage:
        scheduler = Scheduler(agency)
        scheduler.add(TaskSchedule(
            name="Daily Report",
            task="Generate a daily performance report",
            team="Analytics",
            interval_seconds=86400,
        ))
        scheduler.add_cron_schedule(
            name="Weekday Standup",
            task="Summarise overnight changes",
            cron_expression="0 9 * * MON-FRI",
        )
        await scheduler.start()  # Runs in background
    """

    def __init__(
        self,
        execute_fn: Callable[..., Awaitable[Any]] | None = None,
        *,
        store: ScheduleStore | None = None,
        catch_up: bool = False,
    ):
        self._schedules: dict[str, TaskSchedule] = {}
        self._execute_fn = execute_fn
        self._running = False
        self._task: asyncio.Task | None = None
        self._store = store
        self._catch_up = catch_up

        # Load persisted schedules on init
        if self._store:
            for s in self._store.load_all():
                self._schedules[s.id] = s
            if self._schedules:
                logger.info(f"Loaded {len(self._schedules)} persisted schedule(s)")

    # -- public API ---------------------------------------------------------

    def add(self, schedule: TaskSchedule) -> str:
        """Add a scheduled task. Returns the schedule ID."""
        self._schedules[schedule.id] = schedule
        if not schedule.next_run:
            schedule.next_run = schedule.compute_next_run(datetime.now(timezone.utc))
        if self._store:
            self._store.save(schedule)
        desc = schedule.cron_expression or f"every {schedule.interval_seconds}s"
        logger.info(f"Scheduled task '{schedule.name}' ({desc})")
        return schedule.id

    def add_cron_schedule(
        self,
        name: str,
        task: str,
        cron_expression: str,
        *,
        team: str = "",
        context: dict[str, Any] | None = None,
        enabled: bool = True,
        catch_up: bool | None = None,
    ) -> str:
        """Convenience: add a schedule driven by a cron expression."""
        if not _cron_valid(cron_expression):
            raise ValueError(f"Invalid cron expression: {cron_expression}")
        schedule = TaskSchedule(
            name=name,
            task=task,
            team=team,
            cron_expression=cron_expression,
            enabled=enabled,
            context=context or {},
            catch_up=catch_up if catch_up is not None else self._catch_up,
        )
        return self.add(schedule)

    def remove(self, schedule_id: str) -> bool:
        """Remove a scheduled task."""
        if schedule_id in self._schedules:
            del self._schedules[schedule_id]
            if self._store:
                self._store.delete(schedule_id)
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
            if self._store:
                self._store.save(s)
            return True
        return False

    def disable(self, schedule_id: str) -> bool:
        """Disable a scheduled task."""
        s = self._schedules.get(schedule_id)
        if s:
            s.enabled = False
            if self._store:
                self._store.save(s)
            return True
        return False

    # -- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        """Start the scheduler loop as a background task."""
        if self._running:
            return
        self._running = True
        await self._recover_missed()
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

    # -- internals ----------------------------------------------------------

    async def _recover_missed(self) -> None:
        """Run missed schedules whose next_run is in the past (if catch_up enabled)."""
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        for schedule in list(self._schedules.values()):
            if not schedule.enabled:
                continue
            should_catch_up = schedule.catch_up if schedule.catch_up else self._catch_up
            if should_catch_up and schedule.next_run and schedule.next_run < now_iso:
                logger.info(f"Catching up missed schedule: {schedule.name}")
                await self._execute_schedule(schedule)
            # Ensure next_run is in the future
            if schedule.next_run and schedule.next_run <= now_iso:
                schedule.next_run = schedule.compute_next_run(now)
                if self._store:
                    self._store.save(schedule)

    async def _run_loop(self) -> None:
        """Main scheduler loop — checks for due tasks every second."""
        while self._running:
            now = datetime.now(timezone.utc)
            now_iso = now.isoformat()

            for schedule in list(self._schedules.values()):
                if not schedule.enabled:
                    continue
                if not schedule.next_run or schedule.next_run <= now_iso:
                    asyncio.create_task(self._execute_schedule(schedule))
                    schedule.next_run = schedule.compute_next_run(now)
                    if self._store:
                        self._store.save(schedule)

            await asyncio.sleep(1)

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

        if self._store:
            self._store.save(schedule)

    def __repr__(self) -> str:
        active = sum(1 for s in self._schedules.values() if s.enabled)
        return f"Scheduler(tasks={len(self._schedules)}, active={active}, running={self._running})"
