"""Tests for forge.runtime.router."""
import pytest
from unittest.mock import AsyncMock, MagicMock, PropertyMock

from forge.runtime.router import Router, RoutedTask
from forge.runtime.agent import AgentStatus


def _make_agent(name="TestAgent", agent_id="agent-1", status=AgentStatus.IDLE):
    """Create a mock agent for router tests."""
    agent = MagicMock()
    agent.name = name
    agent.id = agent_id
    agent.status = status
    agent.execute = AsyncMock(return_value="result")
    return agent


class TestRouterInit:
    def test_init_empty(self):
        router = Router()
        assert router._agents == {}
        assert router._team_map == {}

    def test_get_agents_empty(self):
        router = Router()
        assert router.get_agents() == []


class TestRegisterAgent:
    def test_register_agent_no_team(self):
        router = Router()
        agent = _make_agent()
        router.register_agent(agent)
        assert agent.id in router._agents
        assert router.get_agents() == [agent]

    def test_register_agent_with_team(self):
        router = Router()
        agent = _make_agent()
        router.register_agent(agent, team="backend")
        assert "backend" in router._team_map
        assert agent.id in router._team_map["backend"]

    def test_register_multiple_agents_same_team(self):
        router = Router()
        a1 = _make_agent(name="A1", agent_id="a1")
        a2 = _make_agent(name="A2", agent_id="a2")
        router.register_agent(a1, team="backend")
        router.register_agent(a2, team="backend")
        assert len(router._team_map["backend"]) == 2

    def test_unregister_agent(self):
        router = Router()
        agent = _make_agent()
        router.register_agent(agent, team="team1")
        router.unregister_agent(agent.id)
        assert agent.id not in router._agents
        assert agent.id not in router._team_map.get("team1", [])

    def test_get_agents_by_team(self):
        router = Router()
        a1 = _make_agent(name="A1", agent_id="a1")
        a2 = _make_agent(name="A2", agent_id="a2")
        router.register_agent(a1, team="frontend")
        router.register_agent(a2, team="backend")
        frontend = router.get_agents(team="frontend")
        assert len(frontend) == 1
        assert frontend[0].name == "A1"


class TestRouteTask:
    @pytest.mark.asyncio
    async def test_route_to_agent(self):
        router = Router()
        agent = _make_agent(agent_id="target-1")
        router.register_agent(agent)
        task = RoutedTask(task_id="t1", content="do work", target_agent="target-1")
        result = await router.route_to_agent(task)
        agent.execute.assert_called_once_with("do work", {})
        assert result == "result"

    @pytest.mark.asyncio
    async def test_route_to_missing_agent_raises(self):
        router = Router()
        task = RoutedTask(task_id="t1", content="do work", target_agent="ghost")
        with pytest.raises(ValueError, match="not found"):
            await router.route_to_agent(task)

    @pytest.mark.asyncio
    async def test_route_to_team(self):
        router = Router()
        agent = _make_agent(agent_id="team-agent")
        router.register_agent(agent, team="ops")
        task = RoutedTask(task_id="t2", content="team task", target_team="ops")
        result = await router.route_to_team(task)
        agent.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_route_to_missing_team_raises(self):
        router = Router()
        task = RoutedTask(task_id="t2", content="team task", target_team="ghost")
        with pytest.raises(ValueError, match="not found"):
            await router.route_to_team(task)

    @pytest.mark.asyncio
    async def test_broadcast(self):
        router = Router()
        a1 = _make_agent(agent_id="b1")
        a2 = _make_agent(agent_id="b2")
        router.register_agent(a1)
        router.register_agent(a2)
        task = RoutedTask(task_id="t3", content="broadcast")
        results = await router.broadcast(task)
        assert len(results) == 2
        a1.execute.assert_called_once()
        a2.execute.assert_called_once()


class TestRoutedTask:
    def test_defaults(self):
        task = RoutedTask(task_id="t1", content="do stuff")
        assert task.priority == 0
        assert task.metadata == {}
        assert task.source_agent is None
        assert task.target_agent is None
        assert task.target_team is None
