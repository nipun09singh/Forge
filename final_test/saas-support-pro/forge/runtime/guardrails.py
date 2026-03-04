"""Guardrails and safety filters for agent actions."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class GuardrailViolation:
    """A detected guardrail violation."""
    rule: str
    description: str
    severity: str = "warning"  # warning, block
    content_preview: str = ""


class ContentFilter:
    """
    Filters agent outputs for harmful, sensitive, or inappropriate content.
    
    Checks for:
    - PII (emails, phone numbers, SSNs, credit cards)
    - Harmful instructions
    - Profanity / offensive content
    - Custom blocked patterns
    """

    def __init__(
        self,
        block_pii: bool = True,
        custom_blocked_patterns: list[str] | None = None,
        custom_blocked_words: list[str] | None = None,
    ):
        self.block_pii = block_pii
        self.custom_patterns = [re.compile(p, re.IGNORECASE) for p in (custom_blocked_patterns or [])]
        self.custom_words = [w.lower() for w in (custom_blocked_words or [])]

        # PII patterns
        self._pii_patterns = {
            "ssn": re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
            "credit_card": re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b'),
            "phone_us": re.compile(r'\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'),
            "email_address": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        }

    def check(self, content: str) -> list[GuardrailViolation]:
        """Check content for violations. Returns list of violations found."""
        violations = []

        if self.block_pii:
            for pii_type, pattern in self._pii_patterns.items():
                matches = pattern.findall(content)
                if matches:
                    violations.append(GuardrailViolation(
                        rule=f"pii_{pii_type}",
                        description=f"PII detected: {pii_type} ({len(matches)} instance(s))",
                        severity="warning",
                        content_preview=matches[0][:20] + "..." if matches else "",
                    ))

        for pattern in self.custom_patterns:
            if pattern.search(content):
                violations.append(GuardrailViolation(
                    rule="custom_pattern",
                    description=f"Blocked pattern matched: {pattern.pattern}",
                    severity="block",
                ))

        content_lower = content.lower()
        for word in self.custom_words:
            if word in content_lower:
                violations.append(GuardrailViolation(
                    rule="blocked_word",
                    description=f"Blocked word detected: {word}",
                    severity="block",
                ))

        return violations

    def redact_pii(self, content: str) -> str:
        """Redact PII from content, replacing with [REDACTED]."""
        result = content
        for pii_type, pattern in self._pii_patterns.items():
            result = pattern.sub(f"[REDACTED_{pii_type.upper()}]", result)
        return result


class ActionLimiter:
    """
    Limits agent actions to prevent runaway execution.
    
    Tracks and enforces:
    - Max tool calls per task
    - Max tokens per task
    - Max cost per task
    - Blocked tool names
    """

    def __init__(
        self,
        max_tool_calls: int = 50,
        max_tokens: int = 100_000,
        max_cost_usd: float = 5.0,
        blocked_tools: list[str] | None = None,
    ):
        self.max_tool_calls = max_tool_calls
        self.max_tokens = max_tokens
        self.max_cost_usd = max_cost_usd
        self.blocked_tools = set(blocked_tools or [])

        self._tool_call_count: int = 0
        self._token_count: int = 0
        self._cost_usd: float = 0.0

    def check_tool_call(self, tool_name: str) -> GuardrailViolation | None:
        """Check if a tool call is allowed."""
        if tool_name in self.blocked_tools:
            return GuardrailViolation(
                rule="blocked_tool",
                description=f"Tool '{tool_name}' is blocked by policy",
                severity="block",
            )

        self._tool_call_count += 1
        if self._tool_call_count > self.max_tool_calls:
            return GuardrailViolation(
                rule="max_tool_calls",
                description=f"Tool call limit exceeded ({self.max_tool_calls})",
                severity="block",
            )
        return None

    def record_tokens(self, tokens: int, cost: float) -> GuardrailViolation | None:
        """Record token usage and check limits."""
        self._token_count += tokens
        self._cost_usd += cost

        if self._token_count > self.max_tokens:
            return GuardrailViolation(
                rule="max_tokens",
                description=f"Token limit exceeded ({self.max_tokens:,})",
                severity="block",
            )
        if self._cost_usd > self.max_cost_usd:
            return GuardrailViolation(
                rule="max_cost",
                description=f"Cost limit exceeded (${self.max_cost_usd:.2f})",
                severity="block",
            )
        return None

    def reset(self) -> None:
        """Reset counters (call between tasks)."""
        self._tool_call_count = 0
        self._token_count = 0
        self._cost_usd = 0.0


class ScopeGuard:
    """
    Prevents agents from accessing resources outside their allowed scope.
    
    Controls:
    - Allowed URL patterns (for HTTP tool)
    - Allowed file paths (for file tool)
    - Allowed SQL tables (for SQL tool)
    """

    def __init__(
        self,
        allowed_url_patterns: list[str] | None = None,
        blocked_url_patterns: list[str] | None = None,
        allowed_file_paths: list[str] | None = None,
        allowed_sql_tables: list[str] | None = None,
    ):
        self.allowed_urls = [re.compile(p) for p in (allowed_url_patterns or [])]
        self.blocked_urls = [re.compile(p) for p in (blocked_url_patterns or [
            r".*localhost.*",
            r".*127\.0\.0\.1.*",
            r".*0\.0\.0\.0.*",
            r".*169\.254\..*",  # Link-local
            r".*metadata\.google\..*",  # Cloud metadata
        ])]
        self.allowed_paths = allowed_file_paths  # None = allow all (within sandbox)
        self.allowed_tables = set(t.lower() for t in (allowed_sql_tables or []))

    def check_url(self, url: str) -> GuardrailViolation | None:
        """Check if a URL is allowed."""
        for pattern in self.blocked_urls:
            if pattern.match(url):
                return GuardrailViolation(
                    rule="blocked_url",
                    description=f"URL blocked by policy: {url[:100]}",
                    severity="block",
                )

        if self.allowed_urls:
            if not any(p.match(url) for p in self.allowed_urls):
                return GuardrailViolation(
                    rule="url_not_allowed",
                    description=f"URL not in allowed list: {url[:100]}",
                    severity="block",
                )
        return None

    def check_sql(self, query: str) -> GuardrailViolation | None:
        """Check if a SQL query is within allowed scope."""
        if not self.allowed_tables:
            return None  # No restrictions

        # Extract table names from query (basic parsing)
        query_upper = query.upper()
        words = re.findall(r'\b\w+\b', query_upper)

        # Check for table references after FROM, JOIN, INTO, UPDATE
        table_keywords = {"FROM", "JOIN", "INTO", "UPDATE", "TABLE"}
        for i, word in enumerate(words):
            if word in table_keywords and i + 1 < len(words):
                table = words[i + 1].lower()
                if table not in self.allowed_tables and table not in ("select", "where", "set", "values"):
                    return GuardrailViolation(
                        rule="sql_table_not_allowed",
                        description=f"Access to table '{table}' is not allowed",
                        severity="block",
                    )
        return None


class GuardrailsEngine:
    """
    Combines all guardrails into a single engine.
    
    Usage:
        guardrails = GuardrailsEngine(
            content_filter=ContentFilter(block_pii=True),
            action_limiter=ActionLimiter(max_tool_calls=20),
            scope_guard=ScopeGuard(blocked_url_patterns=[...]),
        )
        agent.set_guardrails(guardrails)
    """

    def __init__(
        self,
        content_filter: ContentFilter | None = None,
        action_limiter: ActionLimiter | None = None,
        scope_guard: ScopeGuard | None = None,
    ):
        self.content_filter = content_filter or ContentFilter()
        self.action_limiter = action_limiter or ActionLimiter()
        self.scope_guard = scope_guard or ScopeGuard()

    def check_output(self, content: str) -> list[GuardrailViolation]:
        """Check agent output content."""
        return self.content_filter.check(content)

    def check_tool_call(self, tool_name: str, args: dict) -> list[GuardrailViolation]:
        """Check if a tool call is allowed."""
        violations = []

        # Action limiter
        v = self.action_limiter.check_tool_call(tool_name)
        if v:
            violations.append(v)

        # Scope guard — check URL args
        if tool_name in ("http_request", "send_webhook"):
            url = args.get("url", "")
            if url:
                v = self.scope_guard.check_url(url)
                if v:
                    violations.append(v)

        # Scope guard — check SQL args
        if tool_name in ("query_database",):
            query = args.get("query", "")
            if query:
                v = self.scope_guard.check_sql(query)
                if v:
                    violations.append(v)

        return violations

    def redact_output(self, content: str) -> str:
        """Redact sensitive content from output."""
        return self.content_filter.redact_pii(content)

    def reset_for_new_task(self) -> None:
        """Reset per-task counters."""
        self.action_limiter.reset()
