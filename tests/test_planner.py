"""Tests for forge.runtime.planner"""

import pytest
from forge.runtime.planner import Planner, TaskPlan, PlanStep, StepStatus


class TestPlanStep:
    def test_default_status(self):
        step = PlanStep(id="s1", description="Test step")
        assert step.status == StepStatus.PENDING

    def test_can_retry(self):
        step = PlanStep(id="s1", description="Test", max_retries=2)
        assert step.can_retry
        step.retry_count = 2
        assert not step.can_retry


class TestTaskPlan:
    def test_plan_creation(self):
        plan = TaskPlan(task="Test task", steps=[
            PlanStep(id="s1", description="Step 1"),
            PlanStep(id="s2", description="Step 2", depends_on=["s1"]),
        ])
        assert len(plan.steps) == 2
        assert plan.progress == 0.0

    def test_get_ready_steps_no_deps(self):
        plan = TaskPlan(task="Test", steps=[
            PlanStep(id="s1", description="Step 1"),
            PlanStep(id="s2", description="Step 2"),
        ])
        ready = plan.get_ready_steps()
        assert len(ready) == 2

    def test_get_ready_steps_with_deps(self):
        plan = TaskPlan(task="Test", steps=[
            PlanStep(id="s1", description="Step 1"),
            PlanStep(id="s2", description="Step 2", depends_on=["s1"]),
        ])
        ready = plan.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].id == "s1"

    def test_progress_tracking(self):
        plan = TaskPlan(task="Test", steps=[
            PlanStep(id="s1", description="Step 1", status=StepStatus.COMPLETED),
            PlanStep(id="s2", description="Step 2"),
        ])
        assert plan.progress == 0.5

    def test_summary(self):
        plan = TaskPlan(task="Test task", steps=[
            PlanStep(id="s1", description="Do something"),
        ])
        summary = plan.to_summary()
        assert "Test task" in summary
        assert "s1" in summary

    def test_get_step(self):
        plan = TaskPlan(task="Test", steps=[PlanStep(id="s1", description="A")])
        assert plan.get_step("s1") is not None
        assert plan.get_step("nonexistent") is None


class TestPlanner:
    def test_planner_creation(self):
        planner = Planner()
        assert planner.max_replans == 3

    @pytest.mark.asyncio
    async def test_plan_without_llm_creates_single_step(self):
        planner = Planner()
        plan = await planner.plan("Do something")
        assert len(plan.steps) == 1
        assert plan.steps[0].description == "Do something"

    def test_get_team_roster_empty(self):
        planner = Planner()
        assert "No teams" in planner._get_team_roster()

    def test_active_plans(self):
        planner = Planner()
        assert planner.get_active_plans() == []
