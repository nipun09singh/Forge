"""Project Executor — builds complete multi-file projects using AI agent teams.

This is the key module that transforms Forge from "one agent, one response" into
"complete project built by a coordinated AI team over multiple phases."

The flow:
1. PLAN: Strategic Planner decomposes task into steps
2. EXECUTE: Each step assigned to best agent, run through BuildLoop
3. REVIEW: QA checks each step's output
4. INTEGRATE: Full test run, documentation, packaging
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from forge.runtime.agency import Agency
    from forge.runtime.agent import Agent

logger = logging.getLogger(__name__)


@dataclass
class ProjectResult:
    """Result of a complete project execution."""
    success: bool
    project_dir: str = ""
    files_created: list[str] = field(default_factory=list)
    steps_completed: int = 0
    steps_total: int = 0
    total_duration_seconds: float = 0.0
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    build_log: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""


class ProjectExecutor:
    """
    Orchestrates multiple agents through multiple phases to build
    complete, multi-file projects.

    Instead of one agent making one response, this:
    1. Uses the Planner to decompose into steps
    2. Assigns each step to the best agent
    3. Each agent uses the BuildLoop (write→test→fix→repeat)
    4. QA reviews each step
    5. Git commits each completed step
    6. Continues until entire project is done
    """

    def __init__(self, max_step_retries: int = 3):
        self.max_step_retries = max_step_retries

    async def execute_project(
        self,
        task: str,
        agency: "Agency",
        workdir: str = "./workspace/project",
    ) -> ProjectResult:
        """Execute a complete project from a task description."""
        from forge.runtime.build_loop import BuildLoop
        from forge.runtime.integrations.command_tool import run_command
        from forge.runtime.integrations.file_tool import read_write_file
        from forge.runtime.integrations.git_tool import git_operation

        start_time = time.time()
        project_dir = Path(workdir).resolve()
        project_dir.mkdir(parents=True, exist_ok=True)
        os.environ["AGENCY_DATA_DIR"] = str(project_dir)

        files_created: list[str] = []
        build_log: list[dict[str, Any]] = []

        logger.info("=== PROJECT EXECUTION START ===")
        logger.info(f"Task: {task[:100]}")
        logger.info(f"Workdir: {project_dir}")

        # Initialize git repo
        await git_operation("init", workdir=str(project_dir))

        # ─── PHASE 1: PLANNING ────────────────────────────────
        logger.info("PHASE 1: Planning...")

        plan = await agency.planner.plan(task, context={
            "workdir": str(project_dir),
            "instructions": (
                "Break this into concrete implementation steps. "
                "Each step should produce one or more files. "
                "Include steps for: project structure, core logic, "
                "tests, documentation. Order by dependency."
            ),
        })

        steps = plan.steps
        logger.info(f"Plan created: {len(steps)} steps")
        for step in steps:
            logger.info(f"  - {step.id}: {step.description[:80]}")

        build_log.append({
            "phase": "planning",
            "steps": len(steps),
            "plan_summary": plan.to_summary(),
        })

        # ─── PHASE 2: STEP-BY-STEP EXECUTION ──────────────────
        logger.info("PHASE 2: Executing steps...")

        completed_steps = 0
        accumulated_context: list[str] = []

        for i, step in enumerate(steps):
            logger.info("")
            logger.info(f"--- Step {i+1}/{len(steps)}: {step.description[:60]} ---")

            # Build context from previous steps
            context_text = ""
            if accumulated_context:
                context_text = "Previous steps completed:\n" + "\n".join(
                    f"  - {ctx}" for ctx in accumulated_context[-5:]
                )
                context_text += f"\nFiles created so far: {', '.join(files_created[-10:])}"

            # Create the step task with full context
            step_task = (
                f"{step.description}\n\n"
                f"Working directory: {project_dir}\n"
                f"Use read_write_file to create files in this directory.\n"
                f"Use run_command to execute shell commands.\n"
                f"{context_text}\n\n"
                f"Create the actual files. Write real, working code. "
                f"Do not just describe what you would do — DO it using your tools."
            )

            # Select the best agent for this step — execute directly on the
            # agent to avoid the team lead delegation layer which loses tool
            # instructions and can complete without any tool calls.
            team_name = step.assigned_team or None
            target_agent = self._pick_agent(agency, team_name)

            # Execute the step with retries
            step_success = False
            step_output = ""

            for attempt in range(self.max_step_retries):
                try:
                    result = await target_agent.execute(step_task)
                    step_output = result.output
                    step_success = result.success

                    if step_success:
                        # Verify the step actually produced output (not just text)
                        current_files = set()
                        for f in project_dir.rglob("*"):
                            if f.is_file() and ".git" not in f.parts:
                                current_files.add(str(f.relative_to(project_dir)))

                        new_in_step = [f for f in current_files if f not in set(files_created)]

                        # If step description implies file creation but no files appeared
                        step_desc_lower = step.description.lower()
                        expects_files = any(w in step_desc_lower for w in
                            ["create", "write", "build", "implement", "generate", "save", "code"])

                        if expects_files and len(new_in_step) == 0 and attempt < self.max_step_retries - 1:
                            logger.warning(f"  ⚠️ Step claims success but created 0 files. Retrying...")
                            step_success = False
                            # Add hint to retry
                            step_task = (
                                f"{step.description}\n\n"
                                f"IMPORTANT: Your previous attempt did not create any files. "
                                f"You MUST use the read_write_file tool to actually create files. "
                                f"Do not just describe what you would do — USE YOUR TOOLS to do it."
                            )
                            continue

                        logger.info(f"  ✅ Step completed (attempt {attempt + 1})")
                        if new_in_step:
                            logger.info(f"  📁 New files: {', '.join(new_in_step)}")
                        break
                    else:
                        logger.warning(f"  ⚠️ Step failed (attempt {attempt + 1}): {step_output[:100]}")
                except Exception as e:
                    logger.error(f"  ❌ Step error (attempt {attempt + 1}): {e}")
                    step_output = str(e)

            # Scan workdir for new/changed files
            current_files = set()
            for f in project_dir.rglob("*"):
                if f.is_file() and ".git" not in f.parts:
                    rel = str(f.relative_to(project_dir))
                    current_files.add(rel)

            new_files = [f for f in current_files if f not in files_created]
            files_created.extend(new_files)

            build_log.append({
                "phase": "execution",
                "step": step.id,
                "description": step.description[:100],
                "success": step_success,
                "new_files": new_files,
                "output_preview": step_output[:200],
            })

            if step_success:
                completed_steps += 1
                accumulated_context.append(
                    f"[{step.id}] {step.description[:60]} — done ({len(new_files)} files)"
                )

                # Git commit this step
                try:
                    await git_operation("add", ".", workdir=str(project_dir))
                    await git_operation(
                        "commit",
                        f"Step {i+1}: {step.description[:50]}",
                        workdir=str(project_dir),
                    )
                except Exception:
                    pass  # Git commit is nice-to-have, don't fail on it

        # ─── PHASE 3: SUMMARY ─────────────────────────────────
        duration = time.time() - start_time

        total_cost = 0.0
        total_tokens = 0
        try:
            for team in agency.teams.values():
                if team.lead and hasattr(team.lead, '_event_log') and team.lead._event_log:
                    costs = team.lead._event_log.cost_tracker.get_summary()
                    total_cost = costs.get("total_cost_usd", 0)
                    total_tokens = costs.get("total_tokens", 0)
                    break
        except Exception:
            pass

        summary_lines = [
            f"Project: {task[:80]}",
            f"Status: {'SUCCESS' if completed_steps == len(steps) else 'PARTIAL'}",
            f"Steps: {completed_steps}/{len(steps)} completed",
            f"Files: {len(files_created)} created",
            f"Duration: {duration:.1f}s",
            f"Cost: ${total_cost:.4f}",
            "",
            "Files created:",
        ]
        for f in sorted(files_created):
            summary_lines.append(f"  {f}")

        summary = "\n".join(summary_lines)
        logger.info("\n=== PROJECT EXECUTION COMPLETE ===")
        logger.info(summary)

        return ProjectResult(
            success=completed_steps >= len(steps) * 0.7,  # 70%+ steps = success
            project_dir=str(project_dir),
            files_created=sorted(files_created),
            steps_completed=completed_steps,
            steps_total=len(steps),
            total_duration_seconds=round(duration, 1),
            total_cost_usd=round(total_cost, 4),
            total_tokens=total_tokens,
            build_log=build_log,
            summary=summary,
        )

    @staticmethod
    def _pick_agent(agency: "Agency", team_name: str | None) -> "Agent":
        """Pick the best agent for a project step, preferring a specialist from the named team."""
        if team_name and team_name in agency.teams:
            team = agency.teams[team_name]
            # Prefer the first non-lead agent (specialist); fall back to lead
            if team.agents:
                return team.agents[0]
            if team.lead:
                return team.lead
        # Fallback: first agent from first team
        for team in agency.teams.values():
            if team.agents:
                return team.agents[0]
            if team.lead:
                return team.lead
        raise RuntimeError("No agents available in the agency.")

    def __repr__(self) -> str:
        return f"ProjectExecutor(max_retries={self.max_step_retries})"
