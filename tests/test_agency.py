"""Tests for forge.runtime.agency"""

import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from forge.runtime.agent import Agent, TaskResult, AgentStatus
from forge.runtime.agency import Agency
from forge.runtime.team import Team

# Ensure Agency can be instantiated without a real API key
_FAKE_KEY = "sk-test-fake-key"


def _make_agency(**kwargs):
    """Create an Agency with a fake API key."""
    kwargs.setdefault("name", "Test")
    kwargs.setdefault("api_key", _FAKE_KEY)
    return Agency(**kwargs)


class TestAgency:
    def test_creation(self):
        agency = _make_agency(description="Test agency")
        assert agency.name == "Test"
        assert repr(agency)

    def test_add_team(self, sample_team, mock_llm_client):
        agency = _make_agency()
        agency._llm_client = mock_llm_client
        agency.add_team(sample_team)
        assert "TestTeam" in agency.teams

    def test_spawn_agent(self, mock_llm_client):
        agency = _make_agency()
        agency._llm_client = mock_llm_client
        agent = agency.spawn_agent("NewAgent", "specialist", "You are new.")
        assert agent.name == "NewAgent"

    def test_get_status(self, sample_agency):
        status = sample_agency.get_status()
        assert "name" in status
        assert "teams" in status

    @pytest.mark.asyncio
    async def test_execute_empty_task(self, sample_agency):
        result = await sample_agency.execute("")
        assert not result.success

    @pytest.mark.asyncio
    async def test_execute_bad_team(self, sample_agency):
        result = await sample_agency.execute("test", team_name="nonexistent")
        assert not result.success

    @pytest.mark.asyncio
    async def test_execute_with_team(self, sample_agency):
        result = await sample_agency.execute("test task")
        assert isinstance(result, TaskResult)

    def test_add_team_validation(self):
        agency = _make_agency()
        with pytest.raises(ValueError):
            agency.add_team(None)


class TestConcurrencyEnforcement:
    """Tests for concurrency limit enforcement via semaphore."""

    def test_set_concurrency_limit_creates_semaphore(self):
        agency = _make_agency()
        assert agency._concurrency_semaphore is None
        agency.set_concurrency_limit(3)
        assert agency.max_concurrent_tasks == 3
        assert isinstance(agency._concurrency_semaphore, asyncio.Semaphore)

    def test_set_concurrency_limit_zero_disables(self):
        agency = _make_agency()
        agency.set_concurrency_limit(5)
        assert agency._concurrency_semaphore is not None
        agency.set_concurrency_limit(0)
        assert agency._concurrency_semaphore is None
        assert agency.max_concurrent_tasks == 0

    def test_get_concurrency_status(self):
        agency = _make_agency()
        status = agency.get_concurrency_status()
        assert status == {"active_tasks": 0, "max_concurrent_tasks": 0, "limited": False}
        agency.set_concurrency_limit(4)
        status = agency.get_concurrency_status()
        assert status == {"active_tasks": 0, "max_concurrent_tasks": 4, "limited": True}

    @pytest.mark.asyncio
    async def test_limit_enforces_max_concurrent(self):
        """With limit=2, at most 2 tasks should run concurrently."""
        agency = _make_agency()
        agent = Agent(name="A", role="worker", system_prompt="test")
        agent.set_llm_client(agency._llm_client)
        agent.set_memory(agency.memory)
        agency._standalone_agents[agent.id] = agent
        agency.router.register_agent(agent)

        agency.set_concurrency_limit(2)
        peak_concurrent = 0
        lock = asyncio.Lock()

        original_execute_inner = agency._execute_inner

        async def tracked_execute(task, team_name=None, context=None, use_planner=False):
            nonlocal peak_concurrent
            async with lock:
                current = agency._active_tasks
                if current > peak_concurrent:
                    peak_concurrent = current
            await asyncio.sleep(0.05)
            return await original_execute_inner(task, team_name, context, use_planner)

        agency._execute_inner = tracked_execute

        tasks = [{"task": f"task-{i}"} for i in range(6)]
        await agency.execute_parallel(tasks)
        assert peak_concurrent <= 2

    @pytest.mark.asyncio
    async def test_unlimited_when_zero(self):
        """With limit=0 (default), all tasks run without restriction."""
        agency = _make_agency()
        agent = Agent(name="A", role="worker", system_prompt="test")
        agent.set_llm_client(agency._llm_client)
        agent.set_memory(agency.memory)
        agency._standalone_agents[agent.id] = agent
        agency.router.register_agent(agent)

        assert agency.max_concurrent_tasks == 0
        assert agency._concurrency_semaphore is None

        tasks = [{"task": f"task-{i}"} for i in range(4)]
        results = await agency.execute_parallel(tasks)
        assert len(results) == 4

    @pytest.mark.asyncio
    async def test_active_task_tracking(self):
        """_active_tasks increments during execution and decrements after."""
        agency = _make_agency()
        agent = Agent(name="A", role="worker", system_prompt="test")
        agent.set_llm_client(agency._llm_client)
        agent.set_memory(agency.memory)
        agency._standalone_agents[agent.id] = agent
        agency.router.register_agent(agent)

        assert agency._active_tasks == 0
        result = await agency.execute("simple task")
        assert isinstance(result, TaskResult)
        assert agency._active_tasks == 0

    @pytest.mark.asyncio
    async def test_dynamic_limit_change(self):
        """Changing the limit dynamically replaces the semaphore."""
        agency = _make_agency()
        agency.set_concurrency_limit(5)
        sem1 = agency._concurrency_semaphore
        agency.set_concurrency_limit(2)
        sem2 = agency._concurrency_semaphore
        assert sem1 is not sem2
        assert agency.max_concurrent_tasks == 2
