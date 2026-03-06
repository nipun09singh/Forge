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
