"""Team coordination for groups of agents working together."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from forge.runtime.agent import Agent, AgentStatus, TaskResult
from forge.runtime.memory import SharedMemory

logger = logging.getLogger(__name__)


@dataclass
class TeamTask:
    """A task assigned to a team."""
    id: str = field(default_factory=lambda: f"task-{uuid.uuid4().hex[:8]}")
    description: str = ""
    assigned_to: str | None = None
    status: str = "pending"
    result: TaskResult | None = None


class Team:
    """
    A team of agents that collaborate on tasks.
    
    Features:
    - Team lead delegates work to specialists
    - Dynamic agent spawning for scaling
    - Parallel execution of independent subtasks
    - Shared memory across team members
    """

    def __init__(
        self,
        name: str,
        lead: Agent | None = None,
        agents: list[Agent] | None = None,
        shared_memory: SharedMemory | None = None,
    ):
        self.name = name
        self.lead = lead
        self.agents: list[Agent] = agents or []
        self.memory = shared_memory or SharedMemory()
        self._task_log: list[TeamTask] = []

        # Share memory with all team members
        if self.lead:
            self.lead.set_memory(self.memory)
        for agent in self.agents:
            agent.set_memory(self.memory)

    def add_agent(self, agent: Agent) -> None:
        """Add an agent to the team."""
        agent.set_memory(self.memory)
        self.agents.append(agent)

    def remove_agent(self, agent_id: str) -> None:
        """Remove an agent from the team."""
        self.agents = [a for a in self.agents if a.id != agent_id]

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> TaskResult:
        """
        Execute a task as a team.
        
        If a lead exists, the lead decides how to delegate.
        Otherwise, all agents work on the task in parallel.
        """
        logger.info(f"Team '{self.name}' executing: {task[:80]}...")

        if self.lead:
            return await self._led_execution(task, context)
        return await self._parallel_execution(task, context)

    async def _led_execution(self, task: str, context: dict[str, Any] | None) -> TaskResult:
        """Lead agent coordinates the team."""
        assert self.lead is not None

        team_info = "\n".join(
            f"- {a.name} ({a.role})" for a in self.agents
        )
        delegation_prompt = (
            f"You are the team lead of '{self.name}'. Your team members:\n"
            f"{team_info}\n\n"
            f"Task: {task}\n\n"
            f"Coordinate your team. You can delegate subtasks. "
            f"Provide the final consolidated result."
        )

        # Give the lead delegation tools
        from forge.runtime.tools import Tool, ToolParameter
        import json

        async def delegate_to_agent(agent_name: str, subtask: str) -> str:
            """Delegate a subtask to a specific team member."""
            agent = next((a for a in self.agents if a.name == agent_name), None)
            if not agent:
                return f"Agent '{agent_name}' not found in team."
            result = await agent.execute(subtask, context)
            tt = TeamTask(description=subtask, assigned_to=agent_name, status="done", result=result)
            self._task_log.append(tt)
            self.memory.store(f"team:{self.name}:{agent_name}:result", result.output, author=agent_name)
            return result.output

        async def delegate_parallel(tasks_json: str) -> str:
            """Delegate multiple subtasks in parallel. Input: JSON list of {agent_name, subtask}."""
            try:
                tasks = json.loads(tasks_json)
            except json.JSONDecodeError:
                return "Invalid JSON. Provide a list of {agent_name, subtask} objects."
            
            coros = []
            for t in tasks:
                coros.append(delegate_to_agent(t["agent_name"], t["subtask"]))
            results = await asyncio.gather(*coros, return_exceptions=True)
            return "\n---\n".join(str(r) for r in results)

        delegate_tool = Tool(
            name="delegate_to_agent",
            description="Delegate a subtask to a specific team member by name.",
            parameters=[
                ToolParameter(name="agent_name", type="string", description="Name of the team member"),
                ToolParameter(name="subtask", type="string", description="The subtask to delegate"),
            ],
            _fn=delegate_to_agent,
        )
        parallel_tool = Tool(
            name="delegate_parallel",
            description="Delegate multiple subtasks to team members in parallel. Provide JSON list of {agent_name, subtask}.",
            parameters=[
                ToolParameter(name="tasks_json", type="string", description='JSON list: [{"agent_name": "...", "subtask": "..."}]'),
            ],
            _fn=delegate_parallel,
        )

        self.lead.tool_registry.register(delegate_tool)
        self.lead.tool_registry.register(parallel_tool)

        return await self.lead.execute(delegation_prompt, context)

    async def _parallel_execution(self, task: str, context: dict[str, Any] | None) -> TaskResult:
        """All agents work on the task independently in parallel."""
        coros = [agent.execute(task, context) for agent in self.agents]
        results = await asyncio.gather(*coros, return_exceptions=True)

        outputs = []
        all_success = True
        for agent, result in zip(self.agents, results):
            if isinstance(result, Exception):
                outputs.append(f"[{agent.name}] ERROR: {result}")
                all_success = False
            else:
                outputs.append(f"[{agent.name}] {result.output}")
                if not result.success:
                    all_success = False

        combined = "\n\n".join(outputs)
        self.memory.store(f"team:{self.name}:combined_result", combined, author=self.name)
        return TaskResult(success=all_success, output=combined)

    def __repr__(self) -> str:
        count = len(self.agents) + (1 if self.lead else 0)
        return f"Team(name={self.name!r}, agents={count})"
