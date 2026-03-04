"""Smart model routing — automatically picks the cheapest model for each task."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# Model tiers: cheaper models for simpler tasks
MODEL_TIERS = {
    "fast": {
        "models": ["gpt-4o-mini", "gpt-3.5-turbo"],
        "cost_per_1k_input": 0.00015,
        "max_complexity": "low",
    },
    "standard": {
        "models": ["gpt-4o"],
        "cost_per_1k_input": 0.005,
        "max_complexity": "medium",
    },
    "premium": {
        "models": ["gpt-4", "gpt-4-turbo"],
        "cost_per_1k_input": 0.03,
        "max_complexity": "high",
    },
}

# Complexity indicators
HIGH_COMPLEXITY_SIGNALS = [
    "analyze", "design", "architect", "strategy", "plan",
    "complex", "detailed", "comprehensive", "evaluate",
    "compare", "critique", "negotiate", "optimize",
    "multi-step", "research", "investigate",
]

LOW_COMPLEXITY_SIGNALS = [
    "classify", "route", "categorize", "format",
    "extract", "summarize briefly", "yes or no",
    "simple", "quick", "lookup", "check status",
    "list", "count", "convert",
]


class ModelRouter:
    """
    Routes LLM calls to the most cost-effective model based on task complexity.

    Simple tasks (classification, routing, extraction) → cheap model (gpt-4o-mini)
    Complex tasks (analysis, strategy, critique) → premium model (gpt-4)

    Saves 60-80% on LLM costs for typical workloads.
    """

    def __init__(
        self,
        default_model: str = "gpt-4",
        fast_model: str = "gpt-4o-mini",
        standard_model: str = "gpt-4o",
        premium_model: str = "gpt-4",
        enabled: bool = True,
    ):
        self.default_model = default_model
        self.fast_model = fast_model
        self.standard_model = standard_model
        self.premium_model = premium_model
        self.enabled = enabled
        self._routing_stats: dict[str, int] = {"fast": 0, "standard": 0, "premium": 0}

    def select_model(
        self,
        task: str = "",
        messages: list[dict] | None = None,
        has_tools: bool = False,
        agent_role: str = "",
    ) -> str:
        """
        Select the best model for a task based on complexity signals.

        Returns the model name to use.
        """
        if not self.enabled:
            return self.default_model

        complexity = self._assess_complexity(task, messages, has_tools, agent_role)

        if complexity == "low":
            self._routing_stats["fast"] += 1
            model = self.fast_model
        elif complexity == "medium":
            self._routing_stats["standard"] += 1
            model = self.standard_model
        else:
            self._routing_stats["premium"] += 1
            model = self.premium_model

        logger.debug(f"Model routing: complexity={complexity} → {model} (task: {task[:50]}...)")
        return model

    def _assess_complexity(
        self,
        task: str,
        messages: list[dict] | None,
        has_tools: bool,
        agent_role: str,
    ) -> str:
        """Assess task complexity: low, medium, or high."""
        task_lower = task.lower() if task else ""

        # Role-based routing: managers/coordinators get premium, support gets fast
        if agent_role in ("manager", "coordinator", "analyst"):
            return "high"
        if agent_role in ("support",):
            # Support agents can use fast model unless task is complex
            if not any(s in task_lower for s in HIGH_COMPLEXITY_SIGNALS):
                return "low"

        # Message count: more messages = more context needed = higher model
        msg_count = len(messages) if messages else 0
        if msg_count > 15:
            return "high"

        # Task length: very short tasks are usually simple
        if len(task) < 100 and not has_tools:
            # Check for low-complexity signals
            if any(s in task_lower for s in LOW_COMPLEXITY_SIGNALS):
                return "low"

        # Check for high-complexity signals
        high_count = sum(1 for s in HIGH_COMPLEXITY_SIGNALS if s in task_lower)
        if high_count >= 2:
            return "high"

        # Check for low-complexity signals
        low_count = sum(1 for s in LOW_COMPLEXITY_SIGNALS if s in task_lower)
        if low_count >= 2:
            return "low"

        # Tool calling typically needs a smarter model
        if has_tools:
            return "medium"

        return "medium"  # Default to standard

    def get_stats(self) -> dict[str, Any]:
        """Get routing statistics."""
        total = sum(self._routing_stats.values())
        if total == 0:
            return {"total_calls": 0, "routing": self._routing_stats}

        fast_pct = self._routing_stats["fast"] / total
        estimated_savings = fast_pct * 0.80  # Fast model is ~80% cheaper

        return {
            "total_calls": total,
            "routing": dict(self._routing_stats),
            "fast_percentage": round(fast_pct * 100, 1),
            "estimated_cost_savings": f"{estimated_savings:.0%}",
        }

    def __repr__(self) -> str:
        return f"ModelRouter(fast={self.fast_model}, premium={self.premium_model}, stats={self._routing_stats})"
