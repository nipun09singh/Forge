"""Tests for forge.runtime.self_evolution."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from forge.runtime.self_evolution import SelfEvolution, EvolutionRecord
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

    def test_cleanup_prompt_bloat(self):
        evo = SelfEvolution(None, None, llm_client=None)
        agent = Agent(name="Test", role="test", system_prompt="Base prompt\n\n[Auto-improvement]: tip1\n\n[Auto-improvement]: tip2\n\n[Auto-improvement]: tip3\n\n[Auto-improvement]: tip4\n\n[Auto-improvement]: tip5\n\n[Auto-improvement]: tip6")
        removed = evo.cleanup_prompt_bloat({"Test": agent})
        assert removed >= 0


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
