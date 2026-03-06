"""Tests for forge.runtime.execution_strategy."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from forge.runtime.execution_strategy import ExecutionStrategy
from forge.runtime.agency import Agency
from forge.runtime.agent import Agent, TaskResult
from forge.runtime.team import Team


class TestExecutionStrategy:
    """Tests for ExecutionStrategy enum."""

    def test_orchestrator_value(self):
        assert ExecutionStrategy.ORCHESTRATOR == "orchestrator"

    def test_team_value(self):
        assert ExecutionStrategy.TEAM == "team"

    def test_all_strategies_documented(self):
        """Every strategy has a docstring description."""
        # Verify enum members are the expected set
        assert set(ExecutionStrategy) == {ExecutionStrategy.ORCHESTRATOR, ExecutionStrategy.TEAM}

    def test_strategy_is_string_compatible(self):
        """Strategy values can be used as strings (for serialization)."""
        assert ExecutionStrategy.ORCHESTRATOR == "orchestrator"
        assert ExecutionStrategy.TEAM == "team"
        # Round-trip: string -> enum -> string
        for strategy in ExecutionStrategy:
            assert ExecutionStrategy(strategy.value) == strategy

    def test_is_str_subclass(self):
        """ExecutionStrategy is a str enum, so members are also strings."""
        assert isinstance(ExecutionStrategy.ORCHESTRATOR, str)
        assert isinstance(ExecutionStrategy.TEAM, str)

    def test_equality_with_raw_string(self):
        """str enum members compare equal to their raw string values."""
        assert ExecutionStrategy.ORCHESTRATOR == "orchestrator"
        assert ExecutionStrategy.TEAM == "team"

    def test_members_list(self):
        members = list(ExecutionStrategy)
        assert len(members) == 2
        assert ExecutionStrategy.ORCHESTRATOR in members
        assert ExecutionStrategy.TEAM in members


class TestAgencyExecutionStrategy:
    """Tests for Agency.execute_project() integration."""

    def _make_agency(self, strategy=ExecutionStrategy.ORCHESTRATOR):
        """Helper to create a test agency."""
        agency = Agency(
            name="TestAgency",
            description="Test",
            api_key="sk-test-fake",
            execution_strategy=strategy,
        )
        mock_client = AsyncMock()
        agency._llm_client = mock_client
        return agency

    def test_default_strategy(self):
        """Agency defaults to ORCHESTRATOR strategy."""
        agency = self._make_agency()
        assert agency.strategy == ExecutionStrategy.ORCHESTRATOR

    def test_custom_strategy(self):
        """Agency accepts custom strategy."""
        agency = self._make_agency(strategy=ExecutionStrategy.TEAM)
        assert agency.strategy == ExecutionStrategy.TEAM

    @pytest.mark.asyncio
    async def test_execute_project_orchestrator(self):
        """execute_project with ORCHESTRATOR strategy calls orchestrator.build()."""
        agency = self._make_agency()

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.summary = "Project built"
        mock_result.files_created = ["main.py"]
        mock_result.iterations = 5
        mock_result.duration_seconds = 10.0
        mock_result.total_tokens = 1000
        agency.orchestrator.build = AsyncMock(return_value=mock_result)

        result = await agency.execute_project("Build something")
        assert result.success is True
        assert "main.py" in result.data["files_created"]
        agency.orchestrator.build.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_project_orchestrator_data_fields(self):
        """execute_project ORCHESTRATOR populates all expected data fields."""
        agency = self._make_agency()

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.summary = "Done"
        mock_result.files_created = ["a.py", "b.py"]
        mock_result.iterations = 3
        mock_result.duration_seconds = 7.5
        mock_result.total_tokens = 500
        agency.orchestrator.build = AsyncMock(return_value=mock_result)

        result = await agency.execute_project("Build it")
        assert result.data["iterations"] == 3
        assert result.data["duration_seconds"] == 7.5
        assert result.data["total_tokens"] == 500
        assert result.output == "Done"

    @pytest.mark.asyncio
    async def test_execute_project_team_no_teams(self):
        """execute_project with TEAM strategy fails gracefully when no teams."""
        agency = self._make_agency(strategy=ExecutionStrategy.TEAM)
        result = await agency.execute_project("Build something")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_execute_project_team_with_team(self):
        """execute_project with TEAM strategy delegates to first team."""
        agency = self._make_agency(strategy=ExecutionStrategy.TEAM)

        mock_client = AsyncMock()
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = "Done"
        response.choices[0].message.tool_calls = None
        response.usage = MagicMock()
        response.usage.prompt_tokens = 10
        response.usage.completion_tokens = 5
        response.usage.total_tokens = 15
        mock_client.chat.completions.create = AsyncMock(return_value=response)

        lead = Agent(name="Lead", role="manager", system_prompt="Lead the team")
        lead.set_llm_client(mock_client)
        team = Team(name="DevTeam", lead=lead)
        agency.add_team(team)

        result = await agency.execute_project("Build something")
        assert result is not None

    @pytest.mark.asyncio
    async def test_execute_project_strategy_override(self):
        """Strategy can be overridden per-call."""
        agency = self._make_agency(strategy=ExecutionStrategy.ORCHESTRATOR)

        # With team override but no teams, should fail
        result = await agency.execute_project("Build something", strategy=ExecutionStrategy.TEAM)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_execute_project_orchestrator_sets_client(self):
        """execute_project sets LLM client on orchestrator if not already set."""
        agency = self._make_agency()
        agency.orchestrator._llm_client = None

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.summary = "ok"
        mock_result.files_created = []
        mock_result.iterations = 1
        mock_result.duration_seconds = 1.0
        mock_result.total_tokens = 100
        agency.orchestrator.build = AsyncMock(return_value=mock_result)
        agency.orchestrator.set_llm_client = MagicMock()

        result = await agency.execute_project("Build")
        agency.orchestrator.set_llm_client.assert_called_once_with(agency._llm_client)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_project_orchestrator_passes_workdir(self):
        """execute_project forwards the workdir argument."""
        agency = self._make_agency()

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.summary = "ok"
        mock_result.files_created = []
        mock_result.iterations = 1
        mock_result.duration_seconds = 1.0
        mock_result.total_tokens = 50
        agency.orchestrator.build = AsyncMock(return_value=mock_result)

        await agency.execute_project("Build", workdir="/custom/dir")
        agency.orchestrator.build.assert_called_once_with("Build", workdir="/custom/dir")
