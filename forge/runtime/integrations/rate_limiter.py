"""Rate limiter for external integrations — prevents abuse via sliding window throttling.

Each integration has sensible defaults configurable via environment variables.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any


class RateLimitExceeded(Exception):
    """Raised when a rate limit is exceeded."""

    def __init__(self, key: str, limit: int, period_seconds: int, retry_after: float):
        self.key = key
        self.limit = limit
        self.period_seconds = period_seconds
        self.retry_after = retry_after
        super().__init__(
            f"Rate limit exceeded for '{key}': {limit} calls per {period_seconds}s. "
            f"Retry after {retry_after:.1f}s."
        )


class RateLimiter:
    """Sliding-window rate limiter (thread-safe).

    Tracks timestamps of calls within a rolling window and rejects
    calls that exceed the configured maximum.
    """

    def __init__(self, max_calls: int, period_seconds: int):
        if max_calls <= 0 or period_seconds <= 0:
            raise ValueError("max_calls and period_seconds must be positive")
        self.max_calls = max_calls
        self.period_seconds = period_seconds
        self._calls: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> list[float]:
        """Remove expired timestamps and return the remaining ones."""
        cutoff = now - self.period_seconds
        entries = self._calls.get(key, [])
        pruned = [t for t in entries if t > cutoff]
        self._calls[key] = pruned
        return pruned

    def acquire(self, key: str = "default") -> bool:
        """Returns True if the call is allowed, False if rate-limited."""
        now = time.monotonic()
        with self._lock:
            recent = self._prune(key, now)
            if len(recent) >= self.max_calls:
                return False
            recent.append(now)
            return True

    def remaining(self, key: str = "default") -> int:
        """Return the number of calls remaining in the current window."""
        now = time.monotonic()
        with self._lock:
            recent = self._prune(key, now)
            return max(0, self.max_calls - len(recent))

    def retry_after(self, key: str = "default") -> float:
        """Seconds until the next call would be allowed (0 if already allowed)."""
        now = time.monotonic()
        with self._lock:
            recent = self._prune(key, now)
            if len(recent) < self.max_calls:
                return 0.0
            oldest = recent[0]
            return max(0.0, oldest + self.period_seconds - now)

    def check_or_raise(self, key: str = "default") -> None:
        """Raises RateLimitExceeded if the call is not allowed."""
        if not self.acquire(key):
            raise RateLimitExceeded(
                key=key,
                limit=self.max_calls,
                period_seconds=self.period_seconds,
                retry_after=self.retry_after(key),
            )


class AmountRateLimiter:
    """Tracks cumulative amounts within a sliding window (e.g. dollar totals)."""

    def __init__(self, max_amount: float, period_seconds: int):
        if max_amount <= 0 or period_seconds <= 0:
            raise ValueError("max_amount and period_seconds must be positive")
        self.max_amount = max_amount
        self.period_seconds = period_seconds
        self._entries: dict[str, list[tuple[float, float]]] = {}  # key -> [(timestamp, amount)]
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> list[tuple[float, float]]:
        cutoff = now - self.period_seconds
        entries = self._entries.get(key, [])
        pruned = [(t, a) for t, a in entries if t > cutoff]
        self._entries[key] = pruned
        return pruned

    def acquire(self, amount: float, key: str = "default") -> bool:
        """Returns True if adding this amount stays within limits."""
        now = time.monotonic()
        with self._lock:
            recent = self._prune(key, now)
            total = sum(a for _, a in recent)
            if total + amount > self.max_amount:
                return False
            recent.append((now, amount))
            return True

    def remaining(self, key: str = "default") -> float:
        """Return the remaining amount budget in the current window."""
        now = time.monotonic()
        with self._lock:
            recent = self._prune(key, now)
            total = sum(a for _, a in recent)
            return max(0.0, self.max_amount - total)

    def check_or_raise(self, amount: float, key: str = "default") -> None:
        """Raises RateLimitExceeded if the amount would exceed the limit."""
        if not self.acquire(amount, key):
            raise RateLimitExceeded(
                key=key,
                limit=int(self.max_amount),
                period_seconds=self.period_seconds,
                retry_after=0.0,
            )


def _env_int(name: str, default: int) -> int:
    """Read an integer from an environment variable with a fallback."""
    val = os.environ.get(name)
    if val is not None:
        try:
            return int(val)
        except ValueError:
            pass
    return default


# ---------------------------------------------------------------------------
# Shared limiter instances — one per integration, lazily initialized
# ---------------------------------------------------------------------------
_instances: dict[str, RateLimiter | AmountRateLimiter] = {}
_init_lock = threading.Lock()


def get_email_limiter() -> RateLimiter:
    """20 emails per hour (default), configurable via RATE_LIMIT_EMAIL_PER_HOUR."""
    key = "email"
    if key not in _instances:
        with _init_lock:
            if key not in _instances:
                _instances[key] = RateLimiter(
                    max_calls=_env_int("RATE_LIMIT_EMAIL_PER_HOUR", 20),
                    period_seconds=3600,
                )
    return _instances[key]  # type: ignore[return-value]


def get_sms_limiter() -> RateLimiter:
    """10 SMS per hour (default), configurable via RATE_LIMIT_SMS_PER_HOUR."""
    key = "sms"
    if key not in _instances:
        with _init_lock:
            if key not in _instances:
                _instances[key] = RateLimiter(
                    max_calls=_env_int("RATE_LIMIT_SMS_PER_HOUR", 10),
                    period_seconds=3600,
                )
    return _instances[key]  # type: ignore[return-value]


def get_stripe_limiter() -> RateLimiter:
    """20 charges per hour (default), configurable via RATE_LIMIT_STRIPE_PER_HOUR."""
    key = "stripe"
    if key not in _instances:
        with _init_lock:
            if key not in _instances:
                _instances[key] = RateLimiter(
                    max_calls=_env_int("RATE_LIMIT_STRIPE_PER_HOUR", 20),
                    period_seconds=3600,
                )
    return _instances[key]  # type: ignore[return-value]


def get_stripe_amount_limiter() -> AmountRateLimiter:
    """$500 total per hour (default), configurable via RATE_LIMIT_STRIPE_AMOUNT_PER_HOUR (in cents)."""
    key = "stripe_amount"
    if key not in _instances:
        with _init_lock:
            if key not in _instances:
                _instances[key] = AmountRateLimiter(
                    max_amount=_env_int("RATE_LIMIT_STRIPE_AMOUNT_PER_HOUR", 50000),
                    period_seconds=3600,
                )
    return _instances[key]  # type: ignore[return-value]


def get_http_limiter() -> RateLimiter:
    """100 requests per minute (default), configurable via RATE_LIMIT_HTTP_PER_MINUTE."""
    key = "http"
    if key not in _instances:
        with _init_lock:
            if key not in _instances:
                _instances[key] = RateLimiter(
                    max_calls=_env_int("RATE_LIMIT_HTTP_PER_MINUTE", 100),
                    period_seconds=60,
                )
    return _instances[key]  # type: ignore[return-value]


def get_webhook_limiter() -> RateLimiter:
    """30 calls per minute (default), configurable via RATE_LIMIT_WEBHOOK_PER_MINUTE."""
    key = "webhook"
    if key not in _instances:
        with _init_lock:
            if key not in _instances:
                _instances[key] = RateLimiter(
                    max_calls=_env_int("RATE_LIMIT_WEBHOOK_PER_MINUTE", 30),
                    period_seconds=60,
                )
    return _instances[key]  # type: ignore[return-value]


def rate_limit_error(tool_name: str, limiter: RateLimiter, key: str = "default") -> str:
    """Build a JSON error response for a rate-limited call."""
    return json.dumps({
        "success": False,
        "error": "rate_limit_exceeded",
        "message": (
            f"{tool_name} rate limit exceeded: max {limiter.max_calls} calls "
            f"per {limiter.period_seconds}s. "
            f"Remaining: {limiter.remaining(key)}. "
            f"Retry after {limiter.retry_after(key):.1f}s."
        ),
    })


def amount_limit_error(tool_name: str, limiter: AmountRateLimiter, amount: float, key: str = "default") -> str:
    """Build a JSON error response for an amount-based rate limit."""
    return json.dumps({
        "success": False,
        "error": "rate_limit_exceeded",
        "message": (
            f"{tool_name} amount limit exceeded: max {limiter.max_amount:.0f} cents "
            f"per {limiter.period_seconds}s. "
            f"Requested: {amount:.0f}. Remaining budget: {limiter.remaining(key):.0f}."
        ),
    })


def reset_all_limiters() -> None:
    """Reset all limiter instances — for testing only."""
    with _init_lock:
        _instances.clear()
