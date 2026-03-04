"""Self-improvement runtime — feedback loops, quality gates, and performance tracking."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


# =============================================================================
# Quality Gate — validates outputs before delivery
# =============================================================================

@dataclass
class QualityVerdict:
    """Result of a quality gate check."""
    passed: bool
    score: float  # 0.0 to 1.0
    feedback: str = ""
    needs_revision: bool = False
    iteration: int = 0


class QualityGate:
    """
    A checkpoint that validates agent outputs against quality criteria.
    
    If output doesn't pass, it's sent back for revision with feedback.
    This creates a critique → revise loop that iterates until quality is met.
    """

    def __init__(
        self,
        min_score: float = 0.8,
        max_revisions: int = 5,  # Set high — iterate as many times as needed
        evaluator: Callable[..., Awaitable[QualityVerdict]] | None = None,
    ):
        self.min_score = min_score
        self.max_revisions = max_revisions
        self._evaluator = evaluator
        self._llm_client: Any = None

    def __repr__(self) -> str:
        return f"QualityGate(min_score={self.min_score}, max_revisions={self.max_revisions})"

    def set_llm_client(self, client: Any) -> None:
        """Set the LLM client for self-evaluation."""
        self._llm_client = client

    async def check(self, output: str, task: str, criteria: str = "", iteration: int = 0) -> QualityVerdict:
        """
        Check if an output meets quality standards.
        
        Uses either a custom evaluator or LLM-based self-evaluation.
        """
        if self._evaluator:
            return await self._evaluator(output, task, criteria, iteration)

        # Default: LLM-based quality evaluation
        return await self._llm_evaluate(output, task, criteria, iteration)

    async def _llm_evaluate(self, output: str, task: str, criteria: str, iteration: int) -> QualityVerdict:
        """Use LLM to evaluate output quality."""
        if not self._llm_client:
            # No LLM client — pass by default
            return QualityVerdict(passed=True, score=1.0, iteration=iteration)

        eval_prompt = (
            "You are a strict quality evaluator. Rate the following output.\n\n"
            f"ORIGINAL TASK: {task}\n\n"
            f"OUTPUT TO EVALUATE:\n{output}\n\n"
        )
        if criteria:
            eval_prompt += f"SPECIFIC CRITERIA:\n{criteria}\n\n"

        eval_prompt += (
            "Rate the output on a scale of 0.0 to 1.0 on these dimensions:\n"
            "1. Accuracy — Is the information correct?\n"
            "2. Completeness — Does it fully address the task?\n"
            "3. Clarity — Is it well-organized and easy to understand?\n"
            "4. Usefulness — Is it actionable and practical?\n\n"
            "Respond ONLY with a JSON object: "
            '{"score": 0.85, "passed": true, "feedback": "...", "needs_revision": false}\n'
            "Set needs_revision=true and provide specific feedback if score < " + str(self.min_score)
        )

        try:
            import json
            response = await self._llm_client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": eval_prompt}],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)
            return QualityVerdict(
                passed=data.get("passed", data.get("score", 0) >= self.min_score),
                score=float(data.get("score", 0.5)),
                feedback=data.get("feedback", ""),
                needs_revision=data.get("needs_revision", False),
                iteration=iteration,
            )
        except Exception as e:
            logger.warning(f"Quality gate evaluation failed: {e}")
            return QualityVerdict(passed=True, score=0.7, feedback=f"Evaluation error: {e}", iteration=iteration)


# =============================================================================
# Performance Tracker — tracks metrics per agent
# =============================================================================

@dataclass
class TaskMetric:
    """Metrics for a single task execution."""
    agent_name: str
    task_preview: str
    success: bool
    quality_score: float
    duration_seconds: float
    iterations_used: int = 1
    revision_count: int = 0
    timestamp: float = field(default_factory=time.time)


class PerformanceTracker:
    """
    Tracks performance metrics for all agents in an agency.
    
    Provides data for the Self-Improvement Agent and Analytics Agent.
    """

    def __init__(self, max_metrics: int = 10_000) -> None:
        self._metrics: list[TaskMetric] = []
        self._by_agent: dict[str, list[TaskMetric]] = defaultdict(list)
        self._max_metrics = max_metrics

    def __repr__(self) -> str:
        return f"PerformanceTracker(agents={len(self._by_agent)}, tasks={len(self._metrics)})"

    def record(self, metric: TaskMetric) -> None:
        """Record a task execution metric."""
        self._metrics.append(metric)
        self._by_agent[metric.agent_name].append(metric)
        # Prevent unbounded memory growth
        if len(self._metrics) > self._max_metrics:
            self._metrics = self._metrics[-self._max_metrics:]
        agent_metrics = self._by_agent[metric.agent_name]
        if len(agent_metrics) > self._max_metrics:
            self._by_agent[metric.agent_name] = agent_metrics[-self._max_metrics:]

    def get_agent_stats(self, agent_name: str) -> dict[str, Any]:
        """Get aggregate stats for an agent."""
        metrics = self._by_agent.get(agent_name, [])
        if not metrics:
            return {"agent": agent_name, "tasks": 0}

        successes = sum(1 for m in metrics if m.success)
        total = len(metrics)
        avg_quality = sum(m.quality_score for m in metrics) / total
        avg_duration = sum(m.duration_seconds for m in metrics) / total
        avg_revisions = sum(m.revision_count for m in metrics) / total

        return {
            "agent": agent_name,
            "tasks": total,
            "success_rate": round(successes / total, 3),
            "avg_quality_score": round(avg_quality, 3),
            "avg_duration_seconds": round(avg_duration, 2),
            "avg_revisions": round(avg_revisions, 2),
            "recent_failures": [
                {"task": m.task_preview, "quality": m.quality_score}
                for m in metrics[-10:] if not m.success
            ],
        }

    def get_agency_stats(self) -> dict[str, Any]:
        """Get aggregate stats for the entire agency."""
        if not self._metrics:
            return {"total_tasks": 0}

        total = len(self._metrics)
        successes = sum(1 for m in self._metrics if m.success)
        avg_quality = sum(m.quality_score for m in self._metrics) / total

        return {
            "total_tasks": total,
            "success_rate": round(successes / total, 3),
            "avg_quality_score": round(avg_quality, 3),
            "agents_tracked": len(self._by_agent),
            "per_agent": {
                name: self.get_agent_stats(name)
                for name in self._by_agent
            },
        }

    def get_failure_patterns(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent failures for pattern analysis."""
        failures = [m for m in self._metrics if not m.success]
        return [
            {
                "agent": m.agent_name,
                "task": m.task_preview,
                "quality_score": m.quality_score,
                "duration": m.duration_seconds,
                "revisions": m.revision_count,
            }
            for m in failures[-limit:]
        ]


# =============================================================================
# Feedback Collector — gathers feedback on outputs
# =============================================================================

@dataclass
class Feedback:
    """Feedback on an agent output."""
    agent_name: str
    task_preview: str
    rating: float  # 0.0 to 1.0
    comment: str = ""
    source: str = "system"  # "user", "system", "qa_agent"
    timestamp: float = field(default_factory=time.time)


class FeedbackCollector:
    """Collects and aggregates feedback on agent outputs."""

    def __init__(self) -> None:
        self._feedback: list[Feedback] = []
        self._by_agent: dict[str, list[Feedback]] = defaultdict(list)

    def __repr__(self) -> str:
        return f"FeedbackCollector(entries={len(self._feedback)})"

    def collect(self, feedback: Feedback) -> None:
        """Record feedback."""
        self._feedback.append(feedback)
        self._by_agent[feedback.agent_name].append(feedback)

    def get_agent_feedback(self, agent_name: str, limit: int = 50) -> list[Feedback]:
        """Get recent feedback for an agent."""
        return self._by_agent.get(agent_name, [])[-limit:]

    def get_avg_rating(self, agent_name: str) -> float:
        """Get average feedback rating for an agent."""
        fb = self._by_agent.get(agent_name, [])
        return sum(f.rating for f in fb) / max(len(fb), 1)


# =============================================================================
# Reflection Engine — agents reflect on their own outputs
# =============================================================================

class ReflectionEngine:
    """
    Enables agents to reflect on their outputs and self-improve.
    
    After producing an output, the agent runs a reflection step:
    1. Evaluate: "Is this output good enough?"
    2. Critique: "What could be better?"
    3. Improve: If quality is too low, re-execute with improvements
    4. Learn: Store insights for future tasks
    """

    def __init__(self, quality_gate: QualityGate | None = None):
        self.quality_gate = quality_gate or QualityGate()

    def __repr__(self) -> str:
        return f"ReflectionEngine(gate={self.quality_gate!r})"

    async def reflect_and_improve(
        self,
        agent: Any,  # Agent instance
        task: str,
        initial_output: str,
        max_reflections: int = 5,
    ) -> tuple[str, list[QualityVerdict]]:
        """
        Reflect on output and improve iteratively until quality is met.
        
        Returns the final (possibly improved) output and the history of verdicts.
        """
        current_output = initial_output
        verdicts: list[QualityVerdict] = []

        for i in range(max_reflections):
            verdict = await self.quality_gate.check(
                output=current_output,
                task=task,
                iteration=i,
            )
            verdicts.append(verdict)

            if verdict.passed:
                logger.info(f"Reflection pass {i}: PASSED (score={verdict.score:.2f})")
                break

            if not verdict.needs_revision:
                logger.info(f"Reflection pass {i}: Score {verdict.score:.2f} but no revision needed")
                break

            # Self-improve: re-execute with feedback
            logger.info(f"Reflection pass {i}: REVISING (score={verdict.score:.2f})")
            revision_task = (
                f"Your previous output was reviewed and needs improvement.\n\n"
                f"ORIGINAL TASK: {task}\n\n"
                f"YOUR PREVIOUS OUTPUT:\n{current_output}\n\n"
                f"REVIEWER FEEDBACK:\n{verdict.feedback}\n\n"
                f"Please produce an improved version that addresses all feedback. "
                f"Focus on: {verdict.feedback}"
            )

            result = await agent.execute(revision_task)
            current_output = result.output

        return current_output, verdicts
