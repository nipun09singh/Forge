"""Tests for forge.runtime.confidence -- Confidence-Gated Autonomy (Principle 6)."""

import pytest

from forge.runtime.confidence import (
    ConfidenceScorer,
    ConfidenceScore,
    ConfidenceLevel,
)
from forge.runtime.agent import TaskResult


class TestConfidenceScorer:
    """Tests for the ConfidenceScorer heuristic engine."""

    def setup_method(self):
        self.scorer = ConfidenceScorer()

    # --- score_tool_call tests ---

    def test_score_tool_call_read_only_high(self):
        """Read-only tools should score HIGH confidence."""
        result = self.scorer.score_tool_call("web_search", {"query": "python docs"})
        assert result.level == ConfidenceLevel.HIGH
        assert result.score >= 0.9
        assert result.action == "auto"

    def test_score_tool_call_write_medium(self):
        """Write tools should score MEDIUM confidence."""
        result = self.scorer.score_tool_call("write_file", {"path": "out.txt", "content": "hi"})
        assert result.level == ConfidenceLevel.MEDIUM
        assert 0.5 <= result.score < 0.9
        assert result.action == "flag"

    def test_score_tool_call_destructive_low(self):
        """Destructive tools should score LOW confidence."""
        result = self.scorer.score_tool_call("delete", {"path": "/important"})
        assert result.level == ConfidenceLevel.LOW
        assert result.score < 0.5
        assert result.action == "pause"

    def test_score_tool_call_unknown_medium(self):
        """Unknown tools default to MEDIUM confidence."""
        result = self.scorer.score_tool_call("custom_tool_xyz", {})
        assert result.level == ConfidenceLevel.MEDIUM
        assert result.action == "flag"

    # --- score_output tests ---

    def test_score_output_high_quality(self):
        """Good quality score should produce HIGH confidence."""
        result = self.scorer.score_output(
            output="This is a comprehensive, well-structured answer with details.",
            task="Explain Python decorators",
            quality_score=0.95,
        )
        assert result.level == ConfidenceLevel.HIGH
        assert result.score >= 0.9

    def test_score_output_hedging_language_low(self):
        """Hedging language should lower confidence."""
        result = self.scorer.score_output(
            output="I'm not sure, but maybe this could be the answer. I think it might work, possibly.",
            task="Explain Python decorators",
            quality_score=0.0,
        )
        assert result.level == ConfidenceLevel.LOW
        assert result.score < 0.5

    def test_score_output_very_short_low(self):
        """Very short output should be LOW confidence."""
        result = self.scorer.score_output(
            output="OK",
            task="Write a full report on AI trends",
            quality_score=0.0,
        )
        assert result.level == ConfidenceLevel.LOW
        assert result.score < 0.5

    def test_score_output_empty(self):
        """Empty output should be LOW confidence with score 0."""
        result = self.scorer.score_output(output="", task="Do something")
        assert result.score == 0.0
        assert result.level == ConfidenceLevel.LOW
        assert result.action == "pause"

    # --- classify tests ---

    def test_classify_boundary_zero(self):
        assert self.scorer.classify(0.0) == ConfidenceLevel.LOW

    def test_classify_boundary_low_threshold(self):
        assert self.scorer.classify(0.5) == ConfidenceLevel.MEDIUM

    def test_classify_boundary_high_threshold(self):
        assert self.scorer.classify(0.9) == ConfidenceLevel.HIGH

    def test_classify_boundary_one(self):
        assert self.scorer.classify(1.0) == ConfidenceLevel.HIGH

    def test_classify_just_below_low(self):
        assert self.scorer.classify(0.49) == ConfidenceLevel.LOW

    def test_classify_just_below_high(self):
        assert self.scorer.classify(0.89) == ConfidenceLevel.MEDIUM


class TestTaskResultConfidence:
    """Test that TaskResult includes confidence fields."""

    def test_task_result_default_confidence(self):
        result = TaskResult(success=True, output="done")
        assert result.confidence == 1.0
        assert result.confidence_level == "high"

    def test_task_result_custom_confidence(self):
        result = TaskResult(
            success=True,
            output="done",
            confidence=0.6,
            confidence_level="medium",
        )
        assert result.confidence == 0.6
        assert result.confidence_level == "medium"

    def test_task_result_low_confidence(self):
        result = TaskResult(
            success=True,
            output="maybe",
            confidence=0.3,
            confidence_level="low",
        )
        assert result.confidence == 0.3
        assert result.confidence_level == "low"


class TestConfidenceDataClasses:
    """Test confidence data classes and enum."""

    def test_confidence_level_values(self):
        assert ConfidenceLevel.HIGH == "high"
        assert ConfidenceLevel.MEDIUM == "medium"
        assert ConfidenceLevel.LOW == "low"

    def test_confidence_score_creation(self):
        cs = ConfidenceScore(
            score=0.85,
            level=ConfidenceLevel.MEDIUM,
            reasoning="test reason",
            action="flag",
        )
        assert cs.score == 0.85
        assert cs.level == ConfidenceLevel.MEDIUM
        assert cs.reasoning == "test reason"
        assert cs.action == "flag"


class TestConfidenceGating:
    """Tests for confidence-gated autonomy enforcement in orchestrator and agent."""

    @pytest.mark.asyncio
    async def test_low_confidence_tool_call_blocked_in_orchestrator(self):
        """LOW confidence tool calls should be BLOCKED (not executed) in orchestrator."""
        import json
        import tempfile
        from unittest.mock import AsyncMock, MagicMock
        from forge.runtime.orchestrator import OrchestratorAgent

        client = AsyncMock()
        # First response: call a destructive tool (LOW confidence)
        tc = MagicMock()
        tc.id = "tc-low"
        tc.function.name = "delete"
        tc.function.arguments = json.dumps({"path": "/important"})
        resp1 = MagicMock()
        resp1.choices = [MagicMock()]
        resp1.choices[0].message.content = ""
        resp1.choices[0].message.tool_calls = [tc]
        resp1.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        # Second response: DONE
        resp2 = MagicMock()
        resp2.choices = [MagicMock()]
        resp2.choices[0].message.content = '{"status": "DONE", "summary": "finished"}'
        resp2.choices[0].message.tool_calls = None
        resp2.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        client.chat.completions.create = AsyncMock(side_effect=[resp1, resp2])

        orch = OrchestratorAgent(llm_client=client, max_iterations=5)
        orch._ensure_tools()
        # Inject a mock "delete" tool to verify it is NOT called
        mock_tool = MagicMock()
        mock_tool.name = "delete"
        mock_tool.run = AsyncMock(return_value="deleted")
        mock_tool.schema = {"type": "function", "function": {"name": "delete", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}}
        orch._tools.append(mock_tool)
        orch._tool_map["delete"] = mock_tool

        with tempfile.TemporaryDirectory() as tmpdir:
            import os
            open(os.path.join(tmpdir, "dummy.py"), "w").close()
            await orch.build("Test task", workdir=tmpdir)

        # The destructive tool should NOT have been executed
        mock_tool.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_medium_confidence_tool_call_proceeds_in_orchestrator(self):
        """MEDIUM confidence tool calls should PROCEED (be executed) in orchestrator."""
        import json
        import tempfile
        from unittest.mock import AsyncMock, MagicMock
        from forge.runtime.orchestrator import OrchestratorAgent

        client = AsyncMock()
        # First response: call a write tool (MEDIUM confidence)
        tc = MagicMock()
        tc.id = "tc-med"
        tc.function.name = "read_write_file"
        tc.function.arguments = json.dumps({"action": "write", "path": "out.py", "content": "x=1"})
        resp1 = MagicMock()
        resp1.choices = [MagicMock()]
        resp1.choices[0].message.content = ""
        resp1.choices[0].message.tool_calls = [tc]
        resp1.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        # Second response: DONE
        resp2 = MagicMock()
        resp2.choices = [MagicMock()]
        resp2.choices[0].message.content = '{"status": "DONE", "summary": "finished"}'
        resp2.choices[0].message.tool_calls = None
        resp2.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        client.chat.completions.create = AsyncMock(side_effect=[resp1, resp2])

        orch = OrchestratorAgent(llm_client=client, max_iterations=5)
        with tempfile.TemporaryDirectory() as tmpdir:
            await orch.build("Test task", workdir=tmpdir)
            # read_write_file is a built-in tool — it should have been executed
            # If the file was created, the tool ran
            import os
            assert os.path.exists(os.path.join(tmpdir, "out.py"))

    @pytest.mark.asyncio
    async def test_high_confidence_tool_call_proceeds_silently(self):
        """HIGH confidence tool calls should PROCEED silently."""
        import json
        import tempfile
        from unittest.mock import AsyncMock, MagicMock
        from forge.runtime.orchestrator import OrchestratorAgent

        client = AsyncMock()
        # First response: call a read-only tool (HIGH confidence)
        tc = MagicMock()
        tc.id = "tc-high"
        tc.function.name = "web_search"
        tc.function.arguments = json.dumps({"query": "python docs"})
        resp1 = MagicMock()
        resp1.choices = [MagicMock()]
        resp1.choices[0].message.content = ""
        resp1.choices[0].message.tool_calls = [tc]
        resp1.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        # Second response: DONE
        resp2 = MagicMock()
        resp2.choices = [MagicMock()]
        resp2.choices[0].message.content = '{"status": "DONE", "summary": "finished"}'
        resp2.choices[0].message.tool_calls = None
        resp2.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        client.chat.completions.create = AsyncMock(side_effect=[resp1, resp2])

        orch = OrchestratorAgent(llm_client=client, max_iterations=5)
        orch._ensure_tools()
        # The web_search tool exists in built-in tools — it should run without issue
        with tempfile.TemporaryDirectory() as tmpdir:
            import os
            open(os.path.join(tmpdir, "dummy.py"), "w").close()
            await orch.build("Test task", workdir=tmpdir)
        # If we got here without error, high-confidence tool proceeded

    @pytest.mark.asyncio
    async def test_low_confidence_output_triggers_retry_nudge(self):
        """LOW confidence output should trigger a retry nudge, not accept completion."""
        import json
        import tempfile
        from unittest.mock import AsyncMock, MagicMock, patch
        from forge.runtime.orchestrator import OrchestratorAgent

        client = AsyncMock()
        # First response: hedging/short DONE text (triggers LOW confidence on output)
        resp1 = MagicMock()
        resp1.choices = [MagicMock()]
        resp1.choices[0].message.content = '{"status": "DONE", "summary": "ok"}'
        resp1.choices[0].message.tool_calls = None
        resp1.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        # Second response: a proper DONE (will pass confidence)
        resp2 = MagicMock()
        resp2.choices = [MagicMock()]
        resp2.choices[0].message.content = '{"status": "DONE", "summary": "Complete implementation with full test coverage and documentation"}'
        resp2.choices[0].message.tool_calls = None
        resp2.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        client.chat.completions.create = AsyncMock(side_effect=[resp1, resp2])

        orch = OrchestratorAgent(llm_client=client, max_iterations=5)
        with tempfile.TemporaryDirectory() as tmpdir:
            import os
            open(os.path.join(tmpdir, "dummy.py"), "w").close()
            result = await orch.build("Build a full app", workdir=tmpdir)
        # Should have taken 2 iterations (first was nudged, second accepted)
        assert result.iterations >= 2

    @pytest.mark.asyncio
    async def test_score_output_called_on_final_text(self):
        """score_output() should be called when orchestrator receives text output with completion signal."""
        import json
        import tempfile
        from unittest.mock import AsyncMock, MagicMock, patch
        from forge.runtime.orchestrator import OrchestratorAgent
        from forge.runtime.confidence import ConfidenceScorer

        client = AsyncMock()
        # First response: create a file via tool call
        tc = MagicMock()
        tc.id = "tc-file"
        tc.function.name = "read_write_file"
        tc.function.arguments = json.dumps({"action": "write", "path": "app.py", "content": "print('hi')"})
        resp1 = MagicMock()
        resp1.choices = [MagicMock()]
        resp1.choices[0].message.content = ""
        resp1.choices[0].message.tool_calls = [tc]
        resp1.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        # Second response: DONE with text
        resp2 = MagicMock()
        resp2.choices = [MagicMock()]
        resp2.choices[0].message.content = '{"status": "DONE", "summary": "Built a comprehensive project with all features"}'
        resp2.choices[0].message.tool_calls = None
        resp2.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        client.chat.completions.create = AsyncMock(side_effect=[resp1, resp2])

        orch = OrchestratorAgent(llm_client=client, max_iterations=5)

        with patch.object(orch._confidence_scorer, 'score_output', wraps=orch._confidence_scorer.score_output) as mock_score_output:
            with tempfile.TemporaryDirectory() as tmpdir:
                await orch.build("Build something", workdir=tmpdir)
            mock_score_output.assert_called()

    @pytest.mark.asyncio
    async def test_agent_low_confidence_tool_blocked_without_approval_gate(self):
        """In agent.py, LOW confidence tool without approval gate should be blocked."""
        import json
        from unittest.mock import AsyncMock, MagicMock
        from forge.runtime.agent import Agent
        from forge.runtime.tools import ToolRegistry, Tool

        agent = Agent(name="test-agent", role="tester", system_prompt="You are a test agent.")
        # Register a destructive tool
        mock_tool = MagicMock(spec=Tool)
        mock_tool.name = "delete"
        mock_tool.run = AsyncMock(return_value="deleted")
        agent.tool_registry = ToolRegistry()
        agent.tool_registry.register(mock_tool)

        tc = {
            "id": "tc-1",
            "function": {"name": "delete", "arguments": json.dumps({"path": "/data"})},
        }
        result = await agent._execute_single_tool(tc)
        assert "blocked" in result["output"].lower() or "low confidence" in result["output"].lower() or "denied" in result["output"].lower()
        mock_tool.run.assert_not_called()
