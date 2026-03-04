"""Message routing between agents in an agency."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from forge.runtime.agent import Agent

logger = logging.getLogger(__name__)


@dataclass
class RoutedTask:
    """A task routed to an agent."""
    task_id: str
    content: str
    source_agent: str | None = None
    target_agent: str | None = None
    target_team: str | None = None
    priority: int = 0  # higher = more urgent
    metadata: dict[str, Any] = field(default_factory=dict)


class Router:
    """
    Routes messages and tasks between agents.
    
    Supports:
    - Direct agent-to-agent routing
    - Team-level routing (finds best agent in team)
    - Broadcast to all agents
    - Priority queue
    """

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}
        self._team_map: dict[str, list[str]] = {}  # team_name -> [agent_ids]
        self._queue: asyncio.PriorityQueue[tuple[int, RoutedTask]] = asyncio.PriorityQueue()

    def register_agent(self, agent: Agent, team: str | None = None) -> None:
        """Register an agent with the router."""
        self._agents[agent.id] = agent
        if team:
            self._team_map.setdefault(team, []).append(agent.id)

    def unregister_agent(self, agent_id: str) -> None:
        """Remove an agent from the router."""
        self._agents.pop(agent_id, None)
        for team_agents in self._team_map.values():
            if agent_id in team_agents:
                team_agents.remove(agent_id)

    async def route_to_agent(self, task: RoutedTask) -> Any:
        """Route a task directly to a specific agent."""
        if not task.target_agent or task.target_agent not in self._agents:
            raise ValueError(f"Agent '{task.target_agent}' not found.")
        agent = self._agents[task.target_agent]
        logger.info(f"Routing task '{task.task_id}' to agent '{agent.name}'")
        return await agent.execute(task.content, task.metadata)

    async def route_to_team(self, task: RoutedTask) -> Any:
        """Route a task to the best available agent in a team."""
        if not task.target_team or task.target_team not in self._team_map:
            raise ValueError(f"Team '{task.target_team}' not found.")

        team_agent_ids = self._team_map[task.target_team]
        # Find first idle agent, or fall back to first agent
        from forge.runtime.agent import AgentStatus
        for aid in team_agent_ids:
            agent = self._agents.get(aid)
            if agent and agent.status == AgentStatus.IDLE:
                logger.info(f"Routing task '{task.task_id}' to idle agent '{agent.name}' in team '{task.target_team}'")
                return await agent.execute(task.content, task.metadata)

        # No idle agent — use first agent in team
        first_id = team_agent_ids[0]
        agent = self._agents[first_id]
        logger.info(f"Routing task '{task.task_id}' to agent '{agent.name}' (no idle agents in team)")
        return await agent.execute(task.content, task.metadata)

    async def broadcast(self, task: RoutedTask) -> list[Any]:
        """Broadcast a task to all registered agents (parallel execution)."""
        tasks = []
        for agent in self._agents.values():
            tasks.append(agent.execute(task.content, task.metadata))
        return await asyncio.gather(*tasks, return_exceptions=True)

    def get_agents(self, team: str | None = None) -> list[Agent]:
        """Get all agents, optionally filtered by team."""
        if team:
            ids = self._team_map.get(team, [])
            return [self._agents[aid] for aid in ids if aid in self._agents]
        return list(self._agents.values())
