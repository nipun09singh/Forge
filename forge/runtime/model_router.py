"""Smart model routing — automatically picks the cheapest model for each task."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
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

# Adaptive routing thresholds
ADAPTIVE_MIN_SAMPLES = 20
ADAPTIVE_DOWNGRADE_SUCCESS_RATE = 0.90  # 90%+ success → try cheaper model
ADAPTIVE_UPGRADE_FAILURE_RATE = 0.30  # 30%+ failure → upgrade model
PERSISTENCE_SAVE_INTERVAL = 5  # Save after every N outcomes


@dataclass
class RoutingOutcome:
    """Records the result of a routed model call."""

    task_hash: str
    complexity_assessed: str
    model_selected: str
    success: bool
    quality_score: float = 0.0
    tokens: int = 0
    cost: float = 0.0
    timestamp: float = field(default_factory=time.time)


def _task_hash(task: str) -> str:
    """Produce a short hash for a task string."""
    return hashlib.sha256(task.encode()).hexdigest()[:12]


class ModelRouter:
    """
    Routes LLM calls to the most cost-effective model based on task complexity.

    Simple tasks (classification, routing, extraction) → cheap model (gpt-4o-mini)
    Complex tasks (analysis, strategy, critique) → premium model (gpt-4)

    Includes a feedback loop that learns from outcomes to adjust routing over time.
    Saves 60-80% on LLM costs for typical workloads.
    """

    def __init__(
        self,
        default_model: str = "gpt-4",
        fast_model: str = "gpt-4o-mini",
        standard_model: str = "gpt-4o",
        premium_model: str = "gpt-4",
        enabled: bool = True,
        feedback_path: str | Path | None = None,
    ):
        self.default_model = default_model
        self.fast_model = fast_model
        self.standard_model = standard_model
        self.premium_model = premium_model
        self.enabled = enabled
        self._routing_stats: dict[str, int] = {"fast": 0, "standard": 0, "premium": 0}

        self._feedback_history: list[RoutingOutcome] = []
        self._routing_adjustments: dict[str, str] = {}
        self._outcomes_since_save = 0

        if feedback_path is not None:
            self._feedback_path: Path | None = Path(feedback_path)
        else:
            self._feedback_path = Path.home() / ".forge" / "router_feedback.json"

        self._load_feedback()

    # ------------------------------------------------------------------
    # Model selection
    # ------------------------------------------------------------------

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

        # Apply adaptive routing adjustments
        effective_complexity = self._routing_adjustments.get(complexity, complexity)
        if effective_complexity != complexity:
            logger.debug(
                f"Adaptive routing override: {complexity} → {effective_complexity}"
            )

        if effective_complexity == "low":
            self._routing_stats["fast"] += 1
            model = self.fast_model
        elif effective_complexity == "medium":
            self._routing_stats["standard"] += 1
            model = self.standard_model
        else:
            self._routing_stats["premium"] += 1
            model = self.premium_model

        logger.debug(f"Model routing: complexity={complexity} → {model} (task: {task[:50]}...)")
        return model

    # ------------------------------------------------------------------
    # Complexity assessment
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Feedback recording
    # ------------------------------------------------------------------

    def record_outcome(
        self,
        task_id: str,
        model_used: str,
        success: bool,
        quality_score: float = 0.0,
        tokens_used: int = 0,
        cost: float = 0.0,
        complexity_assessed: str = "medium",
    ) -> None:
        """Record the outcome of a routed call for adaptive learning."""
        outcome = RoutingOutcome(
            task_hash=_task_hash(task_id),
            complexity_assessed=complexity_assessed,
            model_selected=model_used,
            success=success,
            quality_score=quality_score,
            tokens=tokens_used,
            cost=cost,
        )
        self._feedback_history.append(outcome)
        self._outcomes_since_save += 1

        logger.debug(
            f"Recorded outcome: model={model_used} success={success} "
            f"quality={quality_score} tokens={tokens_used}"
        )

        self._maybe_adjust_routing()

        if self._outcomes_since_save >= PERSISTENCE_SAVE_INTERVAL:
            self._save_feedback()

    # ------------------------------------------------------------------
    # Adaptive routing
    # ------------------------------------------------------------------

    def _maybe_adjust_routing(self) -> None:
        """Re-evaluate routing adjustments when enough feedback exists."""
        if len(self._feedback_history) < ADAPTIVE_MIN_SAMPLES:
            return

        tier_map = {
            self.fast_model: "fast",
            self.standard_model: "standard",
            self.premium_model: "premium",
        }

        # Group outcomes by (complexity_assessed, model_tier)
        groups: dict[tuple[str, str], list[RoutingOutcome]] = {}
        for o in self._feedback_history:
            tier = tier_map.get(o.model_selected, "unknown")
            key = (o.complexity_assessed, tier)
            groups.setdefault(key, []).append(o)

        new_adjustments: dict[str, str] = {}

        # If fast model succeeds 90%+ on "medium" tasks → downgrade medium→low
        medium_fast = groups.get(("medium", "fast"), [])
        if not medium_fast:
            # Also check outcomes where medium tasks went to standard and succeeded
            medium_std = groups.get(("medium", "standard"), [])
            if len(medium_std) >= ADAPTIVE_MIN_SAMPLES:
                success_rate = sum(1 for o in medium_std if o.success) / len(medium_std)
                avg_quality = (
                    sum(o.quality_score for o in medium_std) / len(medium_std)
                    if medium_std
                    else 0
                )
                # Standard model succeeding almost all the time with high quality
                # on medium tasks: no need to change (it's already the right tier)
        else:
            if len(medium_fast) >= ADAPTIVE_MIN_SAMPLES:
                success_rate = sum(1 for o in medium_fast if o.success) / len(medium_fast)
                if success_rate >= ADAPTIVE_DOWNGRADE_SUCCESS_RATE:
                    new_adjustments["medium"] = "low"
                    logger.info(
                        f"Adaptive routing: medium→low (fast model success rate "
                        f"{success_rate:.0%} on medium tasks)"
                    )

        # If fast model fails often on "low" tasks → upgrade low→medium
        low_fast = groups.get(("low", "fast"), [])
        if low_fast and len(low_fast) >= ADAPTIVE_MIN_SAMPLES:
            failure_rate = sum(1 for o in low_fast if not o.success) / len(low_fast)
            if failure_rate >= ADAPTIVE_UPGRADE_FAILURE_RATE:
                new_adjustments["low"] = "medium"
                logger.info(
                    f"Adaptive routing: low→medium (fast model failure rate "
                    f"{failure_rate:.0%} on low tasks)"
                )

        # If standard model fails often on "medium" tasks → upgrade medium→high
        medium_std = groups.get(("medium", "standard"), [])
        if medium_std and len(medium_std) >= ADAPTIVE_MIN_SAMPLES:
            failure_rate = sum(1 for o in medium_std if not o.success) / len(medium_std)
            if failure_rate >= ADAPTIVE_UPGRADE_FAILURE_RATE:
                new_adjustments["medium"] = "high"
                logger.info(
                    f"Adaptive routing: medium→high (standard model failure rate "
                    f"{failure_rate:.0%} on medium tasks)"
                )

        self._routing_adjustments.update(new_adjustments)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _feedback_file(self) -> Path:
        return self._feedback_path  # type: ignore[return-value]

    def _save_feedback(self) -> None:
        """Persist feedback history and routing adjustments to disk."""
        path = self._feedback_file()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "feedback_history": [asdict(o) for o in self._feedback_history],
                "routing_adjustments": self._routing_adjustments,
            }
            path.write_text(json.dumps(data, indent=2))
            self._outcomes_since_save = 0
            logger.debug(f"Saved {len(self._feedback_history)} outcomes to {path}")
        except OSError as exc:
            logger.warning(f"Failed to save router feedback: {exc}")

    def _load_feedback(self) -> None:
        """Load persisted feedback on startup."""
        path = self._feedback_file()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            self._feedback_history = [
                RoutingOutcome(**item) for item in data.get("feedback_history", [])
            ]
            self._routing_adjustments = data.get("routing_adjustments", {})
            logger.debug(
                f"Loaded {len(self._feedback_history)} outcomes, "
                f"{len(self._routing_adjustments)} adjustments from {path}"
            )
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            logger.warning(f"Failed to load router feedback: {exc}")

    def save(self) -> None:
        """Explicitly save feedback (for callers that want deterministic saves)."""
        self._save_feedback()

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Get routing statistics including feedback-driven insights."""
        total = sum(self._routing_stats.values())
        if total == 0:
            return {"total_calls": 0, "routing": self._routing_stats}

        fast_pct = self._routing_stats["fast"] / total
        estimated_savings = fast_pct * 0.80  # Fast model is ~80% cheaper

        stats: dict[str, Any] = {
            "total_calls": total,
            "routing": dict(self._routing_stats),
            "fast_percentage": round(fast_pct * 100, 1),
            "estimated_cost_savings": f"{estimated_savings:.0%}",
        }

        # Feedback-driven stats
        if self._feedback_history:
            stats["feedback"] = self._compute_feedback_stats()

        if self._routing_adjustments:
            stats["routing_adjustments"] = dict(self._routing_adjustments)

        return stats

    def _compute_feedback_stats(self) -> dict[str, Any]:
        """Compute per-model success rates, actual costs, and recommendations."""
        tier_map = {
            self.fast_model: "fast",
            self.standard_model: "standard",
            self.premium_model: "premium",
        }

        per_model: dict[str, dict[str, Any]] = {}
        total_cost = 0.0

        for o in self._feedback_history:
            tier = tier_map.get(o.model_selected, "other")
            bucket = per_model.setdefault(tier, {
                "total": 0, "successes": 0, "total_tokens": 0, "total_cost": 0.0,
                "quality_sum": 0.0,
            })
            bucket["total"] += 1
            bucket["successes"] += int(o.success)
            bucket["total_tokens"] += o.tokens
            bucket["total_cost"] += o.cost
            bucket["quality_sum"] += o.quality_score
            total_cost += o.cost

        success_rates: dict[str, float] = {}
        model_stats: dict[str, dict[str, Any]] = {}
        for tier, bucket in per_model.items():
            count = bucket["total"]
            rate = bucket["successes"] / count if count else 0.0
            success_rates[tier] = round(rate, 3)
            model_stats[tier] = {
                "calls": count,
                "success_rate": round(rate * 100, 1),
                "avg_quality": round(bucket["quality_sum"] / count, 2) if count else 0.0,
                "total_tokens": bucket["total_tokens"],
                "total_cost": round(bucket["total_cost"], 4),
            }

        # Recommendations
        recommendations: list[str] = []
        fast_stats = per_model.get("fast", {})
        if fast_stats and fast_stats.get("total", 0) >= 10:
            rate = fast_stats["successes"] / fast_stats["total"]
            if rate >= 0.90:
                recommendations.append(
                    f"Fast model sufficient for {rate:.0%} of routed tasks — "
                    "consider routing more traffic to it."
                )
            elif rate < 0.70:
                recommendations.append(
                    f"Fast model success rate only {rate:.0%} — "
                    "consider tightening complexity thresholds."
                )

        std_stats = per_model.get("standard", {})
        if std_stats and std_stats.get("total", 0) >= 10:
            rate = std_stats["successes"] / std_stats["total"]
            if rate >= 0.95:
                recommendations.append(
                    f"Standard model succeeding at {rate:.0%} — "
                    "some tasks may be downgradeable to fast."
                )

        return {
            "total_outcomes": len(self._feedback_history),
            "per_model": model_stats,
            "total_actual_cost": round(total_cost, 4),
            "recommendations": recommendations,
        }

    def __repr__(self) -> str:
        adjustments = f", adjustments={self._routing_adjustments}" if self._routing_adjustments else ""
        return (
            f"ModelRouter(fast={self.fast_model}, premium={self.premium_model}, "
            f"stats={self._routing_stats}, feedback={len(self._feedback_history)}{adjustments})"
        )
