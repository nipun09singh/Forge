"""Tests for the rate limiter module."""

import asyncio
import json
import time
import pytest
from unittest.mock import patch

from forge.runtime.integrations.rate_limiter import (
    RateLimiter,
    AmountRateLimiter,
    RateLimitExceeded,
    get_email_limiter,
    get_sms_limiter,
    get_stripe_limiter,
    get_stripe_amount_limiter,
    get_http_limiter,
    get_webhook_limiter,
    rate_limit_error,
    amount_limit_error,
    reset_all_limiters,
)


@pytest.fixture(autouse=True)
def _reset_limiters():
    """Reset shared limiter instances between tests."""
    reset_all_limiters()
    yield
    reset_all_limiters()


class TestRateLimiter:
    """Core RateLimiter behaviour."""

    def test_allows_calls_within_limit(self):
        rl = RateLimiter(max_calls=3, period_seconds=60)
        assert rl.acquire() is True
        assert rl.acquire() is True
        assert rl.acquire() is True

    def test_blocks_after_limit(self):
        rl = RateLimiter(max_calls=2, period_seconds=60)
        assert rl.acquire() is True
        assert rl.acquire() is True
        assert rl.acquire() is False

    def test_remaining(self):
        rl = RateLimiter(max_calls=5, period_seconds=60)
        assert rl.remaining() == 5
        rl.acquire()
        assert rl.remaining() == 4
        rl.acquire()
        rl.acquire()
        assert rl.remaining() == 2

    def test_retry_after_zero_when_allowed(self):
        rl = RateLimiter(max_calls=2, period_seconds=60)
        assert rl.retry_after() == 0.0

    def test_retry_after_positive_when_blocked(self):
        rl = RateLimiter(max_calls=1, period_seconds=60)
        rl.acquire()
        assert rl.retry_after() > 0

    def test_check_or_raise_passes(self):
        rl = RateLimiter(max_calls=1, period_seconds=60)
        rl.check_or_raise()  # should not raise

    def test_check_or_raise_raises(self):
        rl = RateLimiter(max_calls=1, period_seconds=60)
        rl.acquire()
        with pytest.raises(RateLimitExceeded) as exc_info:
            rl.check_or_raise()
        assert exc_info.value.limit == 1
        assert exc_info.value.retry_after > 0

    def test_per_key_isolation(self):
        rl = RateLimiter(max_calls=1, period_seconds=60)
        assert rl.acquire("a") is True
        assert rl.acquire("a") is False
        assert rl.acquire("b") is True  # different key still allowed

    def test_window_expiry(self):
        rl = RateLimiter(max_calls=1, period_seconds=1)
        assert rl.acquire() is True
        assert rl.acquire() is False
        time.sleep(1.1)
        assert rl.acquire() is True  # window expired

    def test_invalid_params(self):
        with pytest.raises(ValueError):
            RateLimiter(max_calls=0, period_seconds=60)
        with pytest.raises(ValueError):
            RateLimiter(max_calls=5, period_seconds=-1)


class TestAmountRateLimiter:
    """AmountRateLimiter behaviour for dollar-amount caps."""

    def test_allows_within_budget(self):
        rl = AmountRateLimiter(max_amount=100, period_seconds=60)
        assert rl.acquire(50) is True
        assert rl.acquire(30) is True

    def test_blocks_over_budget(self):
        rl = AmountRateLimiter(max_amount=100, period_seconds=60)
        assert rl.acquire(80) is True
        assert rl.acquire(30) is False  # 80 + 30 > 100

    def test_remaining(self):
        rl = AmountRateLimiter(max_amount=100, period_seconds=60)
        assert rl.remaining() == 100
        rl.acquire(40)
        assert rl.remaining() == 60

    def test_check_or_raise(self):
        rl = AmountRateLimiter(max_amount=50, period_seconds=60)
        rl.acquire(50)
        with pytest.raises(RateLimitExceeded):
            rl.check_or_raise(10)


class TestSharedLimiterDefaults:
    """Verify default limits for each integration."""

    def test_email_limiter_defaults(self):
        rl = get_email_limiter()
        assert rl.max_calls == 20
        assert rl.period_seconds == 3600

    def test_sms_limiter_defaults(self):
        rl = get_sms_limiter()
        assert rl.max_calls == 10
        assert rl.period_seconds == 3600

    def test_stripe_limiter_defaults(self):
        rl = get_stripe_limiter()
        assert rl.max_calls == 20
        assert rl.period_seconds == 3600

    def test_stripe_amount_limiter_defaults(self):
        rl = get_stripe_amount_limiter()
        assert rl.max_amount == 50000  # $500 in cents
        assert rl.period_seconds == 3600

    def test_http_limiter_defaults(self):
        rl = get_http_limiter()
        assert rl.max_calls == 100
        assert rl.period_seconds == 60

    def test_webhook_limiter_defaults(self):
        rl = get_webhook_limiter()
        assert rl.max_calls == 30
        assert rl.period_seconds == 60


class TestEnvVarConfiguration:
    """Limits are configurable via environment variables."""

    def test_email_custom_limit(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_EMAIL_PER_HOUR", "5")
        rl = get_email_limiter()
        assert rl.max_calls == 5

    def test_http_custom_limit(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_HTTP_PER_MINUTE", "200")
        rl = get_http_limiter()
        assert rl.max_calls == 200


class TestErrorMessages:
    """Error JSON is well-structured and informative."""

    def test_rate_limit_error_json(self):
        rl = RateLimiter(max_calls=5, period_seconds=60)
        msg = json.loads(rate_limit_error("send_email", rl))
        assert msg["success"] is False
        assert msg["error"] == "rate_limit_exceeded"
        assert "send_email" in msg["message"]
        assert "Remaining" in msg["message"]

    def test_amount_limit_error_json(self):
        rl = AmountRateLimiter(max_amount=50000, period_seconds=3600)
        msg = json.loads(amount_limit_error("stripe_payment", rl, 60000))
        assert msg["success"] is False
        assert msg["error"] == "rate_limit_exceeded"
        assert "60000" in msg["message"]


class TestIntegrationRateLimiting:
    """Rate limiting fires inside actual tool functions."""

    @pytest.mark.asyncio
    async def test_sms_rate_limited(self, monkeypatch):
        monkeypatch.setenv("MOCK_MODE", "true")
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
        monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
        monkeypatch.setenv("RATE_LIMIT_SMS_PER_HOUR", "2")
        from forge.runtime.integrations.twilio_tool import create_twilio_tool
        tool = create_twilio_tool()
        r1 = json.loads(await tool.run(to="+1555", body="msg1"))
        assert r1["success"] is True
        r2 = json.loads(await tool.run(to="+1555", body="msg2"))
        assert r2["success"] is True
        r3 = json.loads(await tool.run(to="+1555", body="msg3"))
        assert r3["success"] is False
        assert r3["error"] == "rate_limit_exceeded"

    @pytest.mark.asyncio
    async def test_email_rate_limited(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_EMAIL_PER_HOUR", "1")
        from forge.runtime.integrations.email_tool import send_email
        # First call may fail on SMTP connect but should NOT be rate-limited
        r1 = json.loads(await send_email("a@b.com", "s", "b"))
        # Could be SMTP error but not rate_limit_exceeded
        r2 = json.loads(await send_email("a@b.com", "s", "b"))
        assert r2["success"] is False
        assert r2["error"] == "rate_limit_exceeded"

    @pytest.mark.asyncio
    async def test_http_rate_limited(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_HTTP_PER_MINUTE", "1")
        from forge.runtime.integrations.http_tool import http_request
        # First call passes rate limit (may fail on network)
        await http_request("https://example.com")
        r2 = json.loads(await http_request("https://example.com"))
        assert r2["success"] is False
        assert r2["error"] == "rate_limit_exceeded"

    @pytest.mark.asyncio
    async def test_webhook_rate_limited(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_WEBHOOK_PER_MINUTE", "1")
        from forge.runtime.integrations.webhook_tool import send_webhook
        await send_webhook("https://example.com/hook", '{"a":1}')
        r2 = json.loads(await send_webhook("https://example.com/hook", '{"a":1}'))
        assert r2["success"] is False
        assert r2["error"] == "rate_limit_exceeded"

    @pytest.mark.asyncio
    async def test_stripe_charge_rate_limited(self, monkeypatch):
        monkeypatch.setenv("MOCK_MODE", "true")
        monkeypatch.delenv("STRIPE_API_KEY", raising=False)
        monkeypatch.setenv("RATE_LIMIT_STRIPE_PER_HOUR", "1")
        from forge.runtime.integrations.stripe_tool import _stripe_action
        r1 = json.loads(await _stripe_action(action="charge", amount=100))
        assert r1["success"] is True
        r2 = json.loads(await _stripe_action(action="charge", amount=100))
        assert r2["success"] is False
        assert r2["error"] == "rate_limit_exceeded"

    @pytest.mark.asyncio
    async def test_stripe_amount_cap(self, monkeypatch):
        monkeypatch.setenv("MOCK_MODE", "true")
        monkeypatch.delenv("STRIPE_API_KEY", raising=False)
        monkeypatch.setenv("RATE_LIMIT_STRIPE_PER_HOUR", "100")  # high count limit
        monkeypatch.setenv("RATE_LIMIT_STRIPE_AMOUNT_PER_HOUR", "1000")  # $10 cap
        from forge.runtime.integrations.stripe_tool import _stripe_action
        r1 = json.loads(await _stripe_action(action="charge", amount=900))
        assert r1["success"] is True
        r2 = json.loads(await _stripe_action(action="charge", amount=200))
        assert r2["success"] is False
        assert "amount" in r2["message"].lower() or "rate_limit" in r2["error"]

    @pytest.mark.asyncio
    async def test_stripe_list_not_rate_limited(self, monkeypatch):
        monkeypatch.setenv("MOCK_MODE", "true")
        monkeypatch.delenv("STRIPE_API_KEY", raising=False)
        monkeypatch.setenv("RATE_LIMIT_STRIPE_PER_HOUR", "1")
        from forge.runtime.integrations.stripe_tool import _stripe_action
        # list_charges should not be rate-limited
        r1 = json.loads(await _stripe_action(action="list_charges"))
        assert r1["success"] is True
        r2 = json.loads(await _stripe_action(action="list_charges"))
        assert r2["success"] is True


# ---------------------------------------------------------------------------
# Edge-case tests — concurrency, reset, amount boundary
# ---------------------------------------------------------------------------

class TestRateLimiterConcurrency:
    """Concurrent access to the rate limiter from multiple asyncio tasks."""

    @pytest.mark.asyncio
    async def test_concurrent_acquire(self):
        """Multiple tasks calling acquire() simultaneously respect the limit."""
        rl = RateLimiter(max_calls=5, period_seconds=60)

        async def _try():
            return rl.acquire()

        results = await asyncio.gather(*[_try() for _ in range(10)])
        assert results.count(True) == 5
        assert results.count(False) == 5

    @pytest.mark.asyncio
    async def test_concurrent_remaining_consistent(self):
        """remaining() stays consistent under concurrent acquire()."""
        rl = RateLimiter(max_calls=3, period_seconds=60)

        async def _acquire_and_check():
            rl.acquire()
            return rl.remaining()

        results = await asyncio.gather(*[_acquire_and_check() for _ in range(3)])
        # After all 3 acquires, remaining must be 0
        assert rl.remaining() == 0


class TestRateLimiterResetBehavior:
    """Window reset after expiry."""

    def test_window_fully_resets_after_expiry(self):
        """After the window expires, all calls are available again."""
        rl = RateLimiter(max_calls=2, period_seconds=1)
        rl.acquire()
        rl.acquire()
        assert rl.remaining() == 0
        time.sleep(1.1)
        assert rl.remaining() == 2
        assert rl.acquire() is True

    def test_retry_after_decreases_over_time(self):
        """retry_after() decreases as time passes."""
        rl = RateLimiter(max_calls=1, period_seconds=2)
        rl.acquire()
        first_retry = rl.retry_after()
        time.sleep(0.5)
        second_retry = rl.retry_after()
        assert second_retry < first_retry


class TestAmountRateLimiterEdgeCases:
    """Boundary conditions for AmountRateLimiter."""

    def test_exactly_at_limit(self):
        """An amount that exactly fills the budget is accepted."""
        rl = AmountRateLimiter(max_amount=100.0, period_seconds=60)
        assert rl.acquire(100.0) is True
        assert rl.remaining() == 0.0

    def test_one_over_limit(self):
        """An amount that exceeds the budget by the smallest margin is rejected."""
        rl = AmountRateLimiter(max_amount=100.0, period_seconds=60)
        rl.acquire(100.0)
        assert rl.acquire(0.01) is False

    def test_budget_replenishes_after_window(self):
        """After window expiry the full budget is available again."""
        rl = AmountRateLimiter(max_amount=100.0, period_seconds=1)
        rl.acquire(100.0)
        assert rl.remaining() == 0.0
        time.sleep(1.1)
        assert rl.remaining() == 100.0
