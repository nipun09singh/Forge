"""Integration tests requiring a real LLM API key.

Run with: pytest tests/test_integration_llm.py -m integration
Skip with: pytest -m "not integration"
"""

import tempfile

import pytest

from forge.runtime.agent import Agent, AgentStatus
from forge.runtime.tools import Tool, ToolParameter
from forge.core.engine import ForgeEngine

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_agent_responds_to_simple_task(real_llm_client):
    """Verify an agent can process a simple task with real LLM."""
    agent = Agent(
        name="SimpleAgent",
        role="specialist",
        system_prompt="You are a helpful assistant. Reply concisely.",
        model="gpt-4o-mini",
        temperature=0.0,
        max_iterations=3,
    )
    agent.set_llm_client(real_llm_client)

    result = await agent.execute("What is 2 + 2? Reply with just the number.")

    assert result.success is True
    assert result.output is not None
    assert len(result.output.strip()) > 0
    assert "4" in result.output
    assert agent.status == AgentStatus.COMPLETED


@pytest.mark.asyncio
async def test_tool_calling_works(real_llm_client):
    """Verify LLM can select and call tools correctly."""
    tool_was_called = False

    async def add_numbers(a: str, b: str) -> str:
        nonlocal tool_was_called
        tool_was_called = True
        return str(int(a) + int(b))

    add_tool = Tool(
        name="add_numbers",
        description="Adds two numbers together and returns the sum",
        parameters=[
            ToolParameter(name="a", type="string", description="First number"),
            ToolParameter(name="b", type="string", description="Second number"),
        ],
        _fn=add_numbers,
    )

    agent = Agent(
        name="ToolAgent",
        role="specialist",
        system_prompt=(
            "You are a math assistant. You MUST use the add_numbers tool "
            "to perform addition. Never compute results yourself."
        ),
        tools=[add_tool],
        model="gpt-4o-mini",
        temperature=0.0,
        max_iterations=5,
    )
    agent.set_llm_client(real_llm_client)

    result = await agent.execute("What is 17 + 25?")

    assert result.success is True
    assert tool_was_called, "Expected the LLM to call the add_numbers tool"
    assert "42" in result.output


@pytest.mark.asyncio
async def test_agency_generation_produces_valid_output(real_llm_client):
    """Verify the core value prop: sentence → working agency."""
    import os

    api_key = os.environ.get("OPENAI_API_KEY", "")

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        engine = ForgeEngine(
            model="gpt-4o-mini",
            api_key=api_key,
            base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            output_dir=tmp_dir,
        )

        blueprint, output_path = await engine.create_agency(
            domain_description="A simple FAQ bot that answers questions about Python programming",
            force=True,
        )

        assert blueprint is not None
        assert blueprint.name, "Blueprint should have a name"
        assert len(blueprint.teams) > 0, "Blueprint should define at least one team"
        assert blueprint.domain, "Blueprint should capture the domain"
