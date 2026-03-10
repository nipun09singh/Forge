"""Tests for forge.runtime.model_router."""

import json

import pytest
from forge.runtime.model_router import (
    ADAPTIVE_MIN_SAMPLES,
    ModelRouter,
    RoutingOutcome,
    _task_hash,
)


class TestModelRouter:
    """Tests for ModelRouter."""

    def _make_router(self, tmp_path):
        """Helper: create a router with a temp feedback file."""
        return ModelRouter(feedback_path=tmp_path / "router_feedback.json")

    def test_init(self):
        router = ModelRouter()
        assert router is not None

    def test_select_model_simple_task(self):
        router = ModelRouter()
        model = router.select_model(
            task="Classify this email as spam or not spam",
            messages=[{"role": "user", "content": "Is this spam?"}],
            has_tools=False,
            agent_role="classifier",
        )
        assert isinstance(model, str)
        assert len(model) > 0

    def test_select_model_complex_task(self):
        router = ModelRouter()
        model = router.select_model(
            task="Design a microservices architecture for a banking platform with compliance requirements",
            messages=[{"role": "user", "content": "Design the architecture"}] * 10,
            has_tools=True,
            agent_role="architect",
        )
        assert isinstance(model, str)

    def test_select_model_returns_valid_model(self):
        router = ModelRouter()
        model = router.select_model(
            task="Simple hello",
            messages=[],
            has_tools=False,
            agent_role="specialist",
        )
        known_models = ["gpt-4", "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo", "gpt-4-turbo"]
        assert any(m in model for m in known_models)

    def test_get_stats(self):
        router = ModelRouter()
        stats = router.get_stats()
        assert isinstance(stats, dict)


class TestFeedbackRecording:
    """Tests for outcome recording and feedback history."""

    def test_record_single_outcome(self, tmp_path):
        router = ModelRouter(feedback_path=tmp_path / "fb.json")
        router.record_outcome(
            task_id="task-1",
            model_used="gpt-4o-mini",
            success=True,
            quality_score=0.95,
            tokens_used=150,
            cost=0.001,
            complexity_assessed="low",
        )
        assert len(router._feedback_history) == 1
        outcome = router._feedback_history[0]
        assert outcome.task_hash == _task_hash("task-1")
        assert outcome.success is True
        assert outcome.quality_score == 0.95
        assert outcome.tokens == 150
        assert outcome.cost == 0.001
        assert outcome.complexity_assessed == "low"
        assert outcome.model_selected == "gpt-4o-mini"

    def test_record_multiple_outcomes(self, tmp_path):
        router = ModelRouter(feedback_path=tmp_path / "fb.json")
        for i in range(10):
            router.record_outcome(
                task_id=f"task-{i}",
                model_used="gpt-4o",
                success=i % 2 == 0,
                quality_score=0.8,
                tokens_used=200,
                cost=0.01,
            )
        assert len(router._feedback_history) == 10

    def test_routing_outcome_dataclass(self):
        o = RoutingOutcome(
            task_hash="abc123",
            complexity_assessed="medium",
            model_selected="gpt-4o",
            success=True,
            quality_score=0.9,
            tokens=100,
            cost=0.005,
        )
        assert o.task_hash == "abc123"
        assert o.timestamp > 0


class TestAdaptiveRouting:
    """Tests for adaptive threshold adjustment based on feedback."""

    def _feed_outcomes(
        self, router, count, model, success, complexity="medium"
    ):
        for i in range(count):
            router.record_outcome(
                task_id=f"adapt-{complexity}-{i}",
                model_used=model,
                success=success,
                quality_score=0.9 if success else 0.3,
                tokens_used=100,
                cost=0.001,
                complexity_assessed=complexity,
            )

    def test_downgrade_medium_to_low_when_fast_succeeds(self, tmp_path):
        """If fast model succeeds 90%+ on medium tasks → route medium→low."""
        router = ModelRouter(feedback_path=tmp_path / "fb.json")
        # Feed 25 successful fast outcomes on medium tasks
        self._feed_outcomes(router, ADAPTIVE_MIN_SAMPLES + 5, "gpt-4o-mini", True, "medium")
        assert router._routing_adjustments.get("medium") == "low"
        # Now selecting model for a medium-complexity task should pick fast
        model = router.select_model(task="do something with tools", has_tools=True)
        assert model == router.fast_model

    def test_upgrade_low_to_medium_when_fast_fails(self, tmp_path):
        """If fast model fails 30%+ on low tasks → upgrade low→medium."""
        router = ModelRouter(feedback_path=tmp_path / "fb.json")
        # Feed mix: 70% success, 30% failure (meets 30% failure threshold)
        n_success = 14
        n_fail = ADAPTIVE_MIN_SAMPLES + 5 - n_success  # leaves >30% failure
        # Actually we need exactly 30% failure rate on at least ADAPTIVE_MIN_SAMPLES
        total = ADAPTIVE_MIN_SAMPLES + 5
        n_fail = int(total * 0.35)  # 35% failure
        n_success = total - n_fail
        self._feed_outcomes(router, n_success, "gpt-4o-mini", True, "low")
        self._feed_outcomes(router, n_fail, "gpt-4o-mini", False, "low")
        assert router._routing_adjustments.get("low") == "medium"

    def test_no_adjustment_below_min_samples(self, tmp_path):
        """No adjustments should be made with fewer than ADAPTIVE_MIN_SAMPLES."""
        router = ModelRouter(feedback_path=tmp_path / "fb.json")
        self._feed_outcomes(router, ADAPTIVE_MIN_SAMPLES - 5, "gpt-4o-mini", True, "medium")
        assert router._routing_adjustments == {}

    def test_upgrade_medium_to_high_when_standard_fails(self, tmp_path):
        """If standard model fails 30%+ on medium tasks → upgrade medium→high."""
        router = ModelRouter(feedback_path=tmp_path / "fb.json")
        total = ADAPTIVE_MIN_SAMPLES + 5
        n_fail = int(total * 0.35)
        n_success = total - n_fail
        self._feed_outcomes(router, n_success, "gpt-4o", True, "medium")
        self._feed_outcomes(router, n_fail, "gpt-4o", False, "medium")
        assert router._routing_adjustments.get("medium") == "high"

    def test_adaptive_override_applies_in_select_model(self, tmp_path):
        """Routing adjustments should influence select_model output."""
        router = ModelRouter(feedback_path=tmp_path / "fb.json")
        router._routing_adjustments["medium"] = "low"
        # A task that normally routes to standard should now use fast
        model = router.select_model(task="do something with tools", has_tools=True)
        assert model == router.fast_model


class TestPersistence:
    """Tests for saving and loading feedback state."""

    def test_save_and_load_roundtrip(self, tmp_path):
        fb_path = tmp_path / "router_feedback.json"
        router = ModelRouter(feedback_path=fb_path)
        router.record_outcome(
            task_id="persist-1",
            model_used="gpt-4o-mini",
            success=True,
            quality_score=0.9,
            tokens_used=100,
            cost=0.001,
            complexity_assessed="low",
        )
        router._routing_adjustments["medium"] = "low"
        router.save()

        # Create a new router from the same file
        router2 = ModelRouter(feedback_path=fb_path)
        assert len(router2._feedback_history) == 1
        assert router2._feedback_history[0].task_hash == _task_hash("persist-1")
        assert router2._feedback_history[0].success is True
        assert router2._routing_adjustments == {"medium": "low"}

    def test_auto_save_after_interval(self, tmp_path):
        """Router auto-saves after PERSISTENCE_SAVE_INTERVAL outcomes."""
        fb_path = tmp_path / "router_feedback.json"
        router = ModelRouter(feedback_path=fb_path)
        # Record 5 outcomes (PERSISTENCE_SAVE_INTERVAL=5)
        for i in range(5):
            router.record_outcome(
                task_id=f"auto-{i}",
                model_used="gpt-4o",
                success=True,
                quality_score=0.8,
                tokens_used=200,
                cost=0.01,
            )
        assert fb_path.exists()
        data = json.loads(fb_path.read_text())
        assert len(data["feedback_history"]) == 5

    def test_load_missing_file(self, tmp_path):
        """Loading from a non-existent file should be a no-op."""
        router = ModelRouter(feedback_path=tmp_path / "nonexistent.json")
        assert len(router._feedback_history) == 0
        assert router._routing_adjustments == {}

    def test_load_corrupt_file(self, tmp_path):
        """Loading a corrupt file should not crash."""
        fb_path = tmp_path / "router_feedback.json"
        fb_path.write_text("NOT VALID JSON {{{")
        router = ModelRouter(feedback_path=fb_path)
        assert len(router._feedback_history) == 0


class TestEnhancedStats:
    """Tests for the enhanced get_stats with feedback data."""

    def test_stats_without_feedback(self, tmp_path):
        router = ModelRouter(feedback_path=tmp_path / "fb.json")
        router.select_model(task="classify this item", agent_role="classifier")
        stats = router.get_stats()
        assert stats["total_calls"] >= 1
        assert "feedback" not in stats  # No feedback yet

    def test_stats_with_feedback(self, tmp_path):
        router = ModelRouter(feedback_path=tmp_path / "fb.json")
        router.select_model(task="classify this item", agent_role="classifier")
        for i in range(5):
            router.record_outcome(
                task_id=f"stats-{i}",
                model_used="gpt-4o-mini",
                success=True,
                quality_score=0.9,
                tokens_used=100,
                cost=0.001,
                complexity_assessed="low",
            )
        stats = router.get_stats()
        assert "feedback" in stats
        fb = stats["feedback"]
        assert fb["total_outcomes"] == 5
        assert "fast" in fb["per_model"]
        assert fb["per_model"]["fast"]["success_rate"] == 100.0
        assert fb["per_model"]["fast"]["calls"] == 5
        assert fb["total_actual_cost"] == pytest.approx(0.005)

    def test_stats_with_adjustments(self, tmp_path):
        router = ModelRouter(feedback_path=tmp_path / "fb.json")
        router._routing_adjustments["medium"] = "low"
        router.select_model(task="hello", has_tools=True)
        stats = router.get_stats()
        assert stats.get("routing_adjustments") == {"medium": "low"}

    def test_stats_recommendations(self, tmp_path):
        router = ModelRouter(feedback_path=tmp_path / "fb.json")
        router.select_model(task="classify this item quickly")
        for i in range(15):
            router.record_outcome(
                task_id=f"rec-{i}",
                model_used="gpt-4o-mini",
                success=True,
                quality_score=0.95,
                tokens_used=50,
                cost=0.0005,
                complexity_assessed="low",
            )
        stats = router.get_stats()
        recommendations = stats["feedback"]["recommendations"]
        assert any("sufficient" in r.lower() or "fast model" in r.lower() for r in recommendations)

    def test_stats_success_rate_per_model(self, tmp_path):
        router = ModelRouter(feedback_path=tmp_path / "fb.json")
        router.select_model(task="do something")
        # 3 successes, 2 failures for standard
        for i in range(3):
            router.record_outcome(
                task_id=f"sr-s-{i}", model_used="gpt-4o", success=True,
                quality_score=0.8, tokens_used=200, cost=0.01,
            )
        for i in range(2):
            router.record_outcome(
                task_id=f"sr-f-{i}", model_used="gpt-4o", success=False,
                quality_score=0.2, tokens_used=200, cost=0.01,
            )
        fb = router.get_stats()["feedback"]
        assert fb["per_model"]["standard"]["success_rate"] == 60.0
        assert fb["per_model"]["standard"]["calls"] == 5
