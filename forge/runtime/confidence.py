"""Confidence-Gated Autonomy -- scores confidence for agent actions and outputs.

Principle 6: Before executing any action, the agent scores its own confidence.
- HIGH (>0.9): auto-proceed silently
- MEDIUM (0.5-0.9): proceed but flag for review
- LOW (<0.5): pause and ask for human approval
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class ConfidenceLevel(str, Enum):
    HIGH = "high"       # >0.9 -- auto-proceed
    MEDIUM = "medium"   # 0.5-0.9 -- proceed but flag
    LOW = "low"         # <0.5 -- pause and ask human


@dataclass
class ConfidenceScore:
    score: float        # 0.0 to 1.0
    level: ConfidenceLevel
    reasoning: str      # why this confidence level
    action: str         # "auto", "flag", "pause"


# Tool categories for confidence scoring
READ_ONLY_TOOLS = frozenset({
    "web_search", "browse_web", "read_file", "read_write_file",
    "http_request", "search", "list_files", "get_status",
    "echo", "lookup", "query",
})

WRITE_TOOLS = frozenset({
    "write_file", "run_command", "create_file", "edit_file",
    "update_file", "execute", "patch",
})

DESTRUCTIVE_TOOLS = frozenset({
    "delete", "delete_file", "rm", "git_push", "send_email",
    "deploy", "publish", "drop_table", "send_notification",
    "send_webhook",
})

# Patterns that indicate hedging / low confidence in output
HEDGING_PATTERNS = re.compile(
    r"\b(i'?m not sure|maybe|i think|possibly|might be|not certain|uncertain"
    r"|i don'?t know|unclear|unsure|could be wrong)\b",
    re.IGNORECASE,
)


class ConfidenceScorer:
    """Scores confidence for agent actions and outputs."""

    HIGH_THRESHOLD = 0.9
    LOW_THRESHOLD = 0.5

    def score_tool_call(
        self, tool_name: str, args: dict, phase: str = "",
    ) -> ConfidenceScore:
        """Score confidence for a tool call based on heuristics."""
        name_lower = tool_name.lower()

        # Check destructive first (highest risk)
        if name_lower in DESTRUCTIVE_TOOLS:
            return ConfidenceScore(
                score=0.3,
                level=ConfidenceLevel.LOW,
                reasoning=f"Tool '{tool_name}' is destructive/irreversible",
                action="pause",
            )

        # Check read-only (lowest risk)
        if name_lower in READ_ONLY_TOOLS:
            return ConfidenceScore(
                score=0.95,
                level=ConfidenceLevel.HIGH,
                reasoning=f"Tool '{tool_name}' is read-only/safe",
                action="auto",
            )

        # Check write tools (medium risk)
        if name_lower in WRITE_TOOLS:
            return ConfidenceScore(
                score=0.7,
                level=ConfidenceLevel.MEDIUM,
                reasoning=f"Tool '{tool_name}' modifies state",
                action="flag",
            )

        # Unknown tool -- medium confidence
        return ConfidenceScore(
            score=0.6,
            level=ConfidenceLevel.MEDIUM,
            reasoning=f"Tool '{tool_name}' is not categorized",
            action="flag",
        )

    def score_output(
        self, output: str, task: str, quality_score: float = 0.0,
    ) -> ConfidenceScore:
        """Score confidence for an agent's final output."""
        # Start with quality_score if provided, otherwise neutral
        score = quality_score if quality_score > 0 else 0.7

        reasons: list[str] = []

        # Empty output
        if not output.strip():
            return ConfidenceScore(
                score=0.0,
                level=ConfidenceLevel.LOW,
                reasoning="output is empty",
                action="pause",
            )

        stripped = output.strip()

        # Check if output is responsive to the task rather than penalizing by length
        if task:
            task_words = set(w.lower() for w in re.findall(r"\b\w{4,}\b", task))
            out_words = set(w.lower() for w in re.findall(r"\b\w{4,}\b", stripped))
            overlap = len(task_words & out_words)
            if overlap == 0 and len(task_words) > 0:
                score = min(score, 0.4)
                reasons.append("output does not reference the task")
            elif len(stripped) < 20 and overlap == 0:
                score = min(score, 0.3)
                reasons.append("very short output with no task relevance")
        elif len(stripped) < 20:
            # No task context available — short output is suspicious but not fatal
            score = min(score, 0.5)
            reasons.append("output is very short (no task context to validate)")

        # Hedging language detection
        hedging_matches = HEDGING_PATTERNS.findall(output)
        if hedging_matches:
            penalty = min(0.3, len(hedging_matches) * 0.1)
            score = max(0.0, score - penalty)
            reasons.append(f"hedging language detected: {', '.join(hedging_matches[:3])}")

        # High quality score boosts confidence
        if quality_score >= 0.9:
            score = max(score, 0.95)
            reasons.append("high quality score")
        elif quality_score >= 0.7:
            reasons.append("acceptable quality score")

        score = max(0.0, min(1.0, score))
        level = self.classify(score)
        action = {"high": "auto", "medium": "flag", "low": "pause"}[level.value]

        return ConfidenceScore(
            score=score,
            level=level,
            reasoning="; ".join(reasons) if reasons else "default assessment",
            action=action,
        )

    def classify(self, score: float) -> ConfidenceLevel:
        """Classify a score into HIGH/MEDIUM/LOW."""
        if score >= self.HIGH_THRESHOLD:
            return ConfidenceLevel.HIGH
        if score >= self.LOW_THRESHOLD:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW
