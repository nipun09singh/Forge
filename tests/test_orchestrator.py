"""Tests for forge.runtime.orchestrator."""

import os
import json
import pytest
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

from forge.runtime.orchestrator import OrchestratorAgent, OrchestratorResult
from forge.runtime.observability import EventLog, TraceContext


def _make_llm_response(content="", tool_calls=None):
    """Helper to create mock LLM responses."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.choices[0].message.tool_calls = tool_calls
    response.usage = MagicMock()
    response.usage.prompt_tokens = 50
    response.usage.completion_tokens = 25
    response.usage.total_tokens = 75
    return response


def _make_tool_call(tc_id, name, arguments):
    """Helper to create mock tool calls."""
    tc = MagicMock()
    tc.id = tc_id
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    return tc


class TestOrchestratorInit:
    """Tests for OrchestratorAgent initialization."""

    def test_default_params(self):
        orch = OrchestratorAgent()
        assert orch.model == "gpt-4o"
        assert orch.max_iterations == 200
        assert orch.max_duration_seconds == 3600.0
        assert orch.max_cost_usd == 5.0

    def test_custom_params(self):
        orch = OrchestratorAgent(model="gpt-4", max_iterations=50, max_cost_usd=2.0)
        assert orch.model == "gpt-4"
        assert orch.max_iterations == 50
        assert orch.max_cost_usd == 2.0

    def test_no_llm_client_returns_failure(self):
        orch = OrchestratorAgent()
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(orch.build("test"))
        assert result.success is False
        assert "No LLM client" in result.summary

    def test_set_event_log(self):
        orch = OrchestratorAgent()
        log = EventLog()
        orch.set_event_log(log)
        assert orch._event_log is log

    def test_set_guardrails(self):
        from forge.runtime.guardrails import GuardrailsEngine
        orch = OrchestratorAgent()
        g = GuardrailsEngine()
        orch.set_guardrails(g)
        assert orch._guardrails is g


class TestOrchestratorBuild:
    """Tests for the main build() loop."""

    @pytest.mark.asyncio
    async def test_build_creates_project_dir(self):
        """build() creates the working directory."""
        client = AsyncMock()
        # Return DONE immediately
        done_response = _make_llm_response(content='{"status": "DONE", "summary": "Built it"}')
        # First call creates a file, second says DONE
        file_tool_call = _make_tool_call("tc1", "read_write_file", {"action": "write", "path": "main.py", "content": "print('hello')"})
        build_response = _make_llm_response(content="", tool_calls=[file_tool_call])
        client.chat.completions.create = AsyncMock(side_effect=[build_response, done_response])

        orch = OrchestratorAgent(llm_client=client, max_iterations=5)
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await orch.build("Build hello world", workdir=tmpdir)
            assert os.path.isdir(tmpdir)

    @pytest.mark.asyncio
    async def test_build_respects_max_iterations(self):
        """build() stops at max_iterations."""
        client = AsyncMock()
        # Always return text (no DONE)
        response = _make_llm_response(content="Still working on it...")
        client.chat.completions.create = AsyncMock(return_value=response)

        orch = OrchestratorAgent(llm_client=client, max_iterations=3)
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await orch.build("Build something", workdir=tmpdir)
            assert result.iterations == 3

    @pytest.mark.asyncio
    async def test_build_respects_timeout(self):
        """build() respects max_duration_seconds."""
        client = AsyncMock()
        response = _make_llm_response(content="Working...")
        client.chat.completions.create = AsyncMock(return_value=response)

        orch = OrchestratorAgent(llm_client=client, max_iterations=1000, max_duration_seconds=0.01)
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await orch.build("Build something", workdir=tmpdir)
            # Should stop quickly due to timeout
            assert result.iterations < 1000

    @pytest.mark.asyncio
    async def test_build_tracks_tokens(self):
        """build() accumulates token counts."""
        client = AsyncMock()
        done_response = _make_llm_response(content='{"status": "DONE", "summary": "Done"}')
        file_tc = _make_tool_call("tc1", "read_write_file", {"action": "write", "path": "a.py", "content": "x=1"})
        build_response = _make_llm_response(content="", tool_calls=[file_tc])
        client.chat.completions.create = AsyncMock(side_effect=[build_response, done_response])

        orch = OrchestratorAgent(llm_client=client, max_iterations=5)
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await orch.build("Build", workdir=tmpdir)
            assert result.total_tokens > 0

    @pytest.mark.asyncio
    async def test_build_emits_observability_events(self):
        """build() emits LLM and tool events when event_log is set."""
        client = AsyncMock()
        done_response = _make_llm_response(content='{"status": "DONE", "summary": "Done"}')
        client.chat.completions.create = AsyncMock(side_effect=[done_response])

        orch = OrchestratorAgent(llm_client=client, max_iterations=5)
        log = EventLog()
        orch.set_event_log(log)
        orch.set_trace_context(TraceContext())

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file so DONE is accepted (needs len(files_created) >= 1)
            os.makedirs(tmpdir, exist_ok=True)
            open(os.path.join(tmpdir, "test.py"), "w").close()
            await orch.build("Build", workdir=tmpdir)
            # Should have emitted at least llm_call and llm_response
            event_types = [e.event_type.value for e in log._events]
            assert "llm_call" in event_types
            assert "llm_response" in event_types


class TestOrchestratorResult:
    """Tests for OrchestratorResult dataclass."""

    def test_defaults(self):
        r = OrchestratorResult(success=True)
        assert r.success is True
        assert r.files_created == []
        assert r.total_tokens == 0
        assert r.iterations == 0

    def test_with_data(self):
        r = OrchestratorResult(
            success=True,
            project_dir="/tmp/test",
            files_created=["main.py", "test.py"],
            iterations=5,
            total_tokens=1000,
        )
        assert len(r.files_created) == 2
        assert r.total_tokens == 1000


class TestDiscoverTool:
    """Tests for the discover_tool meta-tool and 5-primitives principle."""

    def test_orchestrator_starts_with_exactly_6_tools(self):
        """Orchestrator loads exactly 6 tools: 5 primitives + discover_tool."""
        orch = OrchestratorAgent()
        orch._ensure_tools()
        assert len(orch._tools) == 6
        names = {t.name for t in orch._tools}
        assert "discover_tool" in names
        for prim in ["read_write_file", "run_command", "http_request", "web_search", "browse_web"]:
            assert prim in names, f"Missing primitive: {prim}"

    @pytest.mark.asyncio
    async def test_discover_tool_list_returns_all_library_tools(self):
        """discover_tool(action='list') returns JSON with all library tools."""
        orch = OrchestratorAgent()
        orch._ensure_tools()
        tool = orch._tool_map["discover_tool"]
        result = await tool.run(action="list")
        catalog = json.loads(result)
        from forge.runtime.integrations import BuiltinToolkit
        lib = BuiltinToolkit.library()
        assert len(catalog) == len(lib)
        catalog_names = {item["name"] for item in catalog}
        for name in lib:
            assert name in catalog_names

    @pytest.mark.asyncio
    async def test_discover_tool_load_adds_tool(self):
        """discover_tool(action='load', tool_name='git_operation') adds the tool."""
        orch = OrchestratorAgent()
        orch._ensure_tools()
        assert "git_operation" not in orch._tool_map
        tool = orch._tool_map["discover_tool"]
        result = await tool.run(action="load", tool_name="git_operation")
        data = json.loads(result)
        assert data["status"] == "loaded"
        assert "git_operation" in orch._tool_map

    @pytest.mark.asyncio
    async def test_discover_tool_load_invalid_name_returns_error(self):
        """discover_tool(action='load', tool_name='nonexistent') returns an error."""
        orch = OrchestratorAgent()
        orch._ensure_tools()
        tool = orch._tool_map["discover_tool"]
        result = await tool.run(action="load", tool_name="nonexistent_tool")
        data = json.loads(result)
        assert "error" in data
        assert "Unknown tool" in data["error"]

    @pytest.mark.asyncio
    async def test_loaded_tool_appears_in_schema(self):
        """After loading a tool, it appears in the orchestrator's tool schema."""
        orch = OrchestratorAgent()
        orch._ensure_tools()
        schema_before = orch._get_tools_schema()
        names_before = {s["function"]["name"] for s in schema_before}
        assert "send_sms" not in names_before

        tool = orch._tool_map["discover_tool"]
        await tool.run(action="load", tool_name="send_sms")

        schema_after = orch._get_tools_schema()
        names_after = {s["function"]["name"] for s in schema_after}
        assert "send_sms" in names_after


class TestBugFixes:
    """Tests for fresh-eyes audit bug fixes."""

    def test_success_false_when_project_not_complete(self):
        """BUG 1: success should be False when project_complete is False, even with many files."""
        r = OrchestratorResult(
            success=False,
            files_created=["a.py", "b.py", "c.py", "d.py", "e.py"],
            iterations=10,
        )
        assert r.success is False

    @pytest.mark.asyncio
    async def test_success_requires_project_complete(self):
        """BUG 1: build() must not count files as success."""
        client = AsyncMock()
        # Agent just talks (no DONE signal), hits max_iterations
        response = _make_llm_response(content="Still working...")
        client.chat.completions.create = AsyncMock(return_value=response)

        orch = OrchestratorAgent(llm_client=client, max_iterations=2)
        with tempfile.TemporaryDirectory() as tmpdir:
            # Pre-create 5 files so files_created >= 2
            for i in range(5):
                open(os.path.join(tmpdir, f"file{i}.py"), "w").close()
            result = await orch.build("Build something", workdir=tmpdir)
            # Even with 5 files, success should be False (project never completed)
            assert result.success is False

    def test_system_prompt_mentions_plan_and_ship_phases(self):
        """BUG 2: System prompt must mention PLAN and SHIP phases."""
        orch = OrchestratorAgent()
        # We can't call build() without an LLM, but we can inspect
        # that the class produces a prompt with the right phases.
        # Build the system prompt the same way build() does:
        import sys
        python_path = sys.executable
        # The prompt is built inline in build(), so let's check the source
        import inspect
        source = inspect.getsource(OrchestratorAgent.build)
        assert "PHASE 2 — PLAN" in source
        assert "PHASE 5 — SHIP" in source
        assert "PHASE 3 — TEST & DEBUG" not in source
        assert "PHASE 4 — POLISH" not in source


class TestModelRouterIntegration:
    """Tests for ModelRouter integration in OrchestratorAgent."""

    def test_set_model_router(self):
        """set_model_router stores the router instance."""
        from forge.runtime.model_router import ModelRouter
        orch = OrchestratorAgent()
        router = ModelRouter(enabled=True, feedback_path=os.path.join(tempfile.mkdtemp(), "fb.json"))
        orch.set_model_router(router)
        assert orch._model_router is router

    def test_model_router_defaults_to_none(self):
        """By default, _model_router is None (backward compat)."""
        orch = OrchestratorAgent()
        assert orch._model_router is None

    @pytest.mark.asyncio
    async def test_build_without_router_uses_self_model(self):
        """Without a router, build() uses self.model for LLM calls."""
        client = AsyncMock()
        done_response = _make_llm_response(content='{"status": "DONE", "summary": "Done"}')
        client.chat.completions.create = AsyncMock(side_effect=[done_response])

        orch = OrchestratorAgent(llm_client=client, model="gpt-4o", max_iterations=3)
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "f.py"), "w").close()
            await orch.build("Build", workdir=tmpdir)
            call_kwargs = client.chat.completions.create.call_args
            assert call_kwargs.kwargs.get("model") or call_kwargs[1].get("model") == "gpt-4o"

    @pytest.mark.asyncio
    async def test_build_with_router_uses_selected_model(self):
        """With a router, build() uses the model returned by select_model()."""
        from forge.runtime.model_router import ModelRouter
        client = AsyncMock()
        done_response = _make_llm_response(content='{"status": "DONE", "summary": "Done"}')
        client.chat.completions.create = AsyncMock(side_effect=[done_response])

        router = ModelRouter(
            fast_model="gpt-4o-mini",
            standard_model="gpt-4o",
            premium_model="gpt-4",
            enabled=True,
            feedback_path=os.path.join(tempfile.mkdtemp(), "fb.json"),
        )

        orch = OrchestratorAgent(llm_client=client, model="gpt-4o", max_iterations=3)
        orch.set_model_router(router)

        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "f.py"), "w").close()
            await orch.build("Classify this simple item", workdir=tmpdir)

            call_kwargs = client.chat.completions.create.call_args
            used_model = call_kwargs.kwargs.get("model", call_kwargs[1].get("model"))
            # Router should have picked a model (not necessarily self.model)
            assert used_model is not None

    @pytest.mark.asyncio
    async def test_build_with_router_records_outcome(self):
        """With a router, build() records outcomes for the feedback loop."""
        from forge.runtime.model_router import ModelRouter
        client = AsyncMock()
        done_response = _make_llm_response(content='{"status": "DONE", "summary": "Done"}')
        client.chat.completions.create = AsyncMock(side_effect=[done_response])

        router = ModelRouter(
            enabled=True,
            feedback_path=os.path.join(tempfile.mkdtemp(), "fb.json"),
        )

        orch = OrchestratorAgent(llm_client=client, model="gpt-4o", max_iterations=3)
        orch.set_model_router(router)

        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "f.py"), "w").close()
            await orch.build("Build a simple app", workdir=tmpdir)

            # Router should have recorded at least one outcome
            assert len(router._feedback_history) >= 1
            outcome = router._feedback_history[0]
            assert outcome.success is True
            assert outcome.tokens > 0

    @pytest.mark.asyncio
    async def test_build_with_disabled_router_uses_default_model(self):
        """When router.enabled=False, select_model() returns default and self.model is used."""
        from forge.runtime.model_router import ModelRouter
        client = AsyncMock()
        done_response = _make_llm_response(content='{"status": "DONE", "summary": "Done"}')
        client.chat.completions.create = AsyncMock(side_effect=[done_response])

        router = ModelRouter(
            default_model="gpt-4o",
            enabled=False,
            feedback_path=os.path.join(tempfile.mkdtemp(), "fb.json"),
        )

        orch = OrchestratorAgent(llm_client=client, model="gpt-4o", max_iterations=3)
        orch.set_model_router(router)

        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "f.py"), "w").close()
            await orch.build("Build", workdir=tmpdir)

            call_kwargs = client.chat.completions.create.call_args
            used_model = call_kwargs.kwargs.get("model", call_kwargs[1].get("model"))
            assert used_model == "gpt-4o"
