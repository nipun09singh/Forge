"""Escalation primitives — what to do when agents fail."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EscalationLevel(str, Enum):
    RETRY = "retry"                    # Same agent tries again
    DIFFERENT_AGENT = "different_agent" # Route to another agent
    DIFFERENT_MODEL = "different_model" # Try a smarter/different model
    HUMAN = "human"                    # Flag for human review


@dataclass
class EscalationStep:
    """One step in an escalation chain."""
    level: EscalationLevel
    max_attempts: int = 2
    model_override: str = ""  # For DIFFERENT_MODEL level
    agent_override: str = ""  # For DIFFERENT_AGENT level
    notify_channel: str = ""  # For HUMAN level (slack, email, log)


class EscalationPolicy:
    """
    Configurable escalation chain for when agents fail.
    
    Default chain: retry(3) → different_model(2) → human
    """

    def __init__(
        self,
        steps: list[EscalationStep] | None = None,
        max_total_attempts: int = 10,
    ):
        self.steps = steps or [
            EscalationStep(level=EscalationLevel.RETRY, max_attempts=3),
            EscalationStep(level=EscalationLevel.DIFFERENT_MODEL, max_attempts=2, model_override="gpt-4"),
            EscalationStep(level=EscalationLevel.HUMAN, max_attempts=1),
        ]
        self.max_total_attempts = max_total_attempts
        self._attempt_count = 0
        self._current_step_idx = 0
        self._step_attempts: dict[int, int] = {}

    def should_escalate(self, success: bool) -> bool:
        """Check if we should try the next escalation level."""
        if success:
            return False
        self._attempt_count += 1
        if self._attempt_count >= self.max_total_attempts:
            return False
        return self._current_step_idx < len(self.steps)

    def get_next_action(self) -> EscalationStep | None:
        """Get the current escalation action."""
        if self._current_step_idx >= len(self.steps):
            return None

        step = self.steps[self._current_step_idx]
        step_attempts = self._step_attempts.get(self._current_step_idx, 0)

        if step_attempts >= step.max_attempts:
            # Move to next escalation level
            self._current_step_idx += 1
            if self._current_step_idx >= len(self.steps):
                return None
            step = self.steps[self._current_step_idx]
            self._step_attempts[self._current_step_idx] = 0

        self._step_attempts[self._current_step_idx] = self._step_attempts.get(self._current_step_idx, 0) + 1
        logger.info(f"Escalation: {step.level.value} (attempt {self._step_attempts[self._current_step_idx]}/{step.max_attempts})")
        return step

    def reset(self) -> None:
        """Reset escalation state for a new task."""
        self._attempt_count = 0
        self._current_step_idx = 0
        self._step_attempts.clear()

    def __repr__(self) -> str:
        levels = " → ".join(s.level.value for s in self.steps)
        return f"EscalationPolicy({levels})"
