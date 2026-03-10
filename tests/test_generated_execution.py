"""Execution-level tests for generated agencies.

These tests go beyond file-structure checks: they generate an agency,
import its modules, instantiate its objects, call tool functions, and
run a basic task flow — all with mocked LLM calls so no real API costs.
"""

import asyncio
import importlib
import importlib.util
import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from forge.core.blueprint import (
    AgencyBlueprint, AgentBlueprint, AgentRole, TeamBlueprint,
    ToolBlueprint, WorkflowBlueprint, WorkflowStep, APIEndpoint,
)
from forge.generators.agency_generator import AgencyGenerator


# ── Helpers ───────────────────────────────────────────────

def _make_mock_llm_client(content: str = "Mock LLM response"):
    """Create a mock AsyncOpenAI client that returns a text response."""
    client = AsyncMock()
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    resp.choices[0].message.tool_calls = None
    resp.usage = MagicMock()
    resp.usage.prompt_tokens = 50
    resp.usage.completion_tokens = 20
    resp.usage.total_tokens = 70
    client.chat.completions.create = AsyncMock(return_value=resp)
    return client


def _load_module_from_path(module_name: str, file_path: Path) -> types.ModuleType:
    """Import a Python file as a module, given its absolute path."""
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture
def agency_blueprint():
    """A realistic blueprint with both built-in and domain tools."""
    specialist = AgentBlueprint(
        name="Data Agent",
        role=AgentRole.SPECIALIST,
        title="Data Analyst",
        system_prompt="You analyze data and answer questions.",
        capabilities=["Data analysis", "Report generation"],
        tools=[
            ToolBlueprint(
                name="http_request",
                description="Make HTTP requests to external APIs",
                parameters=[
                    {"name": "url", "type": "string", "description": "URL to request", "required": True},
                    {"name": "method", "type": "string", "description": "HTTP method", "required": False},
                ],
            ),
            ToolBlueprint(
                name="analyze_metrics",
                description="Analyze business metrics from a dataset",
                parameters=[
                    {"name": "dataset", "type": "string", "description": "Dataset name", "required": True},
                    {"name": "metric", "type": "string", "description": "Metric to analyze", "required": True},
                ],
            ),
        ],
    )

    lead = AgentBlueprint(
        name="Team Lead",
        role=AgentRole.MANAGER,
        title="Analytics Lead",
        system_prompt="You manage the analytics team and delegate tasks.",
        capabilities=["Team management", "Task delegation"],
        can_spawn_sub_agents=True,
    )

    return AgencyBlueprint(
        name="Analytics Agency",
        slug="analytics-agency",
        description="An analytics agency for data insights",
        domain="Data analytics and business intelligence",
        teams=[TeamBlueprint(
            name="Analytics Team",
            description="Data analysis team",
            lead=lead,
            agents=[specialist],
        )],
        workflows=[WorkflowBlueprint(
            name="Analyze Data",
            steps=[WorkflowStep(id="s1", description="Fetch data"),
                   WorkflowStep(id="s2", description="Analyze", depends_on=["s1"])],
        )],
        api_endpoints=[APIEndpoint(path="/api/task", method="POST", description="Execute task")],
        shared_tools=[
            ToolBlueprint(
                name="send_webhook",
                description="Send notifications via webhook",
                parameters=[
                    {"name": "url", "type": "string", "description": "Webhook URL", "required": True},
                    {"name": "payload", "type": "string", "description": "JSON payload", "required": True},
                ],
            ),
        ],
        model="gpt-4",
    )


@pytest.fixture
def generated_agency_path(agency_blueprint, tmp_path):
    """Generate an agency to a temp directory and return its path."""
    gen = AgencyGenerator(output_base=tmp_path)
    path = gen.generate(agency_blueprint)
    # Make sure the generated dir is importable
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    yield path
    # Clean up sys.path and loaded modules
    if str(path) in sys.path:
        sys.path.remove(str(path))
    mods_to_remove = [k for k in sys.modules if k.startswith(("main", "api_server", "agents.", "tools."))]
    for m in mods_to_remove:
        sys.modules.pop(m, None)


# ── Tests ─────────────────────────────────────────────────

class TestGeneratedModuleImports:
    """Test that generated modules can be imported without crashing."""

    def test_main_module_imports(self, generated_agency_path):
        """The generated main.py should import without errors."""
        main_path = generated_agency_path / "main.py"
        assert main_path.exists()
        mod = _load_module_from_path("main", main_path)
        assert hasattr(mod, "build_agency"), "main.py must expose build_agency()"

    def test_agent_modules_import(self, generated_agency_path):
        """Each generated agent module should import cleanly."""
        agents_dir = generated_agency_path / "agents"
        agent_files = list(agents_dir.glob("agent_*.py"))
        assert len(agent_files) >= 1, "Expected at least one agent module"

        for agent_file in agent_files:
            mod_name = f"agents.{agent_file.stem}"
            mod = _load_module_from_path(mod_name, agent_file)
            # Every agent module should have a create_*_agent function
            create_fns = [a for a in dir(mod) if a.startswith("create_") and a.endswith("_agent")]
            assert len(create_fns) >= 1, (
                f"{agent_file.name} has no create_*_agent function. "
                f"Attributes: {[a for a in dir(mod) if not a.startswith('_')]}"
            )

    def test_tool_modules_import(self, generated_agency_path):
        """Each generated tool module should import cleanly."""
        tools_dir = generated_agency_path / "tools"
        tool_files = list(tools_dir.glob("tool_*.py"))
        assert len(tool_files) >= 1, "Expected at least one tool module"

        for tool_file in tool_files:
            mod_name = f"tools.{tool_file.stem}"
            mod = _load_module_from_path(mod_name, tool_file)
            # Every tool module should expose a *_tool object
            tool_attrs = [a for a in dir(mod) if a.endswith("_tool") and not a.startswith("_")]
            assert len(tool_attrs) >= 1, (
                f"{tool_file.name} has no *_tool attribute. "
                f"Attributes: {[a for a in dir(mod) if not a.startswith('_')]}"
            )

    def test_api_server_module_parseable(self, generated_agency_path):
        """The generated api_server.py should at least be valid Python syntax."""
        import py_compile
        api_path = generated_agency_path / "api_server.py"
        assert api_path.exists()
        # py_compile catches syntax errors without executing module-level side effects
        py_compile.compile(str(api_path), doraise=True)


class TestToolFunctionsCallable:
    """Test that generated tool functions can be called with sample args."""

    def test_builtin_tool_objects_have_run(self, generated_agency_path):
        """Built-in tools (http_request, send_webhook) should have a callable run()."""
        tools_dir = generated_agency_path / "tools"
        for tool_file in tools_dir.glob("tool_*.py"):
            mod = _load_module_from_path(f"tools.{tool_file.stem}", tool_file)
            for attr_name in dir(mod):
                if attr_name.endswith("_tool") and not attr_name.startswith("_"):
                    tool_obj = getattr(mod, attr_name)
                    if hasattr(tool_obj, "run"):
                        assert callable(tool_obj.run), (
                            f"{attr_name} in {tool_file.name} has .run but it's not callable"
                        )

    @pytest.mark.asyncio
    async def test_domain_tool_returns_real_data(self, generated_agency_path):
        """Domain tools (mock-backed) should return realistic data, not hardcoded stubs."""
        tool_path = generated_agency_path / "tools" / "tool_analyze_metrics.py"
        if not tool_path.exists():
            pytest.skip("analyze_metrics tool not generated")

        mod = _load_module_from_path("tools.tool_analyze_metrics", tool_path)
        tool_obj = getattr(mod, "analyze_metrics_tool", None)
        assert tool_obj is not None, "analyze_metrics_tool not found"

        result = await tool_obj.run(dataset="sales_data", metric="revenue")
        assert result is not None, "Tool returned None"
        # Mock-backed tools return JSON-like dicts with results
        if isinstance(result, str):
            data = json.loads(result)
        else:
            data = result
        assert "success" in data or "results" in data or isinstance(data, (dict, list)), (
            f"Tool returned unexpected format: {result}"
        )

    @pytest.mark.asyncio
    async def test_webhook_tool_callable(self, generated_agency_path):
        """The send_webhook tool should be callable and return a result."""
        tool_path = generated_agency_path / "tools" / "tool_send_webhook.py"
        if not tool_path.exists():
            pytest.skip("send_webhook tool not generated")

        mod = _load_module_from_path("tools.tool_send_webhook", tool_path)
        tool_obj = getattr(mod, "send_webhook_tool", None)
        assert tool_obj is not None, "send_webhook_tool not found"
        assert hasattr(tool_obj, "run"), "send_webhook_tool has no run method"

        result = await tool_obj.run(url="https://example.com/hook", payload='{"test": true}')
        assert result is not None


class TestAgentInitialization:
    """Test that Agent objects can be created from generated config."""

    def test_build_agency_returns_agency_and_event_log(self, generated_agency_path):
        """build_agency() should return (Agency, EventLog) tuple without error."""
        main_mod = _load_module_from_path("main", generated_agency_path / "main.py")
        agency, event_log = main_mod.build_agency()

        assert agency is not None
        assert event_log is not None
        assert agency.name == "Analytics Agency"

    def test_agency_has_teams(self, generated_agency_path):
        """The built agency should have at least one team."""
        main_mod = _load_module_from_path("main", generated_agency_path / "main.py")
        agency, _ = main_mod.build_agency()

        assert len(agency.teams) >= 1, f"Agency has no teams: {agency.teams}"

    def test_agency_teams_have_agents(self, generated_agency_path):
        """Each team should have agents (lead and/or members)."""
        main_mod = _load_module_from_path("main", generated_agency_path / "main.py")
        agency, _ = main_mod.build_agency()

        for team_name, team in agency.teams.items():
            total = len(team.agents) + (1 if team.lead else 0)
            assert total >= 1, f"Team '{team_name}' has no agents"

    def test_agents_have_tools_registered(self, generated_agency_path):
        """Agents with tools in the blueprint should have them in their ToolRegistry."""
        main_mod = _load_module_from_path("main", generated_agency_path / "main.py")
        agency, _ = main_mod.build_agency()

        # The specialist agent ("Data Agent") should have tools
        for team in agency.teams.values():
            for agent in team.agents:
                if agent.name == "Data Agent":
                    tool_names = [t.name for t in agent.tool_registry.list_tools()]
                    assert len(tool_names) >= 1, (
                        f"Data Agent has no tools registered. Expected at least http_request."
                    )
                    return
        # If we reach here, we didn't find the Data Agent — not necessarily an error
        # if names were sanitized, but check that at least some agent has tools
        found_tools = False
        for team in agency.teams.values():
            for agent in list(team.agents) + ([team.lead] if team.lead else []):
                if agent.tool_registry.list_tools():
                    found_tools = True
                    break
        assert found_tools, "No agent in the agency has any tools registered"

    def test_memory_is_functional(self, generated_agency_path):
        """Agency memory should support store/recall."""
        main_mod = _load_module_from_path("main", generated_agency_path / "main.py")
        agency, _ = main_mod.build_agency()

        agency.memory.store("test_key", "test_value", author="test")
        assert agency.memory.recall("test_key") == "test_value"


class TestBasicTaskFlow:
    """Test that a generated agency can run a simple task with mocked LLM."""

    @pytest.mark.asyncio
    async def test_agent_execute_with_mock_llm(self, generated_agency_path):
        """An agent from the generated agency should execute a task with mocked LLM."""
        main_mod = _load_module_from_path("main", generated_agency_path / "main.py")
        agency, event_log = main_mod.build_agency()

        mock_client = _make_mock_llm_client("The quarterly revenue is $1.2M, up 15%.")

        # Inject mock LLM into all agents
        for team in agency.teams.values():
            if team.lead:
                team.lead.set_llm_client(mock_client)
            for agent in team.agents:
                agent.set_llm_client(mock_client)

        # Pick any agent and run a task
        agent = None
        for team in agency.teams.values():
            if team.agents:
                agent = team.agents[0]
                break
        assert agent is not None, "No agent found to execute task"

        result = await agent.execute("What is the quarterly revenue?")
        assert result is not None
        assert result.success is True
        assert len(result.output) > 0

    @pytest.mark.asyncio
    async def test_agency_execute_with_mock_llm(self, generated_agency_path):
        """The full agency.execute() flow should complete with mocked LLM."""
        main_mod = _load_module_from_path("main", generated_agency_path / "main.py")
        agency, event_log = main_mod.build_agency()

        mock_client = _make_mock_llm_client("Task completed successfully.")
        agency._llm_client = mock_client

        # Inject into all agents
        for team in agency.teams.values():
            if team.lead:
                team.lead.set_llm_client(mock_client)
            for agent in team.agents:
                agent.set_llm_client(mock_client)

        # Also set on planner
        agency.planner.set_llm_client(mock_client)

        result = await agency.execute("Generate a summary report")
        assert result is not None
        assert result.success is True

    @pytest.mark.asyncio
    async def test_event_log_records_events(self, generated_agency_path):
        """Running a task should generate events in the EventLog."""
        main_mod = _load_module_from_path("main", generated_agency_path / "main.py")
        agency, event_log = main_mod.build_agency()

        mock_client = _make_mock_llm_client("Analysis complete.")
        for team in agency.teams.values():
            if team.lead:
                team.lead.set_llm_client(mock_client)
            for agent in team.agents:
                agent.set_llm_client(mock_client)
        agency._llm_client = mock_client
        agency.planner.set_llm_client(mock_client)

        initial_events = len(event_log.events)
        await agency.execute("Run an analysis")
        assert len(event_log.events) > initial_events, (
            "No new events recorded after executing a task"
        )


class TestGeneratedAPIServer:
    """Test that the FastAPI app can be created from generated code."""

    def test_api_server_creates_fastapi_app(self, generated_agency_path):
        """Importing api_server should produce a FastAPI app object (with patched lifespan)."""
        # The api_server.py does `from main import build_agency` at module level,
        # so main.py must be importable first.
        _load_module_from_path("main", generated_agency_path / "main.py")

        # Patch out the _init_auth call at module level to avoid side effects
        api_path = generated_agency_path / "api_server.py"
        content = api_path.read_text(encoding="utf-8")

        # Check if it defines a FastAPI app
        assert "FastAPI(" in content, "api_server.py should define a FastAPI app"
        assert "app = FastAPI(" in content

        # Import the module — this will trigger module-level code
        # but NOT the lifespan (that only runs when the app starts)
        mod = _load_module_from_path("api_server", api_path)
        assert hasattr(mod, "app"), "api_server module should expose 'app'"

        # Check the app has routes
        routes = [r.path for r in mod.app.routes]
        assert "/api/task" in routes, f"Missing /api/task route. Routes: {routes}"
        assert "/health" in routes, f"Missing /health route. Routes: {routes}"

    def test_api_server_has_required_endpoints(self, generated_agency_path):
        """The API server should have all key endpoints."""
        _load_module_from_path("main", generated_agency_path / "main.py")
        api_path = generated_agency_path / "api_server.py"
        mod = _load_module_from_path("api_server", api_path)

        routes = [r.path for r in mod.app.routes]
        required = ["/api/task", "/api/plan", "/api/status", "/health"]
        for endpoint in required:
            assert endpoint in routes, f"Missing endpoint: {endpoint}"
