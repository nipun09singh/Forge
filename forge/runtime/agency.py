"""Agency — the top-level container managing all agents and teams."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from openai import AsyncOpenAI

from forge.runtime.agent import Agent, TaskResult
from forge.runtime.memory import SharedMemory
from forge.runtime.router import Router
from forge.runtime.team import Team
from forge.runtime.planner import Planner
from forge.runtime.messages import AgentMessage, MessageType, MessageBus
from forge.runtime.checkpointing import CheckpointStore
from forge.runtime.scheduler import Scheduler, TaskSchedule
from forge.runtime.workspace import WorkspaceManager
from forge.runtime.project_executor import ProjectExecutor, ProjectResult
from forge.runtime.inbound import InboundProcessor
from forge.runtime.self_evolution import SelfEvolution
from forge.runtime.agent_spawner import AgentSpawner
from forge.runtime.stress_lab import StressLab
from forge.runtime.orchestrator import OrchestratorAgent

logger = logging.getLogger(__name__)


class Agency:
    """
    An AI Agency — a collection of agent teams that work together.
    
    The Agency:
    - Manages agent lifecycle
    - Provides shared resources (LLM client, memory)
    - Routes tasks to appropriate teams/agents
    - Supports unlimited dynamic agent spawning
    """

    def __init__(
        self,
        name: str,
        description: str = "",
        model: str = "gpt-4",
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self.name = name
        self.description = description
        self.model = model
        self.memory = SharedMemory()
        self.router = Router()
        self.teams: dict[str, Team] = {}
        self._standalone_agents: dict[str, Agent] = {}

        self.message_bus = MessageBus()
        self.scheduler = Scheduler(execute_fn=self.execute)
        self.workspace_manager = WorkspaceManager(base_dir="./workspace")
        self.inbound = InboundProcessor(execute_fn=self.execute)
        self.self_evolution = SelfEvolution()
        self.agent_spawner = AgentSpawner()
        self.project_executor = ProjectExecutor()
        self.stress_lab = StressLab(agency=self)
        self.orchestrator = OrchestratorAgent(model=model)

        # Strategic plannerfor complex task decomposition
        self.planner = Planner(model=model)

        self.max_concurrent_tasks: int = 0
        self._checkpoint_store: CheckpointStore | None = None

        # Initialize LLM client (graceful if no API key — fails only on actual LLM calls)
        client_kwargs: dict[str, Any] = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        if base_url:
            client_kwargs["base_url"] = base_url
        if not api_key and not os.getenv("OPENAI_API_KEY"):
            client_kwargs["api_key"] = "not-set"  # Placeholder — will fail on actual LLM call, not on init
        self._llm_client = AsyncOpenAI(**client_kwargs)
        self.planner.set_llm_client(self._llm_client)
        self.orchestrator.set_llm_client(self._llm_client)

    def add_team(self, team: Team) -> None:
        """Add a team to the agency."""
        if not team or not hasattr(team, 'name'):
            raise ValueError("team must be a valid Team instance with a name.")
        self.teams[team.name] = team
        team.memory = self.memory  # Share agency-wide memory

        # Register all team agents with router
        if team.lead:
            team.lead.set_llm_client(self._llm_client)
            team.lead.set_memory(self.memory)
            self.router.register_agent(team.lead, team=team.name)
        for agent in team.agents:
            agent.set_llm_client(self._llm_client)
            agent.set_memory(self.memory)
            self.router.register_agent(agent, team=team.name)

        # Ensure all agents have primitive tools for real execution
        try:
            from forge.runtime.integrations import BuiltinToolkit
            builtin = BuiltinToolkit.all_tools()
            all_agents = list(team.agents)
            if team.lead:
                all_agents.append(team.lead)
            for agent in all_agents:
                if not agent.tool_registry.list_tools():
                    for tool in builtin:
                        agent.tool_registry.register(tool)
        except ImportError:
            pass

        # Keep planner aware of all teams
        self.planner.set_teams(self.teams)

    def add_agent(self, agent: Agent, team_name: str | None = None) -> None:
        """Add a standalone agent or assign to a team."""
        agent.set_llm_client(self._llm_client)
        agent.set_memory(self.memory)

        if team_name and team_name in self.teams:
            self.teams[team_name].add_agent(agent)
            self.router.register_agent(agent, team=team_name)
        else:
            self._standalone_agents[agent.id] = agent
            self.router.register_agent(agent)

    def spawn_agent(
        self,
        name: str,
        role: str,
        system_prompt: str,
        team_name: str | None = None,
    ) -> Agent:
        """Dynamically spawn a new agent (unlimited scaling)."""
        agent = Agent(name=name, role=role, system_prompt=system_prompt, model=self.model)
        self.add_agent(agent, team_name)
        logger.info(f"Spawned agent '{name}' (role: {role})")
        return agent

    async def execute(self, task: str, team_name: str | None = None, context: dict[str, Any] | None = None, use_planner: bool = False) -> TaskResult:
        """
        Execute a task.
        
        If use_planner=True, decomposes the task into a plan first.
        If team_name is given, delegates to that team.
        Otherwise, uses the first team or a standalone agent.
        """
        logger.info(f"Agency '{self.name}' executing: {task[:80]}...")

        if not task or not isinstance(task, str) or not task.strip():
            return TaskResult(success=False, output="Task must be a non-empty string.")

        if team_name and team_name not in self.teams:
            available = list(self.teams.keys())
            return TaskResult(success=False, output=f"Team '{team_name}' not found. Available teams: {available}")

        # Route through planner for complex multi-step tasks
        if use_planner and self.planner:
            plan_result = await self.planner.plan_and_execute(task, context)
            return TaskResult(
                success=plan_result["status"] == "completed",
                output=plan_result.get("summary", "Plan execution finished."),
                data=plan_result,
            )

        if team_name and team_name in self.teams:
            return await self.teams[team_name].execute(task, context)

        # Auto-route: try first team, then standalone agents
        if self.teams:
            first_team = next(iter(self.teams.values()))
            return await first_team.execute(task, context)

        if self._standalone_agents:
            first_agent = next(iter(self._standalone_agents.values()))
            return await first_agent.execute(task, context)

        return TaskResult(success=False, output="No agents or teams available.")

    async def execute_parallel(self, tasks: list[dict[str, Any]]) -> list[TaskResult]:
        """Execute multiple tasks in parallel across teams."""
        coros = []
        for t in tasks:
            coros.append(self.execute(
                task=t["task"],
                team_name=t.get("team"),
                context=t.get("context"),
            ))
        return await asyncio.gather(*coros, return_exceptions=True)

    async def execute_project(self, task: str, workdir: str = "./workspace/project") -> dict[str, Any]:
        """
        Execute a complex project — plans, builds multi-file output, tests, commits.
        
        This is "project mode" — for tasks that require multiple files,
        builds, tests, and iterative debugging. Uses the full agent team.
        """
        result = await self.project_executor.execute_project(
            task=task,
            agency=self,
            workdir=workdir,
        )
        return {
            "success": result.success,
            "project_dir": result.project_dir,
            "files_created": result.files_created,
            "steps_completed": result.steps_completed,
            "steps_total": result.steps_total,
            "duration_seconds": result.total_duration_seconds,
            "cost_usd": result.total_cost_usd,
            "summary": result.summary,
        }

    async def orchestrate(self, task: str, workdir: str = "./workspace/project") -> dict[str, Any]:
        """
        Build a complete project using the OrchestratorAgent.
        
        This is the CORRECT way to build projects — one intelligent agent loop
        with all tools, not a multi-agent pipeline.
        """
        self.orchestrator.set_llm_client(self._llm_client)
        result = await self.orchestrator.build(task=task, workdir=workdir)
        return {
            "success": result.success,
            "project_dir": result.project_dir,
            "files_created": result.files_created,
            "iterations": result.iterations,
            "duration_seconds": result.duration_seconds,
            "summary": result.summary,
        }

    async def plan(self, task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Plan a complex task using the strategic planner."""
        plan = await self.planner.plan(task, context)
        return {"plan_id": plan.id, "summary": plan.to_summary(), "steps": len(plan.steps)}

    def enable_checkpointing(self, db_path: str = "./data/checkpoints.db") -> None:
        """Enable state checkpointing for fault tolerance and resumability."""
        self._checkpoint_store = CheckpointStore(db_path)

    def checkpoint(self, checkpoint_id: str | None = None) -> str:
        """
        Save the entire agency state to a checkpoint.

        Returns the checkpoint ID for later restoration.
        """
        if not self._checkpoint_store:
            raise RuntimeError("Checkpointing not enabled. Call enable_checkpointing() first.")

        state: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "model": self.model,
            "agents": {},
            "teams": list(self.teams.keys()),
        }

        # Save each agent's state
        for team_name, team in self.teams.items():
            if team.lead:
                state["agents"][f"{team_name}:lead:{team.lead.name}"] = team.lead.save_state()
            for agent in team.agents:
                state["agents"][f"{team_name}:agent:{agent.name}"] = agent.save_state()

        for agent_id, agent in self._standalone_agents.items():
            state["agents"][f"standalone:{agent.name}"] = agent.save_state()

        return self._checkpoint_store.save("agency", self.name, state, checkpoint_id=checkpoint_id)

    def restore(self, checkpoint_id: str | None = None) -> bool:
        """
        Restore agency state from a checkpoint.

        If no checkpoint_id given, restores from the latest checkpoint.
        """
        if not self._checkpoint_store:
            raise RuntimeError("Checkpointing not enabled. Call enable_checkpointing() first.")

        if checkpoint_id:
            cp = self._checkpoint_store.load(checkpoint_id)
        else:
            cp = self._checkpoint_store.load_latest("agency", self.name)

        if not cp:
            return False

        state = cp["state"]
        agent_states = state.get("agents", {})

        # Restore each agent's state
        for team_name, team in self.teams.items():
            if team.lead:
                key = f"{team_name}:lead:{team.lead.name}"
                if key in agent_states:
                    team.lead.load_state(agent_states[key])
            for agent in team.agents:
                key = f"{team_name}:agent:{agent.name}"
                if key in agent_states:
                    agent.load_state(agent_states[key])

        for agent_id, agent in self._standalone_agents.items():
            key = f"standalone:{agent.name}"
            if key in agent_states:
                agent.load_state(agent_states[key])

        logger.info(f"Restored agency '{self.name}' from checkpoint '{cp['id']}'")
        return True

    def list_checkpoints(self, limit: int = 20) -> list[dict]:
        """List available checkpoints for this agency."""
        if not self._checkpoint_store:
            return []
        return self._checkpoint_store.list_checkpoints(entity_type="agency", entity_name=self.name, limit=limit)

    def get_status(self) -> dict[str, Any]:
        """Get a status summary of the agency."""
        teams_info = {}
        for name, team in self.teams.items():
            agents = []
            if team.lead:
                agents.append({"name": team.lead.name, "role": team.lead.role, "status": team.lead.status.value})
            for a in team.agents:
                agents.append({"name": a.name, "role": a.role, "status": a.status.value})
            teams_info[name] = agents

        standalone = [
            {"name": a.name, "role": a.role, "status": a.status.value}
            for a in self._standalone_agents.values()
        ]

        return {
            "name": self.name,
            "teams": teams_info,
            "standalone_agents": standalone,
            "memory_entries": len(self.memory._store),
        }

    def set_concurrency_limit(self, max_tasks: int) -> None:
        """Set maximum concurrent task executions."""
        self.max_concurrent_tasks = max_tasks

    def __repr__(self) -> str:
        total = sum(len(t.agents) + (1 if t.lead else 0) for t in self.teams.values()) + len(self._standalone_agents)
        return f"Agency(name={self.name!r}, teams={len(self.teams)}, agents={total})"
