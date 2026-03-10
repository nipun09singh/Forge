"""Shared test fixtures for Forge test suite."""

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure we can import forge
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from forge.runtime.agent import Agent, TaskResult, AgentStatus
from forge.runtime.agency import Agency
from forge.runtime.team import Team
from forge.runtime.tools import Tool, ToolParameter, ToolRegistry
from forge.runtime.memory import SharedMemory
from forge.runtime.observability import EventLog, TraceContext, CostTracker
from forge.runtime.planner import Planner, TaskPlan, PlanStep, StepStatus
from forge.runtime.improvement import QualityGate, PerformanceTracker, QualityVerdict
from forge.core.blueprint import (
    AgencyBlueprint, AgentBlueprint, AgentRole, TeamBlueprint,
    ToolBlueprint, WorkflowBlueprint, WorkflowStep, APIEndpoint,
)


@pytest.fixture
def mock_llm_client():
    """Mock OpenAI AsyncOpenAI client."""
    client = AsyncMock()
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "Test response from mock LLM"
    response.choices[0].message.tool_calls = None
    response.usage = MagicMock()
    response.usage.prompt_tokens = 100
    response.usage.completion_tokens = 50
    response.usage.total_tokens = 150
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


@pytest.fixture
def sample_tool():
    """A simple test tool."""
    async def echo_tool(message: str) -> str:
        return f"Echo: {message}"

    return Tool(
        name="echo",
        description="Echoes the input message",
        parameters=[ToolParameter(name="message", type="string", description="Message to echo")],
        _fn=echo_tool,
    )


@pytest.fixture
def sample_agent(sample_tool):
    """A test agent with a tool."""
    return Agent(
        name="TestAgent",
        role="specialist",
        system_prompt="You are a test agent.",
        tools=[sample_tool],
        model="gpt-4",
        temperature=0.5,
    )


@pytest.fixture
def sample_agent_with_llm(sample_agent, mock_llm_client):
    """A test agent with a mocked LLM client."""
    sample_agent.set_llm_client(mock_llm_client)
    return sample_agent


@pytest.fixture
def sample_team(sample_agent_with_llm):
    """A test team."""
    lead = Agent(name="Lead", role="manager", system_prompt="You lead the team.")
    lead.set_llm_client(sample_agent_with_llm._llm_client)
    return Team(name="TestTeam", lead=lead, agents=[sample_agent_with_llm])


@pytest.fixture
def sample_agency(sample_team, mock_llm_client):
    """A test agency."""
    agency = Agency(name="TestAgency", description="Test agency", api_key="sk-test-fake")
    agency._llm_client = mock_llm_client
    agency.add_team(sample_team)
    return agency


@pytest.fixture
def sample_blueprint():
    """A test agency blueprint."""
    agent = AgentBlueprint(
        name="TestAgent",
        role=AgentRole.SPECIALIST,
        title="Test Specialist",
        system_prompt="You are a test specialist who helps with testing.",
        capabilities=["Testing", "Debugging"],
        tools=[ToolBlueprint(name="http_request", description="Make HTTP calls", parameters=[
            {"name": "url", "type": "string", "description": "URL", "required": True}
        ])],
    )
    lead = AgentBlueprint(
        name="TestLead",
        role=AgentRole.MANAGER,
        title="Test Manager",
        system_prompt="You manage the test team.",
        capabilities=["Management", "Delegation"],
        can_spawn_sub_agents=True,
    )
    return AgencyBlueprint(
        name="Test Agency",
        slug="test-agency",
        description="A test agency for verification",
        domain="Testing and QA automation",
        teams=[TeamBlueprint(name="Test Team", description="The test team", lead=lead, agents=[agent])],
        workflows=[WorkflowBlueprint(name="Test Workflow", steps=[
            WorkflowStep(id="s1", description="Step 1"),
            WorkflowStep(id="s2", description="Step 2", depends_on=["s1"]),
        ])],
        api_endpoints=[APIEndpoint(path="/api/task", method="POST", description="Execute task")],
        shared_tools=[ToolBlueprint(name="send_webhook", description="Send webhook", parameters=[
            {"name": "url", "type": "string", "description": "URL", "required": True},
            {"name": "payload", "type": "string", "description": "Payload", "required": True},
        ])],
        model="gpt-4",
    )


@pytest.fixture
def tmp_dir():
    """Temporary directory for tests."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        yield d


@pytest.fixture
def event_log():
    """Fresh event log."""
    return EventLog()


@pytest.fixture
def real_llm_client():
    """Real OpenAI client for integration tests. Skips if no API key."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key or api_key == "your-api-key-here":
        pytest.skip("OPENAI_API_KEY not set — skipping integration test")
    from openai import AsyncOpenAI
    return AsyncOpenAI(
        api_key=api_key,
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )
