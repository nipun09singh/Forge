"""Tests for forge.runtime.model_router."""

import pytest
from forge.runtime.model_router import ModelRouter


class TestModelRouter:
    """Tests for ModelRouter."""

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
