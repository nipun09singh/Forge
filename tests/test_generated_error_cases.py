"""Error and edge-case tests for generated agencies.

Covers tool failures, agent errors, memory consistency, and workflow
dependency ordering — all with mocked LLM calls (no real API costs).
"""

import asyncio
import json
import sys
import types
import importlib
import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from forge.core.blueprint import (
    AgencyBlueprint, AgentBlueprint, AgentRole, TeamBlueprint,
    ToolBlueprint, WorkflowBlueprint, WorkflowStep, APIEndpoint,
)
from forge.generators.agency_generator import AgencyGenerator
from forge.runtime.agent import Agent, AgentStatus, TaskResult
from forge.runtime.tools import Tool, ToolParameter, ToolRegistry
from forge.runtime.memory import SharedMemory
from forge.runtime.planner import TaskPlan, PlanStep, StepStatus, CyclicDependencyError
from forge.runtime.observability import EventLog


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


def _make_tool_call_response(tool_name: str, arguments: dict):
    """Create a mock LLM response that requests a tool call."""
    client = AsyncMock()
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = None

    tc = MagicMock()
    tc.id = "call_test_001"
    tc.type = "function"
    tc.function.name = tool_name
    tc.function.arguments = json.dumps(arguments)
    resp.choices[0].message.tool_calls = [tc]

    resp.usage = MagicMock()
    resp.usage.prompt_tokens = 50
    resp.usage.completion_tokens = 20
    resp.usage.total_tokens = 70

    # After the tool call the LLM returns a final text answer
    final_resp = MagicMock()
    final_resp.choices = [MagicMock()]
    final_resp.choices[0].message.content = "Done after tool call."
    final_resp.choices[0].message.tool_calls = None
    final_resp.usage = MagicMock()
    final_resp.usage.prompt_tokens = 60
    final_resp.usage.completion_tokens = 25
    final_resp.usage.total_tokens = 85

    client.chat.completions.create = AsyncMock(side_effect=[resp, final_resp])
    return client


def _load_module_from_path(module_name: str, file_path: Path) -> types.ModuleType:
    """Import a Python file as a module, given its absolute path."""
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_agent_with_tool(tool: Tool, mock_client=None) -> Agent:
    """Create a minimal agent wired up with a single tool and mock LLM."""
    agent = Agent(
        name="TestAgent",
        role="specialist",
        system_prompt="You are a test agent.",
        tools=[tool],
        model="gpt-4",
        tool_timeout_seconds=2.0,
        max_iterations=3,
    )
    if mock_client:
        agent.set_llm_client(mock_client)
    return agent


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def agency_blueprint():
    """A realistic blueprint for generated-agency tests."""
    specialist = AgentBlueprint(
        name="Data Agent",
        role=AgentRole.SPECIALIST,
        title="Data Analyst",
        system_prompt="You analyze data and answer questions.",
        capabilities=["Data analysis"],
        tools=[
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
        system_prompt="You manage the analytics team.",
        capabilities=["Team management"],
        can_spawn_sub_agents=True,
    )
    return AgencyBlueprint(
        name="Analytics Agency",
        slug="analytics-agency",
        description="An analytics agency",
        domain="Data analytics",
        teams=[TeamBlueprint(
            name="Analytics Team",
            description="Data analysis team",
            lead=lead,
            agents=[specialist],
        )],
        workflows=[WorkflowBlueprint(
            name="Analyze Data",
            steps=[
                WorkflowStep(id="s1", description="Fetch data"),
                WorkflowStep(id="s2", description="Analyze", depends_on=["s1"]),
            ],
        )],
        api_endpoints=[APIEndpoint(path="/api/task", method="POST", description="Execute task")],
        model="gpt-4",
    )


@pytest.fixture
def generated_agency_path(agency_blueprint, tmp_path):
    """Generate an agency to a temp directory and return its path."""
    gen = AgencyGenerator(output_base=tmp_path)
    path = gen.generate(agency_blueprint)
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    yield path
    if str(path) in sys.path:
        sys.path.remove(str(path))
    mods_to_remove = [k for k in sys.modules if k.startswith(("main", "api_server", "agents.", "tools."))]
    for m in mods_to_remove:
        sys.modules.pop(m, None)


# ── Tool Failure Tests ────────────────────────────────────


class TestToolFailures:
    """Test that the agent handles tool failures gracefully."""

    @pytest.mark.asyncio
    async def test_tool_raises_exception_agent_continues(self):
        """A tool that raises an exception should not crash the agent."""
        async def bad_tool(**kwargs):
            raise RuntimeError("Database connection failed")

        tool = Tool(
            name="bad_db",
            description="Fails on every call",
            parameters=[ToolParameter(name="query", type="string", description="SQL query")],
            _fn=bad_tool,
        )
        # LLM first calls the tool, then gives a final text answer
        client = _make_tool_call_response("bad_db", {"query": "SELECT 1"})
        agent = _make_agent_with_tool(tool, client)

        result = await agent.execute("Run a query")
        assert result is not None
        assert isinstance(result, TaskResult)
        # The agent should still complete (the tool error is fed back to the LLM)
        assert result.output  # non-empty response

    @pytest.mark.asyncio
    async def test_tool_returns_empty_string(self):
        """A tool returning an empty string should not crash the agent."""
        async def empty_tool(**kwargs):
            return ""

        tool = Tool(
            name="empty",
            description="Returns nothing",
            parameters=[],
            _fn=empty_tool,
        )
        client = _make_tool_call_response("empty", {})
        agent = _make_agent_with_tool(tool, client)

        result = await agent.execute("Do something")
        assert result is not None
        assert isinstance(result, TaskResult)

    @pytest.mark.asyncio
    async def test_tool_returns_none(self):
        """A tool returning None should be safely stringified."""
        async def none_tool(**kwargs):
            return None

        tool = Tool(
            name="null_tool",
            description="Returns None",
            parameters=[],
            _fn=none_tool,
        )
        client = _make_tool_call_response("null_tool", {})
        agent = _make_agent_with_tool(tool, client)

        result = await agent.execute("Call the null tool")
        assert result is not None

    @pytest.mark.asyncio
    async def test_tool_access_denied_by_role_policy(self):
        """A tool denied by role policy returns proper error message."""
        async def secret_fn(**kwargs):
            return "secret data"

        tool = Tool(
            name="admin_tool",
            description="Admin only",
            parameters=[],
            _fn=secret_fn,
        )
        # Agent with denied_tools list blocks admin_tool
        agent = Agent(
            name="LimitedAgent",
            role="specialist",
            system_prompt="You are a limited agent.",
            tools=[tool],
            denied_tools=["admin_tool"],
            max_iterations=3,
            tool_timeout_seconds=2.0,
        )
        client = _make_tool_call_response("admin_tool", {})
        agent.set_llm_client(client)

        result = await agent.execute("Use the admin tool")
        assert result is not None
        # The agent completes; the tool denial is communicated back
        assert isinstance(result, TaskResult)

    @pytest.mark.asyncio
    async def test_unknown_tool_name_handled(self):
        """If LLM requests a tool that doesn't exist, agent handles gracefully."""
        # Register a real tool but LLM asks for a non-existent one
        async def real_fn(**kwargs):
            return "ok"

        tool = Tool(name="real_tool", description="Real tool", parameters=[], _fn=real_fn)
        client = _make_tool_call_response("nonexistent_tool", {})
        agent = _make_agent_with_tool(tool, client)

        result = await agent.execute("Use nonexistent_tool")
        assert result is not None
        assert isinstance(result, TaskResult)

    @pytest.mark.asyncio
    async def test_tool_missing_required_parameter(self):
        """Tool.run() raises ValueError when required parameter is missing."""
        async def param_fn(name: str):
            return f"Hello {name}"

        tool = Tool(
            name="greet",
            description="Greets",
            parameters=[ToolParameter(name="name", type="string", description="Name", required=True)],
            _fn=param_fn,
        )
        with pytest.raises(ValueError, match="requires parameter 'name'"):
            await tool.run()  # no args → ValueError

    @pytest.mark.asyncio
    async def test_tool_with_no_implementation(self):
        """Tool with _fn=None raises NotImplementedError."""
        tool = Tool(name="stub", description="No implementation", parameters=[], _fn=None)
        with pytest.raises(NotImplementedError, match="has no implementation"):
            await tool.run()


# ── Agent Error Tests ─────────────────────────────────────


class TestAgentErrors:
    """Test that agent-level errors are handled without crashes."""

    @pytest.mark.asyncio
    async def test_agent_without_llm_client_returns_error(self):
        """An agent with no LLM client should return a failure result, not crash."""
        tool = Tool(name="noop", description="no-op", parameters=[], _fn=lambda: "ok")
        agent = _make_agent_with_tool(tool)
        # No LLM client set — _call_llm raises RuntimeError, caught by _execute_attempt

        result = await agent.execute("Do something")
        assert result.success is False
        assert "no LLM client" in result.output.lower() or "agent error" in result.output.lower()

    @pytest.mark.asyncio
    async def test_llm_returns_malformed_json_tool_args(self):
        """If LLM returns invalid JSON in tool arguments, agent defaults to empty args."""
        async def echo_fn(**kwargs):
            return f"Got: {kwargs}"

        tool = Tool(name="echo", description="echo", parameters=[], _fn=echo_fn)

        # Build a response where arguments is invalid JSON
        client = AsyncMock()
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = None
        tc = MagicMock()
        tc.id = "call_bad_json"
        tc.type = "function"
        tc.function.name = "echo"
        tc.function.arguments = "{{not valid json}}"
        resp.choices[0].message.tool_calls = [tc]
        resp.usage = MagicMock()
        resp.usage.prompt_tokens = 50
        resp.usage.completion_tokens = 20
        resp.usage.total_tokens = 70

        final = MagicMock()
        final.choices = [MagicMock()]
        final.choices[0].message.content = "Handled malformed args."
        final.choices[0].message.tool_calls = None
        final.usage = MagicMock()
        final.usage.prompt_tokens = 60
        final.usage.completion_tokens = 25
        final.usage.total_tokens = 85

        client.chat.completions.create = AsyncMock(side_effect=[resp, final])

        agent = _make_agent_with_tool(tool, client)
        result = await agent.execute("Echo something")
        # Agent should not crash — defaults args to {}
        assert result is not None
        assert isinstance(result, TaskResult)

    @pytest.mark.asyncio
    async def test_llm_raises_exception_agent_returns_error(self):
        """If the LLM itself raises an exception, agent returns error result."""
        tool = Tool(name="noop", description="no-op", parameters=[], _fn=lambda: "ok")
        client = AsyncMock()
        client.chat.completions.create = AsyncMock(
            side_effect=Exception("API quota exceeded")
        )
        agent = _make_agent_with_tool(tool, client)

        result = await agent.execute("Do something")
        assert result.success is False
        assert "agent error" in result.output.lower() or "api quota" in result.output.lower()
        assert agent.status == AgentStatus.ERROR

    @pytest.mark.asyncio
    async def test_agent_max_iterations_returns_failure(self):
        """Agent that never finishes (always calls tools) hits max_iterations and returns failure."""
        async def loop_fn(**kwargs):
            return "need more data"

        tool = Tool(name="loop", description="loops", parameters=[], _fn=loop_fn)

        # LLM always returns a tool call — never a final text answer
        client = AsyncMock()

        def _make_tool_resp():
            r = MagicMock()
            r.choices = [MagicMock()]
            r.choices[0].message.content = None
            tc = MagicMock()
            tc.id = "call_loop"
            tc.type = "function"
            tc.function.name = "loop"
            tc.function.arguments = "{}"
            r.choices[0].message.tool_calls = [tc]
            r.usage = MagicMock()
            r.usage.prompt_tokens = 50
            r.usage.completion_tokens = 20
            r.usage.total_tokens = 70
            return r

        client.chat.completions.create = AsyncMock(side_effect=[_make_tool_resp() for _ in range(10)])

        agent = Agent(
            name="LoopAgent",
            role="specialist",
            system_prompt="You loop forever.",
            tools=[tool],
            max_iterations=3,
            tool_timeout_seconds=2.0,
        )
        agent.set_llm_client(client)

        result = await agent.execute("Loop forever")
        assert result.success is False
        assert agent.status == AgentStatus.ERROR

    @pytest.mark.asyncio
    async def test_empty_task_returns_failure(self):
        """Agent rejects empty task string immediately."""
        agent = Agent(
            name="EmptyAgent",
            role="specialist",
            system_prompt="test",
            max_iterations=3,
        )
        agent.set_llm_client(_make_mock_llm_client())

        result = await agent.execute("")
        assert result.success is False
        assert "non-empty" in result.output.lower()

    @pytest.mark.asyncio
    async def test_tool_timeout_handled(self):
        """A tool that takes too long should time out without crashing the agent."""
        async def slow_tool(**kwargs):
            await asyncio.sleep(60)  # very slow
            return "finally done"

        tool = Tool(name="slow", description="Slow tool", parameters=[], _fn=slow_tool)
        client = _make_tool_call_response("slow", {})
        # Agent with a very short timeout
        agent = Agent(
            name="TimeoutAgent",
            role="specialist",
            system_prompt="test",
            tools=[tool],
            tool_timeout_seconds=0.1,
            max_iterations=3,
        )
        agent.set_llm_client(client)

        result = await agent.execute("Call the slow tool")
        assert result is not None
        assert isinstance(result, TaskResult)


# ── Memory Tests ──────────────────────────────────────────


class TestMemoryConsistency:
    """Test memory store/recall behaviour in generated agencies."""

    def test_store_and_recall_basic(self):
        """Basic store/recall works."""
        mem = SharedMemory()
        mem.store("key1", {"data": 42}, author="agent-a")
        assert mem.recall("key1") == {"data": 42}

    def test_recall_missing_key_returns_none(self):
        """Recalling a non-existent key returns None."""
        mem = SharedMemory()
        assert mem.recall("nonexistent") is None

    def test_memory_overwrites_on_same_key(self):
        """Storing with the same key overwrites the previous value."""
        mem = SharedMemory()
        mem.store("k", "first", author="a")
        mem.store("k", "second", author="b")
        assert mem.recall("k") == "second"

    def test_memory_persists_across_operations(self):
        """Memory entries survive multiple store operations within a session."""
        mem = SharedMemory()
        for i in range(50):
            mem.store(f"item-{i}", i, author="bulk")

        for i in range(50):
            assert mem.recall(f"item-{i}") == i

    def test_memory_search_by_tag(self):
        """Search filters by tag correctly."""
        mem = SharedMemory()
        mem.store("a", 1, author="x", tags=["important"])
        mem.store("b", 2, author="x", tags=["debug"])
        mem.store("c", 3, author="x", tags=["important", "debug"])

        important = mem.search(tag="important")
        assert len(important) == 2
        keys = {e.key for e in important}
        assert keys == {"a", "c"}

    def test_memory_search_by_author(self):
        """Search filters by author correctly."""
        mem = SharedMemory()
        mem.store("x", 1, author="alice")
        mem.store("y", 2, author="bob")
        mem.store("z", 3, author="alice")

        alice_entries = mem.search(author="alice")
        assert len(alice_entries) == 2

    def test_context_summary_includes_recent(self):
        """get_context_summary returns recent entries for prompt injection."""
        mem = SharedMemory()
        mem.store("task_result", "Revenue is up 15%", author="analyst")
        summary = mem.get_context_summary(max_entries=5)
        assert "Revenue is up 15%" in summary
        assert "analyst" in summary

    def test_generated_agency_memory_shared(self, generated_agency_path):
        """Memory stored at agency level is visible to agents."""
        main_mod = _load_module_from_path("main", generated_agency_path / "main.py")
        agency, _ = main_mod.build_agency()

        agency.memory.store("shared_fact", "The sky is blue", author="test")
        assert agency.memory.recall("shared_fact") == "The sky is blue"

        # All agents sharing the same memory see the value
        for team in agency.teams.values():
            for agent in team.agents:
                if agent.memory is agency.memory:
                    assert agent.memory.recall("shared_fact") == "The sky is blue"

    @pytest.mark.asyncio
    async def test_async_store_recall(self):
        """Async store/recall works correctly."""
        mem = SharedMemory()
        await mem.astore("async_key", "async_val", author="test")
        assert mem.recall("async_key") == "async_val"

    def test_memory_history_truncation(self):
        """History is truncated when it exceeds max_history."""
        mem = SharedMemory(max_history=10)
        for i in range(25):
            mem.store(f"h-{i}", i, author="test")

        # History should be capped
        assert len(mem._history) <= 10
        # But all keys should still be recallable from the store
        for i in range(25):
            assert mem.recall(f"h-{i}") == i


# ── Workflow / Planner Tests ──────────────────────────────


class TestWorkflowDependencies:
    """Test that workflow dependency ordering and cycle detection work."""

    def test_steps_execute_in_dependency_order(self):
        """Steps with dependencies should only become ready after deps complete."""
        plan = TaskPlan(
            task="Build report",
            steps=[
                PlanStep(id="fetch", description="Fetch data"),
                PlanStep(id="transform", description="Transform data", depends_on=["fetch"]),
                PlanStep(id="report", description="Generate report", depends_on=["transform"]),
            ],
        )
        # Initially only 'fetch' is ready (no deps)
        ready = plan.get_ready_steps()
        assert [s.id for s in ready] == ["fetch"]

        # Complete 'fetch' → 'transform' becomes ready
        plan.steps[0].status = StepStatus.COMPLETED
        ready = plan.get_ready_steps()
        assert [s.id for s in ready] == ["transform"]

        # Complete 'transform' → 'report' becomes ready
        plan.steps[1].status = StepStatus.COMPLETED
        ready = plan.get_ready_steps()
        assert [s.id for s in ready] == ["report"]

    def test_parallel_steps_ready_simultaneously(self):
        """Independent steps should all be ready at once."""
        plan = TaskPlan(
            task="Parallel work",
            steps=[
                PlanStep(id="a", description="Task A"),
                PlanStep(id="b", description="Task B"),
                PlanStep(id="c", description="Task C"),
                PlanStep(id="merge", description="Merge results", depends_on=["a", "b", "c"]),
            ],
        )
        ready = plan.get_ready_steps()
        assert len(ready) == 3
        assert {s.id for s in ready} == {"a", "b", "c"}

        # Complete all three → 'merge' is ready
        for step in plan.steps[:3]:
            step.status = StepStatus.COMPLETED
        ready = plan.get_ready_steps()
        assert [s.id for s in ready] == ["merge"]

    def test_cycle_detection_raises_error(self):
        """Circular dependencies should raise CyclicDependencyError."""
        plan = TaskPlan(
            task="Cyclic plan",
            steps=[
                PlanStep(id="a", description="Step A", depends_on=["c"]),
                PlanStep(id="b", description="Step B", depends_on=["a"]),
                PlanStep(id="c", description="Step C", depends_on=["b"]),
            ],
        )
        with pytest.raises(CyclicDependencyError) as exc_info:
            plan.get_ready_steps()
        assert exc_info.value.cycle  # non-empty cycle list

    def test_self_dependency_cycle(self):
        """A step depending on itself should be detected as a cycle."""
        plan = TaskPlan(
            task="Self-dep",
            steps=[
                PlanStep(id="x", description="Depends on itself", depends_on=["x"]),
            ],
        )
        with pytest.raises(CyclicDependencyError):
            plan.get_ready_steps()

    def test_partial_deps_not_ready(self):
        """A step with partially completed deps should not be ready."""
        plan = TaskPlan(
            task="Partial",
            steps=[
                PlanStep(id="a", description="A"),
                PlanStep(id="b", description="B"),
                PlanStep(id="c", description="C", depends_on=["a", "b"]),
            ],
        )
        plan.steps[0].status = StepStatus.COMPLETED
        # b still pending, so c should not be ready
        ready = plan.get_ready_steps()
        assert "c" not in [s.id for s in ready]
        assert "b" in [s.id for s in ready]

    def test_validate_dependencies_on_valid_plan(self):
        """validate_dependencies does not raise on a valid DAG."""
        plan = TaskPlan(
            task="Valid DAG",
            steps=[
                PlanStep(id="s1", description="Step 1"),
                PlanStep(id="s2", description="Step 2", depends_on=["s1"]),
            ],
        )
        plan.validate_dependencies()  # should not raise

    def test_validate_dependencies_on_cyclic_plan(self):
        """validate_dependencies raises CyclicDependencyError on cyclic plan."""
        plan = TaskPlan(
            task="Cyclic",
            steps=[
                PlanStep(id="a", description="A", depends_on=["b"]),
                PlanStep(id="b", description="B", depends_on=["a"]),
            ],
        )
        with pytest.raises(CyclicDependencyError):
            plan.validate_dependencies()

    def test_progress_tracking(self):
        """TaskPlan.progress reports correct completion ratio."""
        plan = TaskPlan(
            task="Progress",
            steps=[
                PlanStep(id="s1", description="S1"),
                PlanStep(id="s2", description="S2"),
                PlanStep(id="s3", description="S3"),
                PlanStep(id="s4", description="S4"),
            ],
        )
        assert plan.progress == 0.0

        plan.steps[0].status = StepStatus.COMPLETED
        plan.steps[1].status = StepStatus.COMPLETED
        assert plan.progress == 0.5

        for s in plan.steps:
            s.status = StepStatus.COMPLETED
        assert plan.progress == 1.0

    def test_step_retry_flag(self):
        """PlanStep.can_retry respects max_retries."""
        step = PlanStep(id="r", description="Retryable", max_retries=2)
        assert step.can_retry is True

        step.retry_count = 1
        assert step.can_retry is True

        step.retry_count = 2
        assert step.can_retry is False
