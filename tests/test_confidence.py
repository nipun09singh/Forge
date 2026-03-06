"""Tests for forge.runtime.confidence -- Confidence-Gated Autonomy (Principle 6)."""

import pytest

from forge.runtime.confidence import (
    ConfidenceScorer,
    ConfidenceScore,
    ConfidenceLevel,
)
from forge.runtime.agent import TaskResult


class TestConfidenceScorer:
    """Tests for the ConfidenceScorer heuristic engine."""

    def setup_method(self):
        self.scorer = ConfidenceScorer()

    # --- score_tool_call tests ---

    def test_score_tool_call_read_only_high(self):
        """Read-only tools should score HIGH confidence."""
        result = self.scorer.score_tool_call("web_search", {"query": "python docs"})
        assert result.level == ConfidenceLevel.HIGH
        assert result.score >= 0.9
        assert result.action == "auto"

    def test_score_tool_call_write_medium(self):
        """Write tools should score MEDIUM confidence."""
        result = self.scorer.score_tool_call("write_file", {"path": "out.txt", "content": "hi"})
        assert result.level == ConfidenceLevel.MEDIUM
        assert 0.5 <= result.score < 0.9
        assert result.action == "flag"

    def test_score_tool_call_destructive_low(self):
        """Destructive tools should score LOW confidence."""
        result = self.scorer.score_tool_call("delete", {"path": "/important"})
        assert result.level == ConfidenceLevel.LOW
        assert result.score < 0.5
        assert result.action == "pause"

    def test_score_tool_call_unknown_medium(self):
        """Unknown tools default to MEDIUM confidence."""
        result = self.scorer.score_tool_call("custom_tool_xyz", {})
        assert result.level == ConfidenceLevel.MEDIUM
        assert result.action == "flag"

    # --- score_output tests ---

    def test_score_output_high_quality(self):
        """Good quality score should produce HIGH confidence."""
        result = self.scorer.score_output(
            output="This is a comprehensive, well-structured answer with details.",
            task="Explain Python decorators",
            quality_score=0.95,
        )
        assert result.level == ConfidenceLevel.HIGH
        assert result.score >= 0.9

    def test_score_output_hedging_language_low(self):
        """Hedging language should lower confidence."""
        result = self.scorer.score_output(
            output="I'm not sure, but maybe this could be the answer. I think it might work, possibly.",
            task="Explain Python decorators",
            quality_score=0.0,
        )
        assert result.level == ConfidenceLevel.LOW
        assert result.score < 0.5

    def test_score_output_very_short_low(self):
        """Very short output should be LOW confidence."""
        result = self.scorer.score_output(
            output="OK",
            task="Write a full report on AI trends",
            quality_score=0.0,
        )
        assert result.level == ConfidenceLevel.LOW
        assert result.score < 0.5

    def test_score_output_empty(self):
        """Empty output should be LOW confidence with score 0."""
        result = self.scorer.score_output(output="", task="Do something")
        assert result.score == 0.0
        assert result.level == ConfidenceLevel.LOW
        assert result.action == "pause"

    # --- classify tests ---

    def test_classify_boundary_zero(self):
        assert self.scorer.classify(0.0) == ConfidenceLevel.LOW

    def test_classify_boundary_low_threshold(self):
        assert self.scorer.classify(0.5) == ConfidenceLevel.MEDIUM

    def test_classify_boundary_high_threshold(self):
        assert self.scorer.classify(0.9) == ConfidenceLevel.HIGH

    def test_classify_boundary_one(self):
        assert self.scorer.classify(1.0) == ConfidenceLevel.HIGH

    def test_classify_just_below_low(self):
        assert self.scorer.classify(0.49) == ConfidenceLevel.LOW

    def test_classify_just_below_high(self):
        assert self.scorer.classify(0.89) == ConfidenceLevel.MEDIUM


class TestTaskResultConfidence:
    """Test that TaskResult includes confidence fields."""

    def test_task_result_default_confidence(self):
        result = TaskResult(success=True, output="done")
        assert result.confidence == 1.0
        assert result.confidence_level == "high"

    def test_task_result_custom_confidence(self):
        result = TaskResult(
            success=True,
            output="done",
            confidence=0.6,
            confidence_level="medium",
        )
        assert result.confidence == 0.6
        assert result.confidence_level == "medium"

    def test_task_result_low_confidence(self):
        result = TaskResult(
            success=True,
            output="maybe",
            confidence=0.3,
            confidence_level="low",
        )
        assert result.confidence == 0.3
        assert result.confidence_level == "low"


class TestConfidenceDataClasses:
    """Test confidence data classes and enum."""

    def test_confidence_level_values(self):
        assert ConfidenceLevel.HIGH == "high"
        assert ConfidenceLevel.MEDIUM == "medium"
        assert ConfidenceLevel.LOW == "low"

    def test_confidence_score_creation(self):
        cs = ConfidenceScore(
            score=0.85,
            level=ConfidenceLevel.MEDIUM,
            reasoning="test reason",
            action="flag",
        )
        assert cs.score == 0.85
        assert cs.level == ConfidenceLevel.MEDIUM
        assert cs.reasoning == "test reason"
        assert cs.action == "flag"
