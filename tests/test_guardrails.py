"""Tests for forge.runtime.guardrails"""

import pytest
from forge.runtime.guardrails import (
    ContentFilter, ActionLimiter, ScopeGuard, GuardrailsEngine, GuardrailViolation,
    SqlSanitizer, luhn_check, PII_CATEGORIES, ALL_PII_CATEGORIES,
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


class TestSqlSanitizer:
    """Tests for the SqlSanitizer class."""

    def test_strip_block_comments(self):
        s = SqlSanitizer()
        assert "secret" not in s.sanitize("SELECT /* secret */ 1")

    def test_strip_line_comments(self):
        s = SqlSanitizer()
        cleaned = s.sanitize("SELECT 1 -- drop everything")
        assert "drop" not in cleaned.lower()

    def test_normalize_whitespace(self):
        s = SqlSanitizer()
        assert s.sanitize("SELECT  \n  *  \t FROM  t") == "SELECT * FROM t"

    def test_validate_blocks_drop(self):
        s = SqlSanitizer()
        v = s.validate("DROP TABLE users")
        assert v is not None and v.rule == "sql_blocked_statement"

    def test_validate_blocks_alter(self):
        s = SqlSanitizer()
        v = s.validate("ALTER TABLE users ADD COLUMN x INT")
        assert v is not None and v.rule == "sql_blocked_statement"

    def test_validate_blocks_create(self):
        s = SqlSanitizer()
        v = s.validate("CREATE TABLE evil (id INT)")
        assert v is not None and v.rule == "sql_blocked_statement"

    def test_validate_blocks_truncate(self):
        s = SqlSanitizer()
        v = s.validate("TRUNCATE TABLE users")
        assert v is not None and v.rule == "sql_blocked_statement"

    def test_validate_allows_select(self):
        s = SqlSanitizer()
        assert s.validate("SELECT * FROM users") is None

    def test_validate_allows_insert(self):
        s = SqlSanitizer()
        assert s.validate("INSERT INTO users (name) VALUES ('a')") is None

    def test_validate_allows_update(self):
        s = SqlSanitizer()
        assert s.validate("UPDATE users SET name = 'b' WHERE id = 1") is None

    def test_validate_allows_delete(self):
        s = SqlSanitizer()
        assert s.validate("DELETE FROM users WHERE id = 1") is None

    def test_validate_allows_with_cte(self):
        s = SqlSanitizer()
        assert s.validate("WITH cte AS (SELECT 1) SELECT * FROM cte") is None

    def test_validate_blocks_semicolon(self):
        s = SqlSanitizer()
        v = s.validate("SELECT 1; DROP TABLE users")
        assert v is not None and v.rule == "sql_multi_statement"

    def test_validate_blocks_sleep(self):
        s = SqlSanitizer()
        v = s.validate("SELECT SLEEP(10)")
        assert v is not None and v.rule == "sql_dangerous_function"

    def test_validate_blocks_benchmark(self):
        s = SqlSanitizer()
        v = s.validate("SELECT BENCHMARK(1000000, SHA1('test'))")
        assert v is not None and v.rule == "sql_dangerous_function"

    def test_validate_blocks_load_file(self):
        s = SqlSanitizer()
        v = s.validate("SELECT LOAD_FILE('/etc/passwd')")
        assert v is not None and v.rule == "sql_dangerous_function"

    def test_is_parameterized_detects_tautology(self):
        s = SqlSanitizer()
        v = s.is_parameterized("SELECT * FROM users WHERE id = 1 OR 1=1")
        assert v is not None and v.rule == "sql_injection_pattern"

    def test_is_parameterized_string_tautology(self):
        s = SqlSanitizer()
        v = s.is_parameterized("SELECT * FROM users WHERE name = '' OR 'a'='a'")
        assert v is not None and v.rule == "sql_injection_pattern"

    def test_is_parameterized_clean_query(self):
        s = SqlSanitizer()
        assert s.is_parameterized("SELECT * FROM users WHERE id = ?") is None


class TestScopeGuardSqlEnhanced:
    """Tests for the enhanced ScopeGuard.check_sql()."""

    def test_blocks_drop_even_without_table_restrictions(self):
        sg = ScopeGuard()  # No allowed_tables
        v = sg.check_sql("DROP TABLE users")
        assert v is not None and v.rule == "sql_blocked_statement"

    def test_blocks_semicolon_injection(self):
        sg = ScopeGuard()
        v = sg.check_sql("SELECT 1; DROP TABLE users")
        assert v is not None and v.rule == "sql_multi_statement"

    def test_blocks_comment_bypass(self):
        """Comments hiding a disallowed table should be stripped first."""
        sg = ScopeGuard(allowed_sql_tables=["customers"])
        v = sg.check_sql("SELECT * FROM /*customers*/ secret_table")
        assert v is not None and v.rule == "sql_table_not_allowed"

    def test_blocks_line_comment_bypass(self):
        sg = ScopeGuard(allowed_sql_tables=["customers"])
        v = sg.check_sql("SELECT * FROM secret_table -- actually customers")
        assert v is not None and v.rule == "sql_table_not_allowed"

    def test_blocks_dangerous_function_with_tables(self):
        sg = ScopeGuard(allowed_sql_tables=["customers"])
        v = sg.check_sql("SELECT SLEEP(5) FROM customers")
        assert v is not None and v.rule == "sql_dangerous_function"

    def test_blocks_tautology_injection_with_tables(self):
        sg = ScopeGuard(allowed_sql_tables=["users"])
        v = sg.check_sql("SELECT * FROM users WHERE name = '' OR 1=1")
        assert v is not None
        assert v.severity == "block"

    def test_allows_legitimate_query(self):
        sg = ScopeGuard(allowed_sql_tables=["customers", "orders"])
        assert sg.check_sql("SELECT * FROM customers WHERE id = ?") is None

    def test_allows_join_on_allowed_tables(self):
        sg = ScopeGuard(allowed_sql_tables=["customers", "orders"])
        assert sg.check_sql(
            "SELECT c.name FROM customers c JOIN orders o ON c.id = o.cust_id"
        ) is None

    def test_no_restrictions_allows_safe_queries(self):
        sg = ScopeGuard()
        assert sg.check_sql("SELECT * FROM any_table") is None

    def test_exec_blocked(self):
        sg = ScopeGuard()
        v = sg.check_sql("EXEC sp_executesql N'SELECT 1'")
        assert v is not None


# ---------------------------------------------------------------------------
# Luhn algorithm
# ---------------------------------------------------------------------------
class TestLuhnCheck:
    def test_valid_visa(self):
        assert luhn_check("4111111111111111") is True

    def test_valid_mastercard(self):
        assert luhn_check("5500000000000004") is True

    def test_invalid_number(self):
        assert luhn_check("1234567890123456") is False

    def test_too_short(self):
        assert luhn_check("12345") is False

    def test_strips_non_digits(self):
        assert luhn_check("4111-1111-1111-1111") is True


# ---------------------------------------------------------------------------
# Expanded PII patterns
# ---------------------------------------------------------------------------
class TestPIIPatterns:
    """Positive and negative tests for every PII pattern."""

    # -- financial --
    def test_credit_card_valid_luhn(self):
        cf = ContentFilter(enabled_pii_categories={"financial"})
        violations = cf.check("Card: 4111-1111-1111-1111")
        assert any(v.rule == "pii_credit_card" for v in violations)

    def test_credit_card_invalid_luhn(self):
        cf = ContentFilter(enabled_pii_categories={"financial"})
        violations = cf.check("Card: 1234-5678-9012-3456")
        assert not any(v.rule == "pii_credit_card" for v in violations)

    def test_iban_positive(self):
        cf = ContentFilter(enabled_pii_categories={"financial"})
        violations = cf.check("IBAN: GB29NWBK60161331926819")
        assert any(v.rule == "pii_iban" for v in violations)

    def test_iban_negative(self):
        cf = ContentFilter(enabled_pii_categories={"financial"})
        violations = cf.check("Just some text with no bank numbers")
        assert not any(v.rule == "pii_iban" for v in violations)

    # -- identity --
    def test_ssn_positive(self):
        cf = ContentFilter(enabled_pii_categories={"identity"})
        violations = cf.check("SSN: 123-45-6789")
        assert any(v.rule == "pii_ssn" for v in violations)

    def test_ssn_negative(self):
        cf = ContentFilter(enabled_pii_categories={"identity"})
        violations = cf.check("Phone: 555-1234")
        assert not any(v.rule == "pii_ssn" for v in violations)

    def test_passport_us_positive(self):
        cf = ContentFilter(enabled_pii_categories={"identity"})
        violations = cf.check("Passport: 123456789")
        assert any(v.rule == "pii_passport" for v in violations)

    def test_passport_uk_positive(self):
        cf = ContentFilter(enabled_pii_categories={"identity"})
        violations = cf.check("Passport: AB1234567")
        assert any(v.rule == "pii_passport" for v in violations)

    def test_passport_negative(self):
        cf = ContentFilter(enabled_pii_categories={"identity"})
        violations = cf.check("Order number: 42")
        assert not any(v.rule == "pii_passport" for v in violations)

    # -- contact --
    def test_phone_us_positive(self):
        cf = ContentFilter(enabled_pii_categories={"contact"})
        violations = cf.check("Call: (555) 123-4567")
        assert any(v.rule == "pii_phone_us" for v in violations)

    def test_phone_us_negative(self):
        cf = ContentFilter(enabled_pii_categories={"contact"})
        violations = cf.check("No phone here")
        assert not any(v.rule == "pii_phone_us" for v in violations)

    def test_phone_intl_positive(self):
        cf = ContentFilter(enabled_pii_categories={"contact"})
        violations = cf.check("Call: +44 20 7946 0958")
        assert any(v.rule == "pii_phone_intl" for v in violations)

    def test_phone_intl_negative(self):
        cf = ContentFilter(enabled_pii_categories={"contact"})
        violations = cf.check("Version +3 released")
        assert not any(v.rule == "pii_phone_intl" for v in violations)

    def test_email_positive(self):
        cf = ContentFilter(enabled_pii_categories={"contact"})
        violations = cf.check("Email: alice@example.com")
        assert any(v.rule == "pii_email_address" for v in violations)

    def test_email_negative(self):
        cf = ContentFilter(enabled_pii_categories={"contact"})
        violations = cf.check("No email here")
        assert not any(v.rule == "pii_email_address" for v in violations)

    # -- network --
    def test_ipv4_positive(self):
        cf = ContentFilter(enabled_pii_categories={"network"})
        violations = cf.check("Server at 192.168.1.100")
        assert any(v.rule == "pii_ipv4_address" for v in violations)

    def test_ipv4_negative(self):
        cf = ContentFilter(enabled_pii_categories={"network"})
        violations = cf.check("Version 3.2.1 released")
        assert not any(v.rule == "pii_ipv4_address" for v in violations)

    def test_ipv6_positive(self):
        cf = ContentFilter(enabled_pii_categories={"network"})
        violations = cf.check("Host: 2001:0db8:85a3:0000:0000:8a2e:0370:7334")
        assert any(v.rule == "pii_ipv6_address" for v in violations)

    def test_ipv6_negative(self):
        cf = ContentFilter(enabled_pii_categories={"network"})
        violations = cf.check("No IPv6 here")
        assert not any(v.rule == "pii_ipv6_address" for v in violations)

    def test_url_with_credentials_positive(self):
        cf = ContentFilter(enabled_pii_categories={"network"})
        violations = cf.check("DB: https://admin:secret@db.internal.com")
        assert any(v.rule == "pii_url_with_credentials" for v in violations)

    def test_url_with_credentials_negative(self):
        cf = ContentFilter(enabled_pii_categories={"network"})
        violations = cf.check("Visit https://example.com")
        assert not any(v.rule == "pii_url_with_credentials" for v in violations)

    # -- secrets --
    def test_aws_access_key_positive(self):
        cf = ContentFilter(enabled_pii_categories={"secrets"})
        violations = cf.check("Key: AKIAIOSFODNN7EXAMPLE")
        assert any(v.rule == "pii_aws_access_key" for v in violations)

    def test_aws_access_key_negative(self):
        cf = ContentFilter(enabled_pii_categories={"secrets"})
        violations = cf.check("No AWS keys here")
        assert not any(v.rule == "pii_aws_access_key" for v in violations)

    def test_api_key_prefixed_positive(self):
        cf = ContentFilter(enabled_pii_categories={"secrets"})
        violations = cf.check("sk-abc12345678901234567890")
        assert any(v.rule == "pii_api_key_prefixed" for v in violations)

    def test_api_key_prefixed_negative(self):
        cf = ContentFilter(enabled_pii_categories={"secrets"})
        violations = cf.check("sk-short")
        assert not any(v.rule == "pii_api_key_prefixed" for v in violations)

    def test_bearer_token_positive(self):
        cf = ContentFilter(enabled_pii_categories={"secrets"})
        violations = cf.check("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9")
        assert any(v.rule == "pii_bearer_token" for v in violations)

    def test_bearer_token_negative(self):
        cf = ContentFilter(enabled_pii_categories={"secrets"})
        violations = cf.check("The standard bearer led the march")
        assert not any(v.rule == "pii_bearer_token" for v in violations)

    def test_generic_hex_secret_positive(self):
        cf = ContentFilter(enabled_pii_categories={"secrets"})
        violations = cf.check("api_key=aabbccdd00112233445566778899aabb00112233")
        assert any(v.rule == "pii_generic_hex_secret" for v in violations)

    def test_generic_hex_secret_negative(self):
        cf = ContentFilter(enabled_pii_categories={"secrets"})
        violations = cf.check("color=#FF5733")
        assert not any(v.rule == "pii_generic_hex_secret" for v in violations)


# ---------------------------------------------------------------------------
# Category configuration
# ---------------------------------------------------------------------------
class TestPIICategoryConfig:
    def test_default_enables_all(self):
        cf = ContentFilter()
        assert cf.enabled_pii_categories == ALL_PII_CATEGORIES

    def test_enable_single_category(self):
        cf = ContentFilter(enabled_pii_categories={"contact"})
        assert "email_address" in cf._pii_patterns
        assert "credit_card" not in cf._pii_patterns

    def test_disable_secrets(self):
        cf = ContentFilter(enabled_pii_categories=ALL_PII_CATEGORIES - {"secrets"})
        assert "aws_access_key" not in cf._pii_patterns
        assert "ssn" in cf._pii_patterns

    def test_invalid_category_ignored(self):
        cf = ContentFilter(enabled_pii_categories={"contact", "nonexistent"})
        assert cf.enabled_pii_categories == {"contact"}


# ---------------------------------------------------------------------------
# Redaction with Luhn
# ---------------------------------------------------------------------------
class TestRedactPIIExpanded:
    def test_redact_valid_credit_card(self):
        cf = ContentFilter(enabled_pii_categories={"financial"})
        result = cf.redact_pii("Card: 4111-1111-1111-1111")
        assert "4111" not in result
        assert "REDACTED_CREDIT_CARD" in result

    def test_no_redact_invalid_credit_card(self):
        cf = ContentFilter(enabled_pii_categories={"financial"})
        result = cf.redact_pii("Card: 1234-5678-9012-3456")
        assert "1234-5678-9012-3456" in result

    def test_redact_aws_key(self):
        cf = ContentFilter(enabled_pii_categories={"secrets"})
        result = cf.redact_pii("Key: AKIAIOSFODNN7EXAMPLE")
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "REDACTED_AWS_ACCESS_KEY" in result

    def test_redact_iban(self):
        cf = ContentFilter(enabled_pii_categories={"financial"})
        result = cf.redact_pii("IBAN: GB29NWBK60161331926819")
        assert "GB29NWBK" not in result
        assert "REDACTED_IBAN" in result

    def test_redact_url_credentials(self):
        cf = ContentFilter(enabled_pii_categories={"network"})
        result = cf.redact_pii("DB: https://admin:password@db.host.com/mydb")
        assert "admin:password" not in result
