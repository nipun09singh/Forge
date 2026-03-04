"""A/B testing — run agent variants in parallel and auto-promote winners."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from forge.runtime.agent import Agent

logger = logging.getLogger(__name__)


@dataclass
class AgentVariant:
    """A variant of an agent for A/B testing."""
    id: str = field(default_factory=lambda: f"var-{uuid.uuid4().hex[:8]}")
    name: str = ""
    system_prompt: str = ""
    model: str = ""
    temperature: float = 0.7
    description: str = ""  # What's different about this variant


@dataclass
class VariantMetrics:
    """Metrics for one variant during a test."""
    variant_id: str = ""
    tasks_run: int = 0
    successes: int = 0
    total_quality_score: float = 0.0
    total_cost_usd: float = 0.0
    total_duration_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.successes / max(self.tasks_run, 1)

    @property
    def avg_quality(self) -> float:
        return self.total_quality_score / max(self.tasks_run, 1)

    @property
    def avg_cost(self) -> float:
        return self.total_cost_usd / max(self.tasks_run, 1)

    @property
    def avg_duration(self) -> float:
        return self.total_duration_ms / max(self.tasks_run, 1)


@dataclass
class ABTestResult:
    """Results of an A/B test."""
    id: str = field(default_factory=lambda: f"test-{uuid.uuid4().hex[:8]}")
    control: VariantMetrics = field(default_factory=VariantMetrics)
    experiment: VariantMetrics = field(default_factory=VariantMetrics)
    winner: str = ""  # "control", "experiment", "inconclusive"
    improvement_pct: float = 0.0
    tasks_total: int = 0
    status: str = "running"  # running, completed, stopped
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "control": {"success_rate": self.control.success_rate, "avg_quality": self.control.avg_quality, "avg_cost": self.control.avg_cost, "tasks": self.control.tasks_run},
            "experiment": {"success_rate": self.experiment.success_rate, "avg_quality": self.experiment.avg_quality, "avg_cost": self.experiment.avg_cost, "tasks": self.experiment.tasks_run},
            "winner": self.winner,
            "improvement_pct": self.improvement_pct,
            "status": self.status,
        }


class ABTestManager:
    """
    Runs A/B tests on agent variants to continuously optimize performance.
    
    Creates two copies of an agent with different configs (prompt, model, temperature),
    runs both on incoming tasks, compares metrics, and identifies the winner.
    """

    def __init__(self) -> None:
        self._active_tests: dict[str, dict[str, Any]] = {}
        self._completed_tests: list[ABTestResult] = []

    def create_test(
        self,
        control: AgentVariant,
        experiment: AgentVariant,
        min_tasks: int = 20,
    ) -> str:
        """Create a new A/B test. Returns test ID."""
        result = ABTestResult(
            control=VariantMetrics(variant_id=control.id),
            experiment=VariantMetrics(variant_id=experiment.id),
        )

        self._active_tests[result.id] = {
            "control_variant": control,
            "experiment_variant": experiment,
            "result": result,
            "min_tasks": min_tasks,
        }

        logger.info(f"Created A/B test {result.id}: '{control.description}' vs '{experiment.description}'")
        return result.id

    def record_control_result(self, test_id: str, success: bool, quality: float = 0.0, cost: float = 0.0, duration_ms: float = 0.0) -> None:
        """Record a result for the control variant."""
        test = self._active_tests.get(test_id)
        if not test:
            return
        m = test["result"].control
        m.tasks_run += 1
        if success:
            m.successes += 1
        m.total_quality_score += quality
        m.total_cost_usd += cost
        m.total_duration_ms += duration_ms
        self._check_completion(test_id)

    def record_experiment_result(self, test_id: str, success: bool, quality: float = 0.0, cost: float = 0.0, duration_ms: float = 0.0) -> None:
        """Record a result for the experiment variant."""
        test = self._active_tests.get(test_id)
        if not test:
            return
        m = test["result"].experiment
        m.tasks_run += 1
        if success:
            m.successes += 1
        m.total_quality_score += quality
        m.total_cost_usd += cost
        m.total_duration_ms += duration_ms
        self._check_completion(test_id)

    def _check_completion(self, test_id: str) -> None:
        """Check if a test has enough data to conclude."""
        test = self._active_tests.get(test_id)
        if not test:
            return

        result = test["result"]
        min_tasks = test["min_tasks"]

        if result.control.tasks_run >= min_tasks and result.experiment.tasks_run >= min_tasks:
            self._conclude_test(test_id)

    def _conclude_test(self, test_id: str) -> None:
        """Analyze results and determine winner."""
        test = self._active_tests.get(test_id)
        if not test:
            return

        result = test["result"]
        c = result.control
        e = result.experiment

        # Compare on primary metric: quality-adjusted success rate
        c_score = c.success_rate * 0.6 + c.avg_quality * 0.3 + (1 - min(c.avg_cost, 1.0)) * 0.1
        e_score = e.success_rate * 0.6 + e.avg_quality * 0.3 + (1 - min(e.avg_cost, 1.0)) * 0.1

        if e_score > c_score * 1.05:  # Experiment must be 5% better
            result.winner = "experiment"
            result.improvement_pct = round((e_score - c_score) / max(c_score, 0.001) * 100, 1)
        elif c_score > e_score * 1.05:
            result.winner = "control"
            result.improvement_pct = 0
        else:
            result.winner = "inconclusive"
            result.improvement_pct = 0

        result.tasks_total = c.tasks_run + e.tasks_run
        result.status = "completed"

        self._completed_tests.append(result)
        del self._active_tests[test_id]

        logger.info(f"A/B test {test_id} completed: winner={result.winner} (improvement: {result.improvement_pct}%)")

    def get_active_tests(self) -> list[dict]:
        """Get all active tests."""
        return [t["result"].to_dict() for t in self._active_tests.values()]

    def get_completed_tests(self, limit: int = 20) -> list[dict]:
        """Get completed test results."""
        return [t.to_dict() for t in self._completed_tests[-limit:]]

    def __repr__(self) -> str:
        return f"ABTestManager(active={len(self._active_tests)}, completed={len(self._completed_tests)})"
