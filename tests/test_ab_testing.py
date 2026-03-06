"""Tests for forge.runtime.ab_testing."""

import pytest
from forge.runtime.ab_testing import ABTestManager, AgentVariant


class TestABTestManager:
    """Tests for ABTestManager."""

    def test_init(self):
        mgr = ABTestManager()
        assert mgr is not None

    def test_create_test(self):
        mgr = ABTestManager()
        test_id = mgr.create_test(
            control=AgentVariant(model="gpt-4", description="control"),
            experiment=AgentVariant(model="gpt-4o-mini", description="experiment"),
        )
        assert test_id is not None
        assert isinstance(test_id, str)

    def test_record_control_result(self):
        mgr = ABTestManager()
        test_id = mgr.create_test(
            control=AgentVariant(model="gpt-4"),
            experiment=AgentVariant(model="gpt-4o"),
        )
        mgr.record_control_result(test_id, success=True, quality=0.9, cost=0.01, duration_ms=2.0)

    def test_record_experiment_result(self):
        mgr = ABTestManager()
        test_id = mgr.create_test(
            control=AgentVariant(model="gpt-4"),
            experiment=AgentVariant(model="gpt-4o"),
        )
        mgr.record_experiment_result(test_id, success=True, quality=0.85, cost=0.005, duration_ms=1.5)

    def test_get_active_tests(self):
        mgr = ABTestManager()
        test_id = mgr.create_test(
            control=AgentVariant(model="gpt-4"),
            experiment=AgentVariant(model="gpt-4o"),
        )
        results = mgr.get_active_tests()
        assert isinstance(results, list)
        assert len(results) == 1

    def test_list_active_tests(self):
        mgr = ABTestManager()
        mgr.create_test(
            control=AgentVariant(description="a"),
            experiment=AgentVariant(description="b"),
        )
        tests = mgr.get_active_tests()
        assert len(tests) >= 1
