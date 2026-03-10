"""Tests for forge.runtime.planner"""

import pytest
from forge.runtime.planner import Planner, TaskPlan, PlanStep, StepStatus, CyclicDependencyError
from forge.core.blueprint import WorkflowBlueprint, WorkflowStep


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


class TestCycleDetection:
    """Tests for DAG cycle detection in TaskPlan."""

    def test_simple_cycle_detected(self):
        """A→B→A should be detected."""
        plan = TaskPlan(task="cycle", steps=[
            PlanStep(id="a", description="A", depends_on=["b"]),
            PlanStep(id="b", description="B", depends_on=["a"]),
        ])
        with pytest.raises(CyclicDependencyError) as exc_info:
            plan.validate_dependencies()
        assert "a" in exc_info.value.cycle
        assert "b" in exc_info.value.cycle

    def test_complex_cycle_detected(self):
        """A→B→C→A should be detected."""
        plan = TaskPlan(task="cycle", steps=[
            PlanStep(id="a", description="A", depends_on=["c"]),
            PlanStep(id="b", description="B", depends_on=["a"]),
            PlanStep(id="c", description="C", depends_on=["b"]),
        ])
        with pytest.raises(CyclicDependencyError) as exc_info:
            plan.validate_dependencies()
        cycle = exc_info.value.cycle
        assert len(cycle) >= 3
        assert cycle[0] == cycle[-1]  # cycle is closed

    def test_self_dependency_detected(self):
        """A→A should be detected."""
        plan = TaskPlan(task="self-dep", steps=[
            PlanStep(id="a", description="A", depends_on=["a"]),
        ])
        with pytest.raises(CyclicDependencyError) as exc_info:
            plan.validate_dependencies()
        assert "a" in exc_info.value.cycle

    def test_valid_dag_passes(self):
        """A valid DAG should not raise."""
        plan = TaskPlan(task="valid", steps=[
            PlanStep(id="a", description="A"),
            PlanStep(id="b", description="B", depends_on=["a"]),
            PlanStep(id="c", description="C", depends_on=["a"]),
            PlanStep(id="d", description="D", depends_on=["b", "c"]),
        ])
        plan.validate_dependencies()  # should not raise

    def test_error_message_includes_cycle_path(self):
        """The error message should contain the cycle path."""
        plan = TaskPlan(task="cycle", steps=[
            PlanStep(id="x", description="X", depends_on=["y"]),
            PlanStep(id="y", description="Y", depends_on=["x"]),
        ])
        with pytest.raises(CyclicDependencyError, match=r"Circular dependency detected"):
            plan.validate_dependencies()

    def test_get_ready_steps_raises_on_deadlock(self):
        """get_ready_steps should raise if stuck due to a cycle."""
        plan = TaskPlan(task="deadlock", steps=[
            PlanStep(id="a", description="A", depends_on=["b"]),
            PlanStep(id="b", description="B", depends_on=["a"]),
        ])
        with pytest.raises(CyclicDependencyError):
            plan.get_ready_steps()

    @pytest.mark.asyncio
    async def test_execute_plan_raises_on_cycle(self):
        """execute_plan should raise before starting execution."""
        planner = Planner()
        plan = TaskPlan(task="cycle", steps=[
            PlanStep(id="a", description="A", depends_on=["b"]),
            PlanStep(id="b", description="B", depends_on=["a"]),
        ])
        with pytest.raises(CyclicDependencyError):
            await planner.execute_plan(plan)

    def test_detect_cycles_returns_none_for_empty(self):
        """No steps means no cycles."""
        assert TaskPlan._detect_cycles([]) is None


class TestWorkflowBlueprintValidation:
    """Tests for cycle detection in WorkflowBlueprint."""

    def test_valid_workflow_passes(self):
        wf = WorkflowBlueprint(name="valid", steps=[
            WorkflowStep(id="s1", description="Step 1"),
            WorkflowStep(id="s2", description="Step 2", depends_on=["s1"]),
        ])
        wf.validate_dependencies()  # should not raise

    def test_cyclic_workflow_detected(self):
        wf = WorkflowBlueprint(name="cycle", steps=[
            WorkflowStep(id="s1", description="Step 1", depends_on=["s2"]),
            WorkflowStep(id="s2", description="Step 2", depends_on=["s1"]),
        ])
        with pytest.raises(CyclicDependencyError):
            wf.validate_dependencies()
