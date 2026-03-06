"""Tests for forge.runtime.agent_spawner."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from forge.runtime.agent_spawner import AgentSpawner, SpawnedAgent
from forge.runtime.improvement import PerformanceTracker, TaskMetric
from forge.runtime.agency import Agency


class TestAgentSpawnerInit:
    """Tests for AgentSpawner initialization."""

    def test_init_defaults(self):
        spawner = AgentSpawner()
        assert spawner._spawned == []

    def test_init_with_tracker(self):
        tracker = PerformanceTracker()
        spawner = AgentSpawner(performance_tracker=tracker)
        assert spawner._tracker is tracker


class TestCheckAndSpawn:
    """Tests for check_and_spawn method."""

    @pytest.mark.asyncio
    async def test_returns_empty_without_tracker(self):
        spawner = AgentSpawner()
        agency = MagicMock(spec=Agency)
        result = await spawner.check_and_spawn(agency)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_without_llm_client(self):
        spawner = AgentSpawner(performance_tracker=PerformanceTracker())
        agency = MagicMock(spec=Agency)
        result = await spawner.check_and_spawn(agency)
        assert result == []


class TestSpawnedAgent:
    """Tests for SpawnedAgent dataclass."""

    def test_creation(self):
        sa = SpawnedAgent(
            name="NewAgent",
            role="specialist",
            reason="Gap in customer support",
        )
        assert sa.name == "NewAgent"
        assert sa.role == "specialist"
        assert sa.reason == "Gap in customer support"


class TestSpawnerStats:
    """Tests for stats and history."""

    def test_get_spawned_agents_empty(self):
        spawner = AgentSpawner()
        assert spawner.get_spawned_agents() == []

    def test_get_stats(self):
        spawner = AgentSpawner()
        stats = spawner.get_stats()
        assert "total_spawned" in stats
        assert stats["total_spawned"] == 0
