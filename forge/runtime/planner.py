"""Strategic Planner — decomposes complex tasks into executable plans."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from forge.runtime.agent import Agent, TaskResult
    from forge.runtime.team import Team

logger = logging.getLogger(__name__)


class CyclicDependencyError(Exception):
    """Raised when a circular dependency is detected among plan steps."""

    def __init__(self, cycle: list[str]):
        self.cycle = cycle
        cycle_str = " → ".join(cycle)
        super().__init__(f"Circular dependency detected: {cycle_str}")


class StepStatus(str, Enum):
    """Status of a plan step."""
    PENDING = "pending"
    READY = "ready"       # Dependencies satisfied, can execute
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    """A single step in a task plan."""
    id: str
    description: str
    assigned_team: str = ""
    assigned_agent: str = ""
    depends_on: list[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: str = ""
    parallel_group: str = ""  # Steps in same group can run concurrently
    estimated_complexity: str = "medium"  # low, medium, high
    retry_count: int = 0
    max_retries: int = 2

    @property
    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries


@dataclass
class TaskPlan:
    """A directed acyclic graph (DAG) of steps to execute a complex task."""
    id: str = field(default_factory=lambda: f"plan-{uuid.uuid4().hex[:8]}")
    task: str = ""
    steps: list[PlanStep] = field(default_factory=list)
    status: str = "pending"  # pending, executing, completed, failed
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def completed_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == StepStatus.COMPLETED]

    @property
    def failed_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == StepStatus.FAILED]

    @property
    def pending_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status in (StepStatus.PENDING, StepStatus.READY)]

    @property
    def running_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == StepStatus.RUNNING]

    @property
    def progress(self) -> float:
        if not self.steps:
            return 0.0
        return len(self.completed_steps) / len(self.steps)

    def get_ready_steps(self) -> list[PlanStep]:
        """Get steps whose dependencies are all satisfied. Does NOT mutate step status.

        Raises CyclicDependencyError if no steps are ready but pending steps
        remain and nothing is running (deadlock implies a cycle).
        """
        completed_ids = {s.id for s in self.completed_steps}
        ready = []
        for step in self.steps:
            if step.status != StepStatus.PENDING:
                continue
            deps_met = all(dep in completed_ids for dep in step.depends_on)
            if deps_met:
                ready.append(step)

        if not ready and self.pending_steps and not self.running_steps:
            cycle = self._detect_cycles(self.pending_steps)
            if cycle:
                raise CyclicDependencyError(cycle)

        return ready

    # ─── CYCLE DETECTION ─────────────────────────────────────

    @staticmethod
    def _detect_cycles(steps: list[PlanStep]) -> list[str] | None:
        """Detect circular dependencies using DFS. Returns cycle path or None."""
        graph: dict[str, list[str]] = {s.id: list(s.depends_on) for s in steps}
        visited: set[str] = set()
        rec_stack: set[str] = set()
        path: list[str] = []

        def dfs(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            for dep in graph.get(node, []):
                if dep not in visited:
                    if dfs(dep):
                        return True
                elif dep in rec_stack:
                    path.append(dep)
                    return True
            path.pop()
            rec_stack.discard(node)
            return False

        for step_id in graph:
            if step_id not in visited:
                if dfs(step_id):
                    cycle_start = path[-1]
                    idx = path.index(cycle_start)
                    return path[idx:]
        return None

    def validate_dependencies(self) -> None:
        """Validate that the plan has no circular dependencies.

        Raises CyclicDependencyError if a cycle is found.
        Can be called externally before execution.
        """
        cycle = self._detect_cycles(self.steps)
        if cycle:
            raise CyclicDependencyError(cycle)

    def mark_ready(self, step: PlanStep) -> None:
        """Mark a step as ready for execution."""
        step.status = StepStatus.READY

    def get_step(self, step_id: str) -> PlanStep | None:
        """Get a step by ID."""
        return next((s for s in self.steps if s.id == step_id), None)

    def to_summary(self) -> str:
        """Human-readable plan summary."""
        lines = [f"Plan: {self.task}", f"Status: {self.status} ({self.progress:.0%} complete)", ""]
        for step in self.steps:
            deps = f" ← [{', '.join(step.depends_on)}]" if step.depends_on else ""
            icon = {"pending": "⏳", "ready": "🟡", "running": "🔄", "completed": "✅", "failed": "❌", "skipped": "⏭️"}.get(step.status.value, "?")
            assign = step.assigned_team or step.assigned_agent or "unassigned"
            lines.append(f"  {icon} {step.id}: {step.description} [{assign}]{deps}")
        return "\n".join(lines)


class Planner:
    """
    Strategic Planner — the brain of an AI agency.

    Takes complex tasks and:
    1. Decomposes them into a DAG of sub-tasks (using LLM)
    2. Assigns sub-tasks to the best agents/teams
    3. Executes the plan respecting dependencies
    4. Runs independent steps in parallel
    5. Re-plans on failure
    6. Tracks progress

    Every generated agency gets a Planner to handle multi-step work.
    """

    def __init__(
        self,
        teams: dict[str, Team] | None = None,
        agents: dict[str, Any] | None = None,  # Agent instances
        llm_client: Any = None,
        model: str = "gpt-4",
        max_replans: int = 3,
    ):
        self._teams = teams or {}
        self._agents = agents or {}
        self._llm_client = llm_client
        self.model = model
        self.max_replans = max_replans
        self._active_plans: dict[str, TaskPlan] = {}
        self._plan_history: list[TaskPlan] = []

    def __repr__(self) -> str:
        return f"Planner(teams={len(self._teams)}, active_plans={len(self._active_plans)})"

    def set_llm_client(self, client: Any) -> None:
        """Set the LLM client for planning."""
        self._llm_client = client

    def set_teams(self, teams: dict[str, Team]) -> None:
        """Update available teams."""
        self._teams = teams

    def set_agents(self, agents: dict[str, Any]) -> None:
        """Update available standalone agents."""
        self._agents = agents

    # ─── PLANNING ─────────────────────────────────────────────

    async def plan(self, task: str, context: dict[str, Any] | None = None) -> TaskPlan:
        """
        Decompose a complex task into an executable plan.

        Uses LLM to analyze the task and produce a DAG of steps
        with dependencies and team/agent assignments.
        """
        if not task or not isinstance(task, str) or not task.strip():
            return TaskPlan(
                task="(empty task)",
                steps=[PlanStep(id="error", description="Cannot plan an empty task", status=StepStatus.FAILED)],
                status="failed",
            )

        if not self._llm_client:
            # Fallback: single-step plan
            return TaskPlan(
                task=task,
                steps=[PlanStep(id="step-1", description=task)],
                status="pending",
            )

        # Build context about available teams and agents
        team_info = self._get_team_roster()

        messages = [
            {"role": "system", "content": (
                "You are a strategic project planner for an AI agency. "
                "Your job is to decompose complex tasks into a series of concrete steps "
                "that can be assigned to teams.\n\n"
                "Rules:\n"
                "1. Each step should be a single, clear action\n"
                "2. Steps can depend on other steps (use step IDs)\n"
                "3. Steps with no dependencies between them CAN run in parallel\n"
                "4. Assign each step to the most appropriate team\n"
                "5. Include a QA review step for important outputs\n"
                "6. Think about what could go wrong and add validation steps\n"
                "7. Keep plans practical — 3 to 15 steps typically\n\n"
                f"Available teams:\n{team_info}\n\n"
                "Respond with a JSON object with this structure:\n"
                '{"steps": [{"id": "step-1", "description": "...", "assigned_team": "...", '
                '"depends_on": [], "estimated_complexity": "low|medium|high"}]}'
            )},
            {"role": "user", "content": f"Create an execution plan for this task:\n\n{task}"},
        ]

        if context:
            ctx_str = "\n".join(f"- {k}: {v}" for k, v in context.items())
            messages[-1]["content"] += f"\n\nAdditional context:\n{ctx_str}"

        try:
            response = await self._llm_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.4,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                logger.warning(f"LLM returned non-JSON plan, falling back to single step: {e}")
                plan = TaskPlan(
                    task=task,
                    steps=[PlanStep(id="step-1", description=task)],
                    status="pending",
                )
                self._active_plans[plan.id] = plan
                return plan

            steps = []
            for s in data.get("steps", []):
                steps.append(PlanStep(
                    id=s.get("id", f"step-{len(steps)+1}"),
                    description=s.get("description", ""),
                    assigned_team=s.get("assigned_team", ""),
                    assigned_agent=s.get("assigned_agent", ""),
                    depends_on=s.get("depends_on", []),
                    estimated_complexity=s.get("estimated_complexity", "medium"),
                ))

            plan = TaskPlan(task=task, steps=steps, status="pending")
            self._active_plans[plan.id] = plan
            logger.info(f"Created plan '{plan.id}' with {len(steps)} steps")
            return plan

        except Exception as e:
            logger.error(f"Planning failed: {e}. Creating single-step fallback plan.")
            plan = TaskPlan(
                task=task,
                steps=[PlanStep(id="step-1", description=task)],
                status="pending",
            )
            self._active_plans[plan.id] = plan
            return plan

    # ─── EXECUTION ────────────────────────────────────────────

    async def execute_plan(self, plan: TaskPlan) -> dict[str, Any]:
        """
        Execute a plan by running steps in dependency order.

        Independent steps are run in parallel.
        Failed steps trigger re-planning.
        Raises CyclicDependencyError if the plan contains circular dependencies.
        """
        plan.validate_dependencies()

        plan.status = "executing"
        replan_count = 0
        consolidated_results: dict[str, Any] = {}

        while True:
            ready_steps = plan.get_ready_steps()

            if not ready_steps:
                # Check if we're done or stuck
                if plan.pending_steps or plan.running_steps:
                    # Still have work but nothing is ready — check for failures
                    if plan.failed_steps and replan_count < self.max_replans:
                        logger.info(f"Re-planning due to {len(plan.failed_steps)} failed steps...")
                        await self._replan(plan, plan.failed_steps)
                        replan_count += 1
                        continue
                    else:
                        plan.status = "failed"
                        break
                else:
                    # All steps either completed or skipped
                    plan.status = "completed"
                    break

            # Execute ready steps in parallel
            logger.info(f"Executing {len(ready_steps)} steps in parallel...")
            tasks = []
            for step in ready_steps:
                step.status = StepStatus.RUNNING
                tasks.append(self._execute_step(step, consolidated_results))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for step, result in zip(ready_steps, results):
                if isinstance(result, Exception):
                    step.status = StepStatus.FAILED
                    step.error = str(result)
                    logger.error(f"Step '{step.id}' failed: {result}")
                elif result and hasattr(result, 'success') and not result.success:
                    step.status = StepStatus.FAILED
                    step.error = result.output if hasattr(result, 'output') else str(result)
                    logger.error(f"Step '{step.id}' failed: {step.error[:100]}")
                else:
                    step.status = StepStatus.COMPLETED
                    output = result.output if hasattr(result, 'output') else str(result)
                    step.result = output
                    consolidated_results[step.id] = output
                    logger.info(f"Step '{step.id}' completed")

        # Build final result
        self._plan_history.append(plan)
        if plan.id in self._active_plans:
            del self._active_plans[plan.id]

        return {
            "plan_id": plan.id,
            "status": plan.status,
            "progress": plan.progress,
            "total_steps": len(plan.steps),
            "completed": len(plan.completed_steps),
            "failed": len(plan.failed_steps),
            "results": consolidated_results,
            "summary": plan.to_summary(),
        }

    async def _execute_step(self, step: PlanStep, context: dict[str, Any]) -> Any:
        """Execute a single plan step by routing to the assigned team/agent."""
        from forge.runtime.agent import TaskResult

        # Build context from previous step results
        step_context = {}
        for dep_id in step.depends_on:
            if dep_id in context:
                step_context[f"result_from_{dep_id}"] = str(context[dep_id])[:500]

        # Route to team
        if step.assigned_team and step.assigned_team in self._teams:
            team = self._teams[step.assigned_team]
            return await team.execute(step.description, step_context or None)

        # Route to specific agent
        if step.assigned_agent:
            for agents in self._agents.values():
                if hasattr(agents, 'name') and agents.name == step.assigned_agent:
                    return await agents.execute(step.description, step_context or None)

        # Fallback: try first team
        if self._teams:
            first_team = next(iter(self._teams.values()))
            return await first_team.execute(step.description, step_context or None)

        return TaskResult(success=False, output=f"No team or agent available for step '{step.id}'")

    # ─── RE-PLANNING ──────────────────────────────────────────

    async def _replan(self, plan: TaskPlan, failed_steps: list[PlanStep]) -> None:
        """Re-plan failed steps — adjust the plan based on failures."""
        if not self._llm_client:
            # Simple retry
            for step in failed_steps:
                if step.can_retry:
                    step.status = StepStatus.PENDING
                    step.retry_count += 1
                else:
                    step.status = StepStatus.SKIPPED
            return

        failed_info = "\n".join(
            f"- {s.id}: {s.description} → ERROR: {s.error[:200]}"
            for s in failed_steps
        )

        messages = [
            {"role": "system", "content": (
                "You are a project planner. Some steps in your plan failed. "
                "Decide for each failed step: retry (with modified approach), "
                "skip (if non-critical), or create alternative steps.\n\n"
                "Respond with JSON: {\"actions\": [{\"step_id\": \"...\", "
                "\"action\": \"retry|skip|replace\", \"new_description\": \"...\"}]}"
            )},
            {"role": "user", "content": (
                f"Original task: {plan.task}\n\n"
                f"Failed steps:\n{failed_info}\n\n"
                f"Completed steps: {[s.id for s in plan.completed_steps]}\n"
                f"Decide what to do with each failed step."
            )},
        ]

        try:
            response = await self._llm_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)

            for action in data.get("actions", []):
                step = plan.get_step(action.get("step_id", ""))
                if not step:
                    continue

                act = action.get("action", "skip")
                if act == "retry" and step.can_retry:
                    step.status = StepStatus.PENDING
                    step.retry_count += 1
                    if action.get("new_description"):
                        step.description = action["new_description"]
                    logger.info(f"Re-planning: retry step '{step.id}'")
                elif act == "replace":
                    step.status = StepStatus.SKIPPED
                    new_step = PlanStep(
                        id=f"{step.id}-alt",
                        description=action.get("new_description", step.description),
                        assigned_team=step.assigned_team,
                        depends_on=step.depends_on,
                    )
                    plan.steps.append(new_step)
                    # Update any steps that depended on the original
                    for s in plan.steps:
                        if step.id in s.depends_on:
                            s.depends_on = [new_step.id if d == step.id else d for d in s.depends_on]
                    logger.info(f"Re-planning: replaced step '{step.id}' with '{new_step.id}'")
                else:
                    step.status = StepStatus.SKIPPED
                    logger.info(f"Re-planning: skipping step '{step.id}'")

        except Exception as e:
            logger.error(f"Re-planning failed: {e}. Retrying failed steps.")
            for step in failed_steps:
                if step.can_retry:
                    step.status = StepStatus.PENDING
                    step.retry_count += 1
                else:
                    step.status = StepStatus.SKIPPED

    # ─── CONVENIENCE ──────────────────────────────────────────

    async def plan_and_execute(self, task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Plan a task and immediately execute the plan."""
        plan = await self.plan(task, context)
        return await self.execute_plan(plan)

    def _get_team_roster(self) -> str:
        """Get a summary of available teams for the planning prompt."""
        if not self._teams:
            return "No teams available"
        lines = []
        for name, team in self._teams.items():
            agents = []
            if team.lead:
                agents.append(f"{team.lead.name} (lead, {team.lead.role})")
            for a in team.agents:
                agents.append(f"{a.name} ({a.role})")
            lines.append(f"- {name}: {', '.join(agents)}")
        return "\n".join(lines)

    def get_active_plans(self) -> list[dict[str, Any]]:
        """Get status of all active plans."""
        return [
            {
                "plan_id": p.id,
                "task": p.task[:80],
                "status": p.status,
                "progress": p.progress,
                "steps": len(p.steps),
            }
            for p in self._active_plans.values()
        ]

    def get_plan_history(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent plan execution history."""
        return [
            {
                "plan_id": p.id,
                "task": p.task[:80],
                "status": p.status,
                "steps": len(p.steps),
                "completed": len(p.completed_steps),
                "failed": len(p.failed_steps),
            }
            for p in self._plan_history[-limit:]
        ]
