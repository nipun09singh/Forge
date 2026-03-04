"""Tests for forge.core.quality"""

import pytest
from forge.core.quality import BlueprintEvaluator, QualityRubric, QualityScore, format_quality_report


class TestBlueprintEvaluator:
    def test_evaluate_produces_score(self, sample_blueprint):
        evaluator = BlueprintEvaluator()
        score = evaluator.evaluate(sample_blueprint)
        assert isinstance(score, QualityScore)
        assert 0 <= score.overall_score <= 1

    def test_evaluate_has_dimensions(self, sample_blueprint):
        evaluator = BlueprintEvaluator()
        score = evaluator.evaluate(sample_blueprint)
        assert len(score.dimension_scores) >= 10

    def test_custom_threshold(self, sample_blueprint):
        rubric = QualityRubric(threshold=0.5)
        evaluator = BlueprintEvaluator(rubric=rubric)
        score = evaluator.evaluate(sample_blueprint)
        assert score.threshold == 0.5


class TestQualityReport:
    def test_format_report(self, sample_blueprint):
        evaluator = BlueprintEvaluator()
        score = evaluator.evaluate(sample_blueprint)
        report = format_quality_report(score)
        assert "Quality Assessment" in report
        assert "Overall Score" in report
