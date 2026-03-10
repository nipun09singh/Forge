"""Tests for forge.runtime.scheduler."""
import os
import tempfile
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta, timezone

from forge.runtime.scheduler import Scheduler, TaskSchedule, ScheduleStore


class TestTaskSchedule:
    def test_defaults(self):
        s = TaskSchedule()
        assert s.name == ""
        assert s.interval_seconds == 3600
        assert s.enabled is True
        assert s.run_count == 0
        assert s.id.startswith("sched-")
        assert s.cron_expression is None
        assert s.catch_up is False

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
        assert "cron_expression" in d
        assert "catch_up" in d

    def test_cron_expression_field(self):
        s = TaskSchedule(name="Cron", cron_expression="*/5 * * * *")
        assert s.cron_expression == "*/5 * * * *"
        d = s.to_dict()
        assert d["cron_expression"] == "*/5 * * * *"

    def test_compute_next_run_interval(self):
        base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        s = TaskSchedule(interval_seconds=300)
        nxt = s.compute_next_run(base)
        assert "2024-01-01T12:05:00" in nxt

    def test_compute_next_run_cron(self):
        base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        s = TaskSchedule(cron_expression="30 14 * * *")
        nxt = s.compute_next_run(base)
        assert "14:30" in nxt


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


class TestCronSchedule:
    def test_add_cron_schedule(self):
        sched = Scheduler()
        sid = sched.add_cron_schedule(
            name="Every5",
            task="run it",
            cron_expression="*/5 * * * *",
            team="ops",
        )
        s = sched.get(sid)
        assert s is not None
        assert s.cron_expression == "*/5 * * * *"
        assert s.name == "Every5"

    def test_add_cron_schedule_invalid(self):
        sched = Scheduler()
        with pytest.raises(ValueError, match="Invalid cron"):
            sched.add_cron_schedule(name="Bad", task="x", cron_expression="not valid cron")

    def test_cron_next_run_computed(self):
        sched = Scheduler()
        sid = sched.add_cron_schedule(
            name="Hourly",
            task="tick",
            cron_expression="0 * * * *",
        )
        s = sched.get(sid)
        assert s.next_run != ""

    def test_weekday_cron(self):
        sched = Scheduler()
        sid = sched.add_cron_schedule(
            name="Weekday Standup",
            task="standup",
            cron_expression="0 9 * * MON-FRI",
        )
        s = sched.get(sid)
        assert s is not None
        assert s.cron_expression == "0 9 * * MON-FRI"


class TestScheduleStore:
    def _make_store(self, tmp_path):
        db_path = os.path.join(tmp_path, "test_schedules.db")
        return ScheduleStore(db_path=db_path)

    def test_save_and_load(self, tmp_path):
        store = self._make_store(tmp_path)
        s = TaskSchedule(id="s1", name="Test", task="do", team="t",
                         interval_seconds=60, cron_expression="*/5 * * * *")
        store.save(s)
        loaded = store.load_all()
        assert len(loaded) == 1
        assert loaded[0].id == "s1"
        assert loaded[0].name == "Test"
        assert loaded[0].cron_expression == "*/5 * * * *"
        assert loaded[0].interval_seconds == 60
        store.close()

    def test_delete(self, tmp_path):
        store = self._make_store(tmp_path)
        s = TaskSchedule(id="s2", name="Del")
        store.save(s)
        assert store.delete("s2") is True
        assert store.delete("s2") is False
        assert len(store.load_all()) == 0
        store.close()

    def test_update_existing(self, tmp_path):
        store = self._make_store(tmp_path)
        s = TaskSchedule(id="s3", name="V1")
        store.save(s)
        s.name = "V2"
        s.run_count = 5
        store.save(s)
        loaded = store.load_all()
        assert len(loaded) == 1
        assert loaded[0].name == "V2"
        assert loaded[0].run_count == 5
        store.close()


class TestPersistentScheduler:
    def test_scheduler_loads_from_store(self, tmp_path):
        db_path = os.path.join(tmp_path, "sched.db")
        store1 = ScheduleStore(db_path=db_path)
        s = TaskSchedule(id="persist1", name="Persisted", task="hello",
                         next_run="2099-01-01T00:00:00+00:00")
        store1.save(s)
        store1.close()

        store2 = ScheduleStore(db_path=db_path)
        sched = Scheduler(store=store2)
        assert "persist1" in sched._schedules
        assert sched._schedules["persist1"].name == "Persisted"
        store2.close()

    def test_add_persists(self, tmp_path):
        db_path = os.path.join(tmp_path, "sched.db")
        store = ScheduleStore(db_path=db_path)
        sched = Scheduler(store=store)
        sched.add(TaskSchedule(id="p2", name="Added"))
        store.close()

        store2 = ScheduleStore(db_path=db_path)
        loaded = store2.load_all()
        assert any(s.id == "p2" for s in loaded)
        store2.close()

    def test_remove_persists(self, tmp_path):
        db_path = os.path.join(tmp_path, "sched.db")
        store = ScheduleStore(db_path=db_path)
        sched = Scheduler(store=store)
        sched.add(TaskSchedule(id="p3", name="ToRemove"))
        sched.remove("p3")
        store.close()

        store2 = ScheduleStore(db_path=db_path)
        loaded = store2.load_all()
        assert not any(s.id == "p3" for s in loaded)
        store2.close()


class TestRecovery:
    @pytest.mark.asyncio
    async def test_catch_up_missed_schedule(self):
        fn = AsyncMock(return_value=MagicMock(success=True, output="caught up"))
        sched = Scheduler(execute_fn=fn, catch_up=True)
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        task = TaskSchedule(id="missed1", name="Missed", task="recover",
                            next_run=past, enabled=True, catch_up=True)
        sched._schedules[task.id] = task
        await sched._recover_missed()
        fn.assert_called_once()
        assert task.run_count == 1

    @pytest.mark.asyncio
    async def test_no_catch_up_skips(self):
        fn = AsyncMock()
        sched = Scheduler(execute_fn=fn, catch_up=False)
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        task = TaskSchedule(id="skip1", name="Skip", task="nope",
                            next_run=past, enabled=True, catch_up=False)
        sched._schedules[task.id] = task
        await sched._recover_missed()
        fn.assert_not_called()
        # But next_run should be updated to the future
        assert task.next_run > datetime.now(timezone.utc).isoformat()
