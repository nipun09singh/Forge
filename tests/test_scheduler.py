"""Tests for forge.runtime.scheduler."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from forge.runtime.scheduler import Scheduler, TaskSchedule


class TestTaskSchedule:
    def test_defaults(self):
        s = TaskSchedule()
        assert s.name == ""
        assert s.interval_seconds == 3600
        assert s.enabled is True
        assert s.run_count == 0
        assert s.id.startswith("sched-")

    def test_custom_values(self):
        s = TaskSchedule(name="Daily Report", interval_seconds=86400, team="analytics")
        assert s.name == "Daily Report"
        assert s.interval_seconds == 86400
        assert s.team == "analytics"

    def test_to_dict(self):
        s = TaskSchedule(name="Test", task="do stuff")
        d = s.to_dict()
        assert d["name"] == "Test"
        assert d["task"] == "do stuff"
        assert "id" in d
        assert "enabled" in d


class TestSchedulerInit:
    def test_init_no_fn(self):
        sched = Scheduler()
        assert sched._schedules == {}
        assert sched._running is False

    def test_init_with_fn(self):
        fn = AsyncMock()
        sched = Scheduler(execute_fn=fn)
        assert sched._execute_fn is fn

    def test_repr(self):
        sched = Scheduler()
        assert "Scheduler" in repr(sched)
        assert "tasks=0" in repr(sched)


class TestSchedulerAddRemove:
    def test_add_returns_id(self):
        sched = Scheduler()
        task = TaskSchedule(name="Report")
        sid = sched.add(task)
        assert sid == task.id
        assert task.id in sched._schedules

    def test_add_sets_next_run(self):
        sched = Scheduler()
        task = TaskSchedule(name="Report")
        sched.add(task)
        assert task.next_run != ""

    def test_remove_existing(self):
        sched = Scheduler()
        task = TaskSchedule(name="ToRemove")
        sid = sched.add(task)
        assert sched.remove(sid) is True
        assert sid not in sched._schedules

    def test_remove_nonexistent(self):
        sched = Scheduler()
        assert sched.remove("not-a-real-id") is False

    def test_get_existing(self):
        sched = Scheduler()
        task = TaskSchedule(name="GetMe")
        sched.add(task)
        assert sched.get(task.id) is task

    def test_get_nonexistent(self):
        sched = Scheduler()
        assert sched.get("nope") is None


class TestSchedulerListAndToggle:
    def test_list_schedules(self):
        sched = Scheduler()
        sched.add(TaskSchedule(name="A"))
        sched.add(TaskSchedule(name="B"))
        lst = sched.list_schedules()
        assert len(lst) == 2
        names = {s["name"] for s in lst}
        assert names == {"A", "B"}

    def test_enable_disable(self):
        sched = Scheduler()
        task = TaskSchedule(name="Toggle", enabled=True)
        sched.add(task)
        assert sched.disable(task.id) is True
        assert task.enabled is False
        assert sched.enable(task.id) is True
        assert task.enabled is True

    def test_enable_nonexistent(self):
        sched = Scheduler()
        assert sched.enable("nope") is False
        assert sched.disable("nope") is False


class TestSchedulerStartStop:
    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        sched = Scheduler()
        await sched.start()
        assert sched._running is True
        await sched.stop()
        assert sched._running is False

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        sched = Scheduler()
        await sched.start()
        task1 = sched._task
        await sched.start()  # second start is a no-op
        assert sched._task is task1
        await sched.stop()

    @pytest.mark.asyncio
    async def test_execute_schedule_with_fn(self):
        fn = AsyncMock(return_value=MagicMock(success=True, output="done"))
        sched = Scheduler(execute_fn=fn)
        task = TaskSchedule(name="Exec", task="do it", team="ops")
        await sched._execute_schedule(task)
        fn.assert_called_once_with(task="do it", team_name="ops", context=None)
        assert task.run_count == 1
        assert task.last_success is True

    @pytest.mark.asyncio
    async def test_execute_schedule_no_fn(self):
        sched = Scheduler()
        task = TaskSchedule(name="NoFn")
        await sched._execute_schedule(task)
        assert task.last_success is False
        assert "No execute function" in task.last_result

    @pytest.mark.asyncio
    async def test_execute_schedule_handles_exception(self):
        fn = AsyncMock(side_effect=RuntimeError("boom"))
        sched = Scheduler(execute_fn=fn)
        task = TaskSchedule(name="Fail", task="crash")
        await sched._execute_schedule(task)
        assert task.last_success is False
        assert "boom" in task.last_result
