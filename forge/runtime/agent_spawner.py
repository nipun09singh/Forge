"""Agent Spawner — autonomously creates new specialist agents when gaps are detected.

When the system notices patterns of poorly-handled requests, it:
1. Clusters the failures to identify gaps
2. Designs a new specialist agent (name, role, prompt, tools)
3. Creates and deploys it into the running agency
4. The agency grows its own workforce without human intervention.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from forge.runtime.agency import Agency

logger = logging.getLogger(__name__)


@dataclass
class SpawnedAgent:
    """Record of an autonomously spawned agent."""
    id: str = field(default_factory=lambda: f"spawn-{uuid.uuid4().hex[:8]}")
    name: str = ""
    role: str = "specialist"
    reason: str = ""
    gap_description: str = ""
    system_prompt: str = ""
    team: str = ""
    spawned_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())



class AgentSpawner:
    """
    Autonomously creates new specialist agents when performance gaps are detected.
    
    Process:
    1. Analyze poorly-handled requests from PerformanceTracker
    2. Cluster failures to identify recurring themes
    3. Use LLM to design a new specialist agent for the gap
    4. Create the agent and add to the agency
    5. Monitor the new agent's performance
    """

    def __init__(
        self,
        performance_tracker: Any = None,
        llm_client: Any = None,
        model: str = "gpt-4o",
        gap_threshold: int = 3,  # Number of similar failures before spawning
    ):
        self._tracker = performance_tracker
        self._llm_client = llm_client
        self.model = model
        self.gap_threshold = gap_threshold
        self._spawned: list[SpawnedAgent] = []

    def set_infrastructure(self, tracker=None, llm_client=None):
        """Wire to agency infrastructure."""
        if tracker: self._tracker = tracker
        if llm_client: self._llm_client = llm_client

    async def check_and_spawn(self, agency: "Agency") -> list[SpawnedAgent]:
        """
        Check for gaps and spawn new agents if needed.
        
        Returns list of newly spawned agents.
        """
        if not self._tracker or not self._llm_client:
            return []

        # Get failure patterns
        failures = self._tracker.get_failure_patterns(limit=30)
        if len(failures) < self.gap_threshold:
            return []

        # Ask LLM to identify gaps
        existing_agents = []
        for team in agency.teams.values():
            if team.lead:
                existing_agents.append(f"{team.lead.name} ({team.lead.role})")
            for a in team.agents:
                existing_agents.append(f"{a.name} ({a.role})")

        prompt = (
            "You are an organizational designer for an AI agency.\n\n"
            f"Current agents: {', '.join(existing_agents)}\n\n"
            f"Recent failures ({len(failures)} tasks):\n"
            + "\n".join(f"  - {f.get('task', '')[:80]}" for f in failures[:10])
            + "\n\n"
            "Are there recurring failure patterns that suggest a NEW specialist agent is needed?\n"
            "If yes, design ONE new agent. If no, respond with empty improvements.\n\n"
            "Return JSON: {\"needed\": true/false, \"agent\": {\"name\": \"...\", \"role\": \"specialist\", "
            "\"title\": \"...\", \"system_prompt\": \"...(3 paragraphs)...\", \"team\": \"...\", "
            "\"reason\": \"why this agent is needed\"}}"
        )

        try:
            response = await self._llm_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
            )
            content = response.choices[0].message.content or "{}"
            if content.strip().startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.strip().endswith("```"):
                    content = content.strip()[:-3]

            data = json.loads(content)
        except Exception as e:
            logger.error(f"Agent spawner analysis failed: {e}")
            return []

        if not data.get("needed", False):
            logger.info("Agent spawner: no new agents needed")
            return []

        # Spawn the new agent
        agent_spec = data.get("agent", {})
        if not agent_spec.get("name"):
            return []

        # Check if we already spawned an agent with this name
        existing_names = {s.name for s in self._spawned}
        if agent_spec["name"] in existing_names:
            logger.info(f"Agent '{agent_spec['name']}' already spawned, skipping")
            return []

        # Create the agent
        new_agent = agency.spawn_agent(
            name=agent_spec["name"],
            role=agent_spec.get("role", "specialist"),
            system_prompt=agent_spec.get("system_prompt", f"You are {agent_spec['name']}."),
            team_name=agent_spec.get("team"),
        )

        record = SpawnedAgent(
            name=agent_spec["name"],
            role=agent_spec.get("role", "specialist"),
            reason=agent_spec.get("reason", "Gap detected"),
            gap_description=data.get("gap_description", ""),
            system_prompt=agent_spec.get("system_prompt", "")[:200],
            team=agent_spec.get("team", ""),
        )
        self._spawned.append(record)

        logger.info(f"SPAWNED NEW AGENT: {record.name} ({record.role}) — Reason: {record.reason}")

        return [record]

    def get_spawned_agents(self) -> list[dict[str, Any]]:
        """Get all autonomously spawned agents."""
        return [
            {
                "id": s.id,
                "name": s.name,
                "role": s.role,
                "reason": s.reason,
                "team": s.team,
                "spawned_at": s.spawned_at,
            }
            for s in self._spawned
        ]

    def get_stats(self) -> dict[str, Any]:
        """Get spawner statistics."""
        return {
            "total_spawned": len(self._spawned),
            "agents": [s.name for s in self._spawned],
        }

    def __repr__(self) -> str:
        return f"AgentSpawner(spawned={len(self._spawned)})"
