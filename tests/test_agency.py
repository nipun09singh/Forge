"""Tests for forge.runtime.agency"""

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
