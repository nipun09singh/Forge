"""Tests for forge.runtime.stress_lab."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from forge.runtime.stress_lab import StressLab, Scenario, TestResult, CycleReport


class TestScenario:
    """Tests for Scenario dataclass."""

    def test_creation(self):
        s = Scenario(
            id="s1",
            description="Handle angry customer",
            difficulty="hard",
            expected_behavior="De-escalate and resolve",
        )
        assert s.id == "s1"
        assert s.difficulty == "hard"


class TestTestResult:
    """Tests for TestResult dataclass."""

    def test_passed(self):
        r = TestResult(scenario_id="s1", passed=True, score=0.9, response="Resolved the issue")
        assert r.passed is True
        assert r.score == 0.9

    def test_failed(self):
        r = TestResult(scenario_id="s1", passed=False, score=0.3, response="Failed to help")
        assert r.passed is False


class TestStressLabInit:
    """Tests for StressLab initialization."""

    def test_init_default(self):
        lab = StressLab()
        assert lab._cycle_reports == []

    def test_init_with_agency(self):
        agency = MagicMock()
        lab = StressLab(agency=agency)
        assert lab.agency is agency


class TestFallbackScenarios:
    """Tests for fallback scenario generation."""

    def test_generates_scenarios(self):
        lab = StressLab()
        scenarios = lab._fallback_scenarios("customer support", 5)
        assert len(scenarios) == 5
        assert all(isinstance(s, Scenario) for s in scenarios)

    def test_scenarios_have_required_fields(self):
        lab = StressLab()
        scenarios = lab._fallback_scenarios("ecommerce", 3)
        for s in scenarios:
            assert s.id
            assert s.description
            assert s.difficulty in ("easy", "medium", "hard")

    def test_different_domains(self):
        lab = StressLab()
        support_scenarios = lab._fallback_scenarios("customer support", 3)
        ecommerce_scenarios = lab._fallback_scenarios("ecommerce", 3)
        assert all(isinstance(s, Scenario) for s in support_scenarios)
        assert all(isinstance(s, Scenario) for s in ecommerce_scenarios)


class TestStressLabReports:
    """Tests for report tracking."""

    def test_get_cycle_reports_empty(self):
        lab = StressLab()
        assert lab._cycle_reports == []
