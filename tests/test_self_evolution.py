"""Tests for forge.runtime.self_evolution."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from forge.runtime.self_evolution import SelfEvolution, EvolutionRecord, PromptOptimizer, OptimizationResult
from forge.runtime.improvement import PerformanceTracker, TaskMetric
from forge.runtime.memory import SharedMemory
from forge.runtime.agent import Agent


def _make_tracker_with_data(agent_name="TestAgent", successes=8, failures=2):
    """Create a PerformanceTracker with pre-loaded metrics."""
    tracker = PerformanceTracker()
    for i in range(successes):
        tracker.record(TaskMetric(
            agent_name=agent_name, task_preview=f"task_{i}",
            success=True, quality_score=0.8, duration_seconds=5.0,
        ))
    for i in range(failures):
        tracker.record(TaskMetric(
            agent_name=agent_name, task_preview=f"failed_task_{i}",
            success=False, quality_score=0.0, duration_seconds=10.0,
        ))
    return tracker


class TestSelfEvolutionInit:
    """Tests for SelfEvolution initialization."""

    def test_init(self):
        tracker = PerformanceTracker()
        memory = SharedMemory()
        evo = SelfEvolution(tracker, memory, llm_client=AsyncMock())
        assert evo._cycle_count == 0
        assert evo._tracker is tracker

    def test_init_none_tracker(self):
        evo = SelfEvolution(None, None, llm_client=None)
        assert evo._tracker is None


class TestEvolutionCycle:
    """Tests for run_evolution_cycle."""

    @pytest.mark.asyncio
    async def test_skips_with_no_tracker(self):
        evo = SelfEvolution(None, None, llm_client=AsyncMock())
        records = await evo.run_evolution_cycle()
        assert records == []

    @pytest.mark.asyncio
    async def test_skips_with_insufficient_data(self):
        """Needs 5+ tasks before evolving."""
        tracker = PerformanceTracker()
        tracker.record(TaskMetric(agent_name="A", task_preview="t", success=True, quality_score=1.0, duration_seconds=1.0))
        evo = SelfEvolution(tracker, SharedMemory(), llm_client=AsyncMock())
        records = await evo.run_evolution_cycle()
        assert records == []

    @pytest.mark.asyncio
    async def test_increments_cycle_count(self):
        tracker = _make_tracker_with_data(successes=10, failures=0)
        client = AsyncMock()
        # Return empty improvements
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = '{"improvements": []}'
        client.chat.completions.create = AsyncMock(return_value=resp)

        evo = SelfEvolution(tracker, SharedMemory(), llm_client=client)
        await evo.run_evolution_cycle()
        assert evo._cycle_count == 1

    @pytest.mark.asyncio
    async def test_returns_evolution_records(self):
        tracker = _make_tracker_with_data(successes=8, failures=2)
        client = AsyncMock()
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = json.dumps({"improvements": [{
            "target_agent": "TestAgent",
            "issue": "Low quality",
            "improved_prompt_addition": "Always verify your work thoroughly.",
            "expected_impact": "Better quality",
        }]})
        client.chat.completions.create = AsyncMock(return_value=resp)

        evo = SelfEvolution(tracker, SharedMemory(), llm_client=client)
        # Provide an agent to mutate
        agent = Agent(name="TestAgent", role="test", system_prompt="Original prompt")
        agent.set_llm_client(client)
        records = await evo.run_evolution_cycle(agents={"TestAgent": agent})
        assert evo._cycle_count == 1


class TestEvolutionHistory:
    """Tests for history and stats tracking."""

    def test_get_history_empty(self):
        evo = SelfEvolution(None, None, llm_client=None)
        assert evo.get_history() == []

    def test_get_stats(self):
        evo = SelfEvolution(None, None, llm_client=None)
        stats = evo.get_stats()
        assert "cycles_completed" in stats
        assert stats["cycles_completed"] == 0



class TestEvolutionRecord:
    """Tests for EvolutionRecord dataclass."""

    def test_creation(self):
        rec = EvolutionRecord(
            target_agent="TestAgent",
            change_type="prompt_update",
            description="Added verification step",
            before_score=0.7, after_score=0.85,
            applied=True,
        )
        assert rec.target_agent == "TestAgent"
        assert rec.applied is True
        assert rec.after_score > rec.before_score


class TestDeepMutations:
    """Tests for deep self-improvement mutations (model, temp, reflection, iterations)."""

    def _make_agent(self, name="TestAgent", model="gpt-4", temperature=0.5,
                    enable_reflection=False, max_iterations=20):
        agent = Agent(name=name, role="test", system_prompt="Test agent")
        agent.model = model
        agent.temperature = temperature
        agent.enable_reflection = enable_reflection
        agent.max_iterations = max_iterations
        return agent

    def _make_tracker_for_agent(self, agent_name, success_rate=0.9, quality=0.8, count=10):
        tracker = PerformanceTracker()
        successes = int(count * success_rate)
        failures = count - successes
        for i in range(successes):
            tracker.record(TaskMetric(
                agent_name=agent_name, task_preview=f"task_{i}",
                success=True, quality_score=quality, duration_seconds=5.0,
            ))
        for i in range(failures):
            tracker.record(TaskMetric(
                agent_name=agent_name, task_preview=f"fail_{i}",
                success=False, quality_score=0.0, duration_seconds=10.0,
            ))
        return tracker

    @pytest.mark.asyncio
    async def test_model_downgrade_on_high_success(self):
        """High-performing agent on expensive model gets downgraded."""
        agent = self._make_agent(model="gpt-4")
        tracker = self._make_tracker_for_agent("TestAgent", success_rate=1.0, quality=0.9, count=10)
        agent._performance_tracker = tracker

        client = AsyncMock()
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = '{"improvements": []}'
        client.chat.completions.create = AsyncMock(return_value=resp)

        evo = SelfEvolution(tracker, SharedMemory(), llm_client=client)
        records = await evo.run_evolution_cycle(agents={"TestAgent": agent})

        # Should have attempted a model downgrade
        model_records = [r for r in records if r.change_type == "model_downgrade"]
        assert len(model_records) > 0, "Expected at least one model_downgrade record"
        assert agent.model in ("gpt-4o", "gpt-4o-mini")

    @pytest.mark.asyncio
    async def test_temperature_decrease_on_low_success(self):
        """Struggling agent gets lower temperature for consistency."""
        agent = self._make_agent(temperature=0.7)
        tracker = self._make_tracker_for_agent("TestAgent", success_rate=0.5, quality=0.5, count=10)
        agent._performance_tracker = tracker

        client = AsyncMock()
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = '{"improvements": []}'
        client.chat.completions.create = AsyncMock(return_value=resp)

        evo = SelfEvolution(tracker, SharedMemory(), llm_client=client)
        records = await evo.run_evolution_cycle(agents={"TestAgent": agent})

        temp_records = [r for r in records if r.change_type == "temperature_decrease"]
        assert len(temp_records) > 0, "Expected at least one temperature_decrease record"
        assert agent.temperature < 0.7

    @pytest.mark.asyncio
    async def test_reflection_enabled_for_low_quality(self):
        """Low-quality agent gets reflection enabled."""
        agent = self._make_agent(enable_reflection=False)
        tracker = self._make_tracker_for_agent("TestAgent", success_rate=0.6, quality=0.4, count=10)
        agent._performance_tracker = tracker

        client = AsyncMock()
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = '{"improvements": []}'
        client.chat.completions.create = AsyncMock(return_value=resp)

        evo = SelfEvolution(tracker, SharedMemory(), llm_client=client)
        records = await evo.run_evolution_cycle(agents={"TestAgent": agent})

        reflection_records = [r for r in records if r.change_type == "enable_reflection"]
        assert len(reflection_records) > 0, "Expected at least one enable_reflection record"
        assert agent.enable_reflection is True

    @pytest.mark.asyncio
    async def test_no_mutation_with_insufficient_data(self):
        """Agents with <5 tasks don't get mutated."""
        agent = self._make_agent()
        tracker = self._make_tracker_for_agent("TestAgent", success_rate=0.5, quality=0.5, count=3)

        client = AsyncMock()
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = "[]"
        client.chat.completions.create = AsyncMock(return_value=resp)

        evo = SelfEvolution(tracker, SharedMemory(), llm_client=client)
        records = await evo.run_evolution_cycle(agents={"TestAgent": agent})

        # Should not have any deep mutation records
        deep_types = {"model_downgrade", "temperature_decrease", "temperature_increase", "enable_reflection", "increase_iterations"}
        deep_records = [r for r in records if r.change_type in deep_types]
        assert len(deep_records) == 0


class TestMutationRollback:
    """Tests for rollback safety on deep mutations."""

    def test_rollback_exists(self):
        """rollback_mutation method exists."""
        evo = SelfEvolution(None, None, llm_client=None)
        assert hasattr(evo, 'rollback_mutation')

    @pytest.mark.asyncio
    async def test_rollback_returns_false_without_tracker(self):
        evo = SelfEvolution(None, None, llm_client=None)
        agent = Agent(name="Test", role="test", system_prompt="test")
        record = EvolutionRecord(target_agent="Test", change_type="model_downgrade",
                                 description="test", before_score=0.9, after_score=0.9, applied=True)
        assert await evo.rollback_mutation(agent, record) is False


def _mock_llm_response(content: str) -> MagicMock:
    """Create a mock LLM response with the given content."""
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    return resp


class TestPromptOptimizerInit:
    """Tests for PromptOptimizer initialization."""

    def test_init_with_tracker(self):
        tracker = PerformanceTracker()
        client = AsyncMock()
        optimizer = PromptOptimizer(client, tracker)
        assert optimizer.tracker is tracker
        assert optimizer.llm_client is client
        assert optimizer.metric_fn is not None

    def test_init_with_custom_metric(self):
        custom_fn = lambda *a, **kw: 0.99
        optimizer = PromptOptimizer(AsyncMock(), PerformanceTracker(), metric_fn=custom_fn)
        assert optimizer.metric_fn is custom_fn


class TestDefaultMetric:
    """Tests for PromptOptimizer._default_metric (real task execution)."""

    @pytest.mark.asyncio
    async def test_returns_neutral_when_no_failures(self):
        """_default_metric should return 0.5 when the agent has no failure data."""
        tracker = _make_tracker_with_data("TestAgent", successes=10, failures=0)
        client = AsyncMock()
        optimizer = PromptOptimizer(client, tracker)
        score = await optimizer._default_metric("Some prompt", "TestAgent")
        assert score == 0.5

    @pytest.mark.asyncio
    async def test_creates_agent_and_runs_task(self):
        """_default_metric should create a test agent, run a failing task, and score based on result."""
        tracker = _make_tracker_with_data("TestAgent", successes=5, failures=3)
        client = AsyncMock()
        optimizer = PromptOptimizer(client, tracker)

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.confidence = 0.9

        with patch("forge.runtime.agent.Agent") as MockAgent:
            mock_agent_instance = MagicMock()
            mock_agent_instance.execute = AsyncMock(return_value=mock_result)
            MockAgent.return_value = mock_agent_instance

            score = await optimizer._default_metric("Test prompt", "TestAgent")

            MockAgent.assert_called_once_with(
                name="_eval_TestAgent",
                role="specialist",
                system_prompt="Test prompt",
            )
            mock_agent_instance.set_llm_client.assert_called_once_with(client)
            mock_agent_instance.execute.assert_called_once()
            assert score == min(1.0, 0.7 + 0.9 * 0.3)

    @pytest.mark.asyncio
    async def test_returns_timeout_score_on_timeout(self):
        """_default_metric should return 0.4 when the agent execution times out."""
        tracker = _make_tracker_with_data("TestAgent", successes=5, failures=3)
        client = AsyncMock()
        optimizer = PromptOptimizer(client, tracker)

        with patch("forge.runtime.agent.Agent") as MockAgent:
            mock_agent_instance = MagicMock()
            mock_agent_instance.execute = AsyncMock(side_effect=asyncio.TimeoutError())
            MockAgent.return_value = mock_agent_instance

            score = await optimizer._default_metric("Test prompt", "TestAgent")
            assert score == 0.4


async def _async_metric_stub(candidate_prompt, agent_name):
    """Simple async metric stub for compile tests: scores based on content length."""
    return min(1.0, len(candidate_prompt) / 100.0)


class TestPromptOptimizerCompile:
    """Tests for PromptOptimizer.compile()."""

    @pytest.mark.asyncio
    async def test_skips_with_insufficient_data(self):
        """compile() should skip when agent has fewer than min_samples tasks."""
        tracker = PerformanceTracker()
        for i in range(3):
            tracker.record(TaskMetric(
                agent_name="TestAgent", task_preview=f"task_{i}",
                success=True, quality_score=0.8, duration_seconds=5.0,
            ))
        client = AsyncMock()
        optimizer = PromptOptimizer(client, tracker)
        agent = Agent(name="TestAgent", role="test", system_prompt="Original prompt")
        result = await optimizer.compile(agent)
        assert not result.improved
        assert "insufficient data" in result.reason

    @pytest.mark.asyncio
    async def test_generates_candidates_via_llm(self):
        """compile() should call the LLM to generate candidate prompt rewrites."""
        tracker = _make_tracker_with_data("TestAgent", successes=8, failures=4)
        client = AsyncMock()
        client.chat.completions.create = AsyncMock(
            return_value=_mock_llm_response("Improved prompt that handles failed_task errors better")
        )
        optimizer = PromptOptimizer(client, tracker, metric_fn=_async_metric_stub)
        agent = Agent(name="TestAgent", role="test", system_prompt="Original prompt")
        result = await optimizer.compile(agent, n_candidates=3, min_samples=5)
        assert client.chat.completions.create.call_count == 3
        assert result.candidates_evaluated == 3

    @pytest.mark.asyncio
    async def test_picks_best_candidate(self):
        """compile() should pick the highest-scoring candidate."""
        tracker = _make_tracker_with_data("TestAgent", successes=7, failures=5)
        client = AsyncMock()
        call_count = 0

        async def varying_responses(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return _mock_llm_response("Better prompt addressing failed_task issues directly -- this one is longer to score higher in the stub metric")
            return _mock_llm_response("Short")

        client.chat.completions.create = AsyncMock(side_effect=varying_responses)
        optimizer = PromptOptimizer(client, tracker, metric_fn=_async_metric_stub)
        agent = Agent(name="TestAgent", role="test", system_prompt="Original prompt")
        result = await optimizer.compile(agent, n_candidates=3, min_samples=5)
        assert result.improved
        assert "failed_task" in result.new_prompt.lower()

    @pytest.mark.asyncio
    async def test_replaces_prompt_not_appends(self):
        """compile() must REPLACE the system prompt entirely, not append."""
        tracker = _make_tracker_with_data("TestAgent", successes=7, failures=5)
        client = AsyncMock()
        new_prompt_text = "Completely new prompt addressing failed_task patterns -- long enough to outscore original in stub metric"
        client.chat.completions.create = AsyncMock(
            return_value=_mock_llm_response(new_prompt_text)
        )
        optimizer = PromptOptimizer(client, tracker, metric_fn=_async_metric_stub)
        original = "Short"
        agent = Agent(name="TestAgent", role="test", system_prompt=original)
        result = await optimizer.compile(agent, n_candidates=1, min_samples=5)
        assert result.improved
        assert original not in agent.system_prompt
        assert agent.system_prompt == new_prompt_text

    @pytest.mark.asyncio
    async def test_stores_old_prompt_for_rollback(self):
        """compile() must store the old prompt in the result for rollback."""
        tracker = _make_tracker_with_data("TestAgent", successes=7, failures=5)
        client = AsyncMock()
        client.chat.completions.create = AsyncMock(
            return_value=_mock_llm_response("New prompt addressing failed_task errors -- long enough to outscore")
        )
        optimizer = PromptOptimizer(client, tracker, metric_fn=_async_metric_stub)
        original = "Short"
        agent = Agent(name="TestAgent", role="test", system_prompt=original)
        result = await optimizer.compile(agent, n_candidates=1, min_samples=5)
        assert result.old_prompt == original

    @pytest.mark.asyncio
    async def test_no_improvement_when_no_candidates_score_better(self):
        """compile() should not replace prompt if no candidate scores better."""
        tracker = _make_tracker_with_data("TestAgent", successes=10, failures=0)
        client = AsyncMock()
        client.chat.completions.create = AsyncMock(
            return_value=_mock_llm_response("Short")
        )

        async def always_low(candidate_prompt, agent_name):
            return 0.1

        optimizer = PromptOptimizer(client, tracker, metric_fn=always_low)
        original = "Original prompt"
        agent = Agent(name="TestAgent", role="test", system_prompt=original)
        result = await optimizer.compile(agent, n_candidates=2, min_samples=5)
        assert not result.improved
        assert agent.system_prompt == original


class TestRollbackWiring:
    """Tests that rollback_mutation is wired into the evolution cycle and works correctly."""

    def _make_agent(self, name="TestAgent", model="gpt-4", temperature=0.5,
                    enable_reflection=False, max_iterations=20):
        agent = Agent(name=name, role="test", system_prompt="Test agent")
        agent.model = model
        agent.temperature = temperature
        agent.enable_reflection = enable_reflection
        agent.max_iterations = max_iterations
        return agent

    def _make_tracker_for_agent(self, agent_name, success_rate=0.9, quality=0.8, count=10):
        tracker = PerformanceTracker()
        successes = int(count * success_rate)
        failures = count - successes
        for i in range(successes):
            tracker.record(TaskMetric(
                agent_name=agent_name, task_preview=f"task_{i}",
                success=True, quality_score=quality, duration_seconds=5.0,
            ))
        for i in range(failures):
            tracker.record(TaskMetric(
                agent_name=agent_name, task_preview=f"fail_{i}",
                success=False, quality_score=0.0, duration_seconds=10.0,
            ))
        return tracker

    @pytest.mark.asyncio
    async def test_rollback_called_after_deep_mutations(self):
        """rollback_mutation IS called after deep mutations are applied."""
        agent = self._make_agent(model="gpt-4")
        tracker = self._make_tracker_for_agent("TestAgent", success_rate=1.0, quality=0.9, count=10)
        agent._performance_tracker = tracker

        client = AsyncMock()
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = '{"improvements": []}'
        client.chat.completions.create = AsyncMock(return_value=resp)

        evo = SelfEvolution(tracker, SharedMemory(), llm_client=client)

        with patch.object(evo, 'rollback_mutation', new_callable=AsyncMock, return_value=False) as mock_rollback:
            records = await evo.run_evolution_cycle(agents={"TestAgent": agent})
            # Deep mutation should have triggered a model_downgrade, so rollback_mutation should be called
            assert mock_rollback.call_count > 0
            # Verify it was called with the agent and a mutation record
            call_args = mock_rollback.call_args
            assert call_args[0][0] is agent
            assert call_args[0][1].change_type in {"model_downgrade", "temperature_decrease", "temperature_increase", "enable_reflection", "increase_iterations"}

    @pytest.mark.asyncio
    async def test_rollback_restores_on_performance_drop(self):
        """rollback_mutation restores agent state when performance drops >10%."""
        agent = self._make_agent(model="gpt-4o-mini")
        # Tracker shows current performance at 0.7 (dropped from 0.9)
        tracker = self._make_tracker_for_agent("TestAgent", success_rate=0.7, quality=0.7, count=10)

        evo = SelfEvolution(tracker, SharedMemory(), llm_client=AsyncMock())
        record = EvolutionRecord(
            target_agent="TestAgent", change_type="model_downgrade",
            description="Downgraded model", before_score=0.9, after_score=0.9, applied=True,
        )

        # current_success (0.7) < before_score (0.9) - 0.1 = 0.8 → rollback
        result = await evo.rollback_mutation(agent, record)
        assert result is True
        assert agent.model == "gpt-4o"  # restored to more expensive model

    @pytest.mark.asyncio
    async def test_rollback_no_restore_when_performance_holds(self):
        """rollback_mutation does NOT restore when performance holds."""
        agent = self._make_agent(model="gpt-4o-mini")
        # Tracker shows current performance at 0.85 (only slight drop from 0.9)
        tracker = self._make_tracker_for_agent("TestAgent", success_rate=0.85, quality=0.85, count=20)

        evo = SelfEvolution(tracker, SharedMemory(), llm_client=AsyncMock())
        record = EvolutionRecord(
            target_agent="TestAgent", change_type="model_downgrade",
            description="Downgraded model", before_score=0.9, after_score=0.9, applied=True,
        )

        # current_success (0.85) < before_score (0.9) - 0.1 = 0.8 → False, no rollback
        result = await evo.rollback_mutation(agent, record)
        assert result is False
        assert agent.model == "gpt-4o-mini"  # unchanged

    @pytest.mark.asyncio
    async def test_no_auto_improvement_in_prompts_after_evolution(self):
        """Prompt-append path is REMOVED — no [Auto-improvement] text after evolution."""
        tracker = _make_tracker_with_data(successes=8, failures=2)
        client = AsyncMock()
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = json.dumps({"improvements": [{
            "target_agent": "TestAgent",
            "issue": "Low quality",
            "improved_prompt_addition": "Always verify your work thoroughly.",
            "expected_impact": "Better quality",
        }]})
        client.chat.completions.create = AsyncMock(return_value=resp)

        evo = SelfEvolution(tracker, SharedMemory(), llm_client=client)
        agent = Agent(name="TestAgent", role="test", system_prompt="Original prompt")
        agent.set_llm_client(client)
        await evo.run_evolution_cycle(agents={"TestAgent": agent})

        # The old prompt-append path should be gone
        assert "[Auto-improvement]" not in agent.system_prompt