"""Predictive failure detection — predict and prevent agent failures before they happen."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FailurePrediction:
    """Prediction of failure probability for a task."""
    probability: float = 0.0  # 0.0 to 1.0
    confidence: float = 0.0   # How confident we are in the prediction
    risk_factors: list[str] = field(default_factory=list)
    mitigation: str = ""
    recommended_action: str = "proceed"  # proceed, add_qa, use_premium_model, escalate_human


class FailurePredictor:
    """
    Predicts agent failure probability based on historical performance data.
    
    Uses simple heuristics + performance history to estimate risk before task execution.
    If risk is high, recommends mitigations (extra QA, premium model, human escalation).
    """

    def __init__(self, performance_tracker: Any = None, risk_threshold: float = 0.7):
        self._tracker = performance_tracker
        self.risk_threshold = risk_threshold
        self._task_history: dict[str, list[bool]] = {}  # agent → [success/fail history]

    def set_performance_tracker(self, tracker: Any) -> None:
        """Set the performance tracker for historical data."""
        self._tracker = tracker

    def record_outcome(self, agent_name: str, success: bool) -> None:
        """Record a task outcome for future predictions."""
        if agent_name not in self._task_history:
            self._task_history[agent_name] = []
        self._task_history[agent_name].append(success)
        # Keep last 200 outcomes per agent
        if len(self._task_history[agent_name]) > 200:
            self._task_history[agent_name] = self._task_history[agent_name][-200:]

    def predict(
        self,
        agent_name: str,
        task: str = "",
        conversation_length: int = 0,
        tools_count: int = 0,
    ) -> FailurePrediction:
        """
        Predict failure probability for an agent + task combination.
        
        Factors considered:
        1. Agent's historical success rate
        2. Task complexity indicators
        3. Conversation length (longer = more likely to fail)
        4. Tool count (more tools = more failure points)
        """
        risk_factors = []
        base_probability = 0.1  # Start with 10% base failure rate

        # Factor 1: Historical success rate
        history = self._task_history.get(agent_name, [])
        if history:
            recent = history[-20:]  # Last 20 tasks
            failure_rate = 1.0 - (sum(recent) / len(recent))
            base_probability = max(base_probability, failure_rate)
            if failure_rate > 0.3:
                risk_factors.append(f"High recent failure rate: {failure_rate:.0%} ({len(recent)} tasks)")
        else:
            risk_factors.append("No performance history (new agent)")
            base_probability = max(base_probability, 0.2)  # Unknown = higher risk

        # Factor 2: Task complexity
        task_lower = task.lower()
        complex_signals = ["analyze", "design", "compare", "multi-step", "complex", "detailed"]
        complexity_count = sum(1 for s in complex_signals if s in task_lower)
        if complexity_count >= 2:
            base_probability += 0.15
            risk_factors.append(f"High task complexity ({complexity_count} complexity signals)")
        
        if len(task) > 500:
            base_probability += 0.1
            risk_factors.append("Very long task description (>500 chars)")

        # Factor 3: Conversation depth
        if conversation_length > 30:
            base_probability += 0.15
            risk_factors.append(f"Deep conversation ({conversation_length} messages — context window pressure)")
        elif conversation_length > 15:
            base_probability += 0.05

        # Factor 4: Tool count
        if tools_count > 5:
            base_probability += 0.1
            risk_factors.append(f"Many tools ({tools_count} — more failure points)")

        # Factor 5: Performance tracker data
        if self._tracker:
            stats = self._tracker.get_agent_stats(agent_name)
            if stats.get("tasks", 0) > 10:
                avg_quality = stats.get("avg_quality_score", 0.8)
                if avg_quality < 0.5:
                    base_probability += 0.2
                    risk_factors.append(f"Low average quality score: {avg_quality:.0%}")

        # Cap probability
        probability = min(base_probability, 0.95)
        confidence = min(len(history) / 50.0, 1.0) if history else 0.3

        # Determine recommended action
        if probability >= 0.8:
            action = "escalate_human"
            mitigation = "Very high failure risk. Escalate to human before proceeding."
        elif probability >= 0.6:
            action = "use_premium_model"
            mitigation = "High failure risk. Use premium model and add extra quality gate."
        elif probability >= 0.4:
            action = "add_qa"
            mitigation = "Moderate failure risk. Add quality review before delivery."
        else:
            action = "proceed"
            mitigation = "Low failure risk. Proceed normally."

        prediction = FailurePrediction(
            probability=round(probability, 3),
            confidence=round(confidence, 3),
            risk_factors=risk_factors,
            mitigation=mitigation,
            recommended_action=action,
        )

        if probability >= self.risk_threshold:
            logger.warning(
                f"High failure risk for {agent_name}: {probability:.0%} — {action}"
            )

        return prediction

    def __repr__(self) -> str:
        return f"FailurePredictor(agents_tracked={len(self._task_history)}, threshold={self.risk_threshold})"
