"""Tests for forge.runtime.team"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from forge.runtime.agent import Agent, TaskResult
from forge.runtime.team import Team
from forge.runtime.memory import SharedMemory


class TestTeam:
    def test_creation(self):
        team = Team(name="Test Team")
        assert team.name == "Test Team"
        assert repr(team)

    def test_add_agent(self, sample_agent_with_llm):
        team = Team(name="Test")
        team.add_agent(sample_agent_with_llm)
        assert len(team.agents) == 1

    def test_remove_agent(self, sample_agent_with_llm):
        team = Team(name="Test", agents=[sample_agent_with_llm])
        team.remove_agent(sample_agent_with_llm.id)
        assert len(team.agents) == 0

    def test_shared_memory(self, sample_agent_with_llm):
        mem = SharedMemory()
        team = Team(name="Test", agents=[sample_agent_with_llm], shared_memory=mem)
        assert sample_agent_with_llm.memory is mem

    @pytest.mark.asyncio
    async def test_parallel_execution(self, mock_llm_client):
        a1 = Agent(name="A1", role="spec", system_prompt="Test")
        a2 = Agent(name="A2", role="spec", system_prompt="Test")
        a1.set_llm_client(mock_llm_client)
        a2.set_llm_client(mock_llm_client)
        team = Team(name="Parallel", agents=[a1, a2])
        result = await team.execute("test task")
        assert result.output  # Contains results from both agents
