"""Tests for forge.runtime.guardrails"""

import pytest
from forge.runtime.guardrails import (
    ContentFilter, ActionLimiter, ScopeGuard, GuardrailsEngine, GuardrailViolation,
)


class TestContentFilter:
    def test_detects_email_pii(self):
        cf = ContentFilter(block_pii=True)
        violations = cf.check("Contact me at john@example.com")
        assert any(v.rule == "pii_email_address" for v in violations)

    def test_detects_ssn(self):
        cf = ContentFilter(block_pii=True)
        violations = cf.check("SSN: 123-45-6789")
        assert any(v.rule == "pii_ssn" for v in violations)

    def test_detects_credit_card(self):
        cf = ContentFilter(block_pii=True)
        violations = cf.check("Card: 4111-1111-1111-1111")
        assert any(v.rule == "pii_credit_card" for v in violations)

    def test_no_pii_clean_text(self):
        cf = ContentFilter(block_pii=True)
        violations = cf.check("Hello, how can I help you today?")
        assert len(violations) == 0

    def test_custom_blocked_words(self):
        cf = ContentFilter(custom_blocked_words=["forbidden"])
        violations = cf.check("This is a forbidden word")
        assert any(v.rule == "blocked_word" for v in violations)

    def test_redact_pii(self):
        cf = ContentFilter()
        redacted = cf.redact_pii("Email: john@example.com, SSN: 123-45-6789")
        assert "john@example.com" not in redacted
        assert "123-45-6789" not in redacted
        assert "REDACTED" in redacted


class TestActionLimiter:
    def test_allows_under_limit(self):
        al = ActionLimiter(max_tool_calls=5)
        for _ in range(5):
            assert al.check_tool_call("any_tool") is None

    def test_blocks_over_limit(self):
        al = ActionLimiter(max_tool_calls=2)
        al.check_tool_call("t1")
        al.check_tool_call("t2")
        violation = al.check_tool_call("t3")
        assert violation is not None
        assert violation.severity == "block"

    def test_blocks_blocked_tools(self):
        al = ActionLimiter(blocked_tools=["dangerous_tool"])
        violation = al.check_tool_call("dangerous_tool")
        assert violation is not None

    def test_token_limit(self):
        al = ActionLimiter(max_tokens=100)
        assert al.record_tokens(50, 0.01) is None
        violation = al.record_tokens(60, 0.01)
        assert violation is not None

    def test_cost_limit(self):
        al = ActionLimiter(max_cost_usd=0.10)
        assert al.record_tokens(100, 0.05) is None
        violation = al.record_tokens(100, 0.06)
        assert violation is not None

    def test_reset(self):
        al = ActionLimiter(max_tool_calls=1)
        al.check_tool_call("t1")
        al.reset()
        assert al.check_tool_call("t1") is None


class TestScopeGuard:
    def test_blocks_localhost(self):
        sg = ScopeGuard()
        violation = sg.check_url("http://localhost:8080/admin")
        assert violation is not None

    def test_blocks_metadata(self):
        sg = ScopeGuard()
        violation = sg.check_url("http://metadata.google.internal/computeMetadata")
        assert violation is not None

    def test_allows_external(self):
        sg = ScopeGuard()
        violation = sg.check_url("https://api.example.com/data")
        assert violation is None

    def test_sql_table_restriction(self):
        sg = ScopeGuard(allowed_sql_tables=["customers", "orders"])
        assert sg.check_sql("SELECT * FROM customers") is None
        violation = sg.check_sql("SELECT * FROM secret_table")
        assert violation is not None


class TestGuardrailsEngine:
    def test_check_tool_call(self):
        engine = GuardrailsEngine(
            action_limiter=ActionLimiter(blocked_tools=["rm_rf"]),
        )
        violations = engine.check_tool_call("rm_rf", {})
        assert len(violations) > 0

    def test_check_output(self):
        engine = GuardrailsEngine()
        violations = engine.check_output("Call me at john@example.com")
        assert len(violations) > 0

    def test_redact(self):
        engine = GuardrailsEngine()
        clean = engine.redact_output("SSN: 123-45-6789")
        assert "123-45-6789" not in clean
