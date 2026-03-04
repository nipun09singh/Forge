"""Critic primitives — different strategies for evaluating agent output."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CriticVerdict:
    """Result from a critic evaluation."""
    passed: bool
    score: float = 1.0  # 0.0 to 1.0
    feedback: str = ""
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


class CriticBase(ABC):
    """Base class for all critics."""

    @abstractmethod
    async def evaluate(self, task: str, output: str, context: dict[str, Any] | None = None, llm_client: Any = None) -> CriticVerdict:
        """Evaluate an output against quality criteria."""
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


class BinaryCritic(CriticBase):
    """Pass/fail evaluation. Best for: did it compile? did tests pass? did it return valid JSON?"""

    def __init__(self, check_fn=None):
        self._check_fn = check_fn

    async def evaluate(self, task, output, context=None, llm_client=None):
        if self._check_fn:
            try:
                passed = self._check_fn(output)
                return CriticVerdict(passed=passed, score=1.0 if passed else 0.0,
                                     feedback="Check passed" if passed else "Check failed")
            except Exception as e:
                return CriticVerdict(passed=False, score=0.0, feedback=f"Check error: {e}")

        # Default: passes if output is non-empty and not an error
        passed = bool(output) and "error" not in output.lower()[:50]
        return CriticVerdict(passed=passed, score=1.0 if passed else 0.0)


class ScoredCritic(CriticBase):
    """Scores output 0-1 using LLM evaluation. Best for quality assessment."""

    def __init__(self, min_score: float = 0.7, criteria: str = ""):
        self.min_score = min_score
        self.criteria = criteria or "accuracy, completeness, clarity, and usefulness"

    async def evaluate(self, task, output, context=None, llm_client=None):
        if not llm_client:
            # Without LLM, use heuristics
            score = min(len(output) / 500, 1.0) * 0.7 + (0.3 if "\n" in output else 0.0)
            return CriticVerdict(passed=score >= self.min_score, score=round(score, 2))

        messages = [
            {"role": "system", "content": (
                f"Score this output 0.0-1.0 on: {self.criteria}. "
                "Return JSON: {\"score\": 0.85, \"feedback\": \"...\", \"issues\": [\"...\"]}"
            )},
            {"role": "user", "content": f"Task: {task}\n\nOutput:\n{output[:2000]}"},
        ]

        try:
            response = await llm_client.chat.completions.create(
                model="gpt-4o-mini", messages=messages, temperature=0.2,
                response_format={"type": "json_object"},
            )
            data = json.loads(response.choices[0].message.content or "{}")
            score = float(data.get("score", 0.5))
            return CriticVerdict(
                passed=score >= self.min_score, score=score,
                feedback=data.get("feedback", ""),
                issues=data.get("issues", []),
            )
        except Exception as e:
            return CriticVerdict(passed=True, score=0.7, feedback=f"Evaluation error: {e}")

    def __repr__(self) -> str:
        return f"ScoredCritic(min_score={self.min_score})"


class FactualCritic(CriticBase):
    """Checks output against a knowledge source. Best for support/docs agents."""

    def __init__(self, knowledge_source: str = "", min_confidence: float = 0.8):
        self.knowledge_source = knowledge_source
        self.min_confidence = min_confidence

    async def evaluate(self, task, output, context=None, llm_client=None):
        if not llm_client or not self.knowledge_source:
            return CriticVerdict(passed=True, score=0.8, feedback="No knowledge source to check against")

        messages = [
            {"role": "system", "content": (
                "You are a fact-checker. Compare the output against the knowledge source. "
                "Identify any claims not supported by the knowledge. "
                "Return JSON: {\"score\": 0.9, \"unsupported_claims\": [\"...\"], \"feedback\": \"...\"}"
            )},
            {"role": "user", "content": (
                f"Knowledge source:\n{self.knowledge_source[:3000]}\n\n"
                f"Output to check:\n{output[:2000]}"
            )},
        ]

        try:
            response = await llm_client.chat.completions.create(
                model="gpt-4o-mini", messages=messages, temperature=0.1,
                response_format={"type": "json_object"},
            )
            data = json.loads(response.choices[0].message.content or "{}")
            score = float(data.get("score", 0.5))
            return CriticVerdict(
                passed=score >= self.min_confidence, score=score,
                feedback=data.get("feedback", ""),
                issues=data.get("unsupported_claims", []),
            )
        except Exception as e:
            return CriticVerdict(passed=True, score=0.7, feedback=f"Fact-check error: {e}")


class ComplianceCritic(CriticBase):
    """Checks output against rules/policies. Best for billing, legal, regulated domains."""

    def __init__(self, rules: list[str] | None = None):
        self.rules = rules or []

    async def evaluate(self, task, output, context=None, llm_client=None):
        if not self.rules:
            return CriticVerdict(passed=True, score=1.0, feedback="No rules to check")

        violations = []
        output_lower = output.lower()

        for rule in self.rules:
            # Simple keyword-based rule checking
            if rule.startswith("NEVER:"):
                banned = rule[6:].strip().lower()
                if banned in output_lower:
                    violations.append(f"Violated rule: {rule}")
            elif rule.startswith("MUST:"):
                required = rule[5:].strip().lower()
                if required not in output_lower:
                    violations.append(f"Missing requirement: {rule}")

        score = 1.0 - (len(violations) / max(len(self.rules), 1))
        return CriticVerdict(
            passed=len(violations) == 0,
            score=max(0.0, score),
            feedback=f"{len(violations)} rule violations found" if violations else "All rules satisfied",
            issues=violations,
        )

    def __repr__(self) -> str:
        return f"ComplianceCritic(rules={len(self.rules)})"
