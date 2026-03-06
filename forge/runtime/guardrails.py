"""Guardrails and safety filters for agent actions."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from forge.runtime.policies import SecurityPolicy

logger = logging.getLogger(__name__)


def luhn_check(number: str) -> bool:
    """Validate a number string using the Luhn algorithm (credit card checksum)."""
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


# ---------------------------------------------------------------------------
# PII pattern categories — each maps a category name to {label: regex}.
# Categories can be individually enabled/disabled in ContentFilter.
# ---------------------------------------------------------------------------
PII_CATEGORIES: dict[str, dict[str, re.Pattern]] = {
    "financial": {
        "credit_card": re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b'),
        "iban": re.compile(r'\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b'),
    },
    "identity": {
        "ssn": re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
        "passport": re.compile(
            r'\b(?:'
            r'[A-Z]?\d{9}'           # US (9 digits) / generic 9-digit
            r'|[A-Z]{2}\d{7}'        # UK / 2-letter prefix + 7 digits
            r'|[A-Z]\d{8}'           # CA / 1-letter + 8 digits
            r')\b'
        ),
    },
    "contact": {
        "phone_us": re.compile(
            r'\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'
        ),
        "phone_intl": re.compile(
            r'\+(?:[2-9]\d{0,2})[-.\s]?\d[\d\-.\s]{6,14}\d\b'
        ),
        "email_address": re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
        ),
    },
    "network": {
        "ipv4_address": re.compile(
            r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}'
            r'(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b'
        ),
        "ipv6_address": re.compile(
            r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b'
            r'|'
            r'\b(?:[0-9a-fA-F]{1,4}:){1,7}:\b'
            r'|'
            r'\b::(?:[0-9a-fA-F]{1,4}:){0,5}[0-9a-fA-F]{1,4}\b'
        ),
        "url_with_credentials": re.compile(
            r'https?://[^:]+:[^@]+@', re.IGNORECASE
        ),
    },
    "secrets": {
        "aws_access_key": re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
        "aws_secret_key": re.compile(
            r'(?i)(?:aws_secret_access_key|secret_key)\s*[:=]\s*[A-Za-z0-9/+=]{40}'
        ),
        "api_key_prefixed": re.compile(
            r'\b(?:sk-[A-Za-z0-9]{20,}|pk_(?:live|test)_[A-Za-z0-9]{20,})\b'
        ),
        "bearer_token": re.compile(
            r'(?i)bearer\s+[A-Za-z0-9\-._~+/]{20,}=*'
        ),
        "generic_hex_secret": re.compile(
            r'(?i)(?:api_key|apikey|secret|token|password)\s*[:=]\s*["\']?[A-Fa-f0-9]{32,}["\']?'
        ),
    },
}

# Flat set of all category names for quick validation
ALL_PII_CATEGORIES: frozenset[str] = frozenset(PII_CATEGORIES)

# Patterns that need extra validation beyond regex
_NEEDS_LUHN = {"credit_card"}


class SqlSanitizer:
    """
    Sanitizes and validates SQL queries to prevent injection and abuse.

    Provides layered defenses:
    - Comment stripping (line and block comments)
    - Multi-statement detection
    - Query type whitelisting
    - Dangerous function blocking
    - String-concatenation warnings

    All rule-sets can be overridden via a ``SecurityPolicy`` or directly
    through constructor kwargs.
    """

    # Class-level defaults (used when no overrides are provided)
    ALLOWED_QUERY_TYPES = {"SELECT", "INSERT", "UPDATE", "DELETE", "WITH"}

    BLOCKED_STATEMENTS = {
        "DROP", "ALTER", "CREATE", "TRUNCATE", "EXEC", "EXECUTE",
        "GRANT", "REVOKE", "ATTACH", "DETACH", "PRAGMA", "VACUUM",
        "RENAME", "REPLACE",
    }

    DANGEROUS_FUNCTIONS = {
        "LOAD_FILE", "INTO OUTFILE", "INTO DUMPFILE",
        "BENCHMARK", "SLEEP", "WAITFOR",
        "PG_SLEEP", "DBMS_PIPE", "UTL_HTTP",
        "XP_CMDSHELL", "SP_EXECUTESQL",
    }

    def __init__(
        self,
        *,
        policy: "SecurityPolicy | None" = None,
        allowed_query_types: set[str] | None = None,
        blocked_statements: set[str] | None = None,
        dangerous_functions: set[str] | None = None,
    ) -> None:
        if policy is not None:
            self.allowed_query_types = set(policy.sql_allowed_types)
            self.blocked_statements = set(policy.sql_blocked_statements)
            self.dangerous_functions = set(policy.sql_dangerous_functions)
        else:
            self.allowed_query_types = set(allowed_query_types or self.ALLOWED_QUERY_TYPES)
            self.blocked_statements = set(blocked_statements or self.BLOCKED_STATEMENTS)
            self.dangerous_functions = set(dangerous_functions or self.DANGEROUS_FUNCTIONS)

    # Pattern for SQL block comments (/* ... */), including nested
    _BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
    # Pattern for SQL line comments (-- to end-of-line)
    _LINE_COMMENT_RE = re.compile(r"--[^\r\n]*")
    # Pattern for string literals (single-quoted), handling escaped quotes
    _STRING_LITERAL_RE = re.compile(r"'(?:[^'\\]|\\.)*'")

    def sanitize(self, query: str) -> str:
        """Strip comments and normalize whitespace. Returns cleaned query."""
        cleaned = self._BLOCK_COMMENT_RE.sub(" ", query)
        cleaned = self._LINE_COMMENT_RE.sub(" ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _strip_string_literals(self, query: str) -> str:
        """Replace string literals with a placeholder to avoid false positives."""
        return self._STRING_LITERAL_RE.sub("'__LITERAL__'", query)

    def validate(self, query: str) -> GuardrailViolation | None:
        """
        Validate a query against security rules. Returns a violation or None.

        Call sanitize() first; this method expects a comment-free query.
        """
        if ";" in query:
            return GuardrailViolation(
                rule="sql_multi_statement",
                description="Multi-statement queries are not allowed (';' detected)",
                severity="block",
            )

        # Work on a copy with string literals masked so keywords inside
        # literal values don't trigger false positives.
        query_for_analysis = self._strip_string_literals(query)
        query_upper = query_for_analysis.upper()

        # --- query type whitelist ---
        first_keyword = re.match(r"\s*(\w+)", query_upper)
        if first_keyword:
            stmt_type = first_keyword.group(1)
            if stmt_type in self.blocked_statements:
                return GuardrailViolation(
                    rule="sql_blocked_statement",
                    description=f"Statement type '{stmt_type}' is not allowed",
                    severity="block",
                )
            if stmt_type not in self.allowed_query_types:
                return GuardrailViolation(
                    rule="sql_disallowed_query_type",
                    description=f"Query type '{stmt_type}' is not in the allowed list",
                    severity="block",
                )

        # --- dangerous functions ---
        for func in self.dangerous_functions:
            pattern = re.compile(r"\b" + func.replace(" ", r"\s+") + r"\b", re.IGNORECASE)
            if pattern.search(query_for_analysis):
                return GuardrailViolation(
                    rule="sql_dangerous_function",
                    description=f"Dangerous SQL function detected: {func}",
                    severity="block",
                )

        return None

    def is_parameterized(self, query: str) -> GuardrailViolation | None:
        """
        Warn if the query looks like it uses string concatenation/interpolation
        instead of parameter placeholders.

        Heuristics:
        - f-string / .format() patterns aren't visible in a raw string, but
          values directly embedded in WHERE clauses (without ? or %s) are suspect.
        - Presence of obvious tautologies like ``OR 1=1`` or ``OR '1'='1'``.
        """
        query_upper = query.upper()

        # Detect common injection tautology patterns
        tautology_patterns = [
            re.compile(r"OR\s+1\s*=\s*1", re.IGNORECASE),
            re.compile(r"OR\s+'[^']*'\s*=\s*'[^']*'", re.IGNORECASE),
            re.compile(r"OR\s+\"[^\"]*\"\s*=\s*\"[^\"]*\"", re.IGNORECASE),
            re.compile(r"OR\s+\d+\s*=\s*\d+", re.IGNORECASE),
        ]
        for pat in tautology_patterns:
            if pat.search(query):
                return GuardrailViolation(
                    rule="sql_injection_pattern",
                    description="Possible SQL injection pattern detected (tautology)",
                    severity="warning",
                )

        return None


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
    - PII (emails, phone numbers, SSNs, credit cards, IBANs, passports, IPs)
    - Cloud credentials and API keys
    - Harmful instructions
    - Profanity / offensive content
    - Custom blocked patterns

    PII patterns are organised into categories that can be individually
    enabled or disabled via ``enabled_pii_categories``.
    """

    def __init__(
        self,
        block_pii: bool = True,
        enabled_pii_categories: set[str] | None = None,
        custom_blocked_patterns: list[str] | None = None,
        custom_blocked_words: list[str] | None = None,
    ):
        self.block_pii = block_pii
        self.custom_patterns = [re.compile(p, re.IGNORECASE) for p in (custom_blocked_patterns or [])]
        self.custom_words = [w.lower() for w in (custom_blocked_words or [])]

        # Resolve which categories are active
        if enabled_pii_categories is not None:
            self.enabled_pii_categories: set[str] = enabled_pii_categories & ALL_PII_CATEGORIES
        else:
            self.enabled_pii_categories = set(ALL_PII_CATEGORIES)

        # Build the active pattern dict from enabled categories
        self._pii_patterns: dict[str, re.Pattern] = {}
        for cat in self.enabled_pii_categories:
            self._pii_patterns.update(PII_CATEGORIES[cat])

    def check(self, content: str) -> list[GuardrailViolation]:
        """Check content for violations. Returns list of violations found."""
        violations = []

        if self.block_pii:
            for pii_type, pattern in self._pii_patterns.items():
                matches = pattern.findall(content)
                if pii_type in _NEEDS_LUHN:
                    matches = [m for m in matches if luhn_check(m)]
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
            if pii_type in _NEEDS_LUHN:
                def _luhn_replacer(m: re.Match, label: str = pii_type) -> str:
                    return f"[REDACTED_{label.upper()}]" if luhn_check(m.group()) else m.group()
                result = pattern.sub(_luhn_replacer, result)
            else:
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
        policy: "SecurityPolicy | None" = None,
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
        self._policy = policy

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
        """Check if a SQL query is within allowed scope.

        Applies layered validation:
        1. Sanitize (strip comments, normalize whitespace)
        2. Structural validation (multi-statement, query type, dangerous funcs)
        3. Table-scope enforcement
        4. Injection-pattern warnings (promoted to blocks when table restrictions are active)
        """
        sanitizer = SqlSanitizer(policy=self._policy)
        cleaned = sanitizer.sanitize(query)

        # Structural validation
        violation = sanitizer.validate(cleaned)
        if violation:
            return violation

        # Injection pattern check
        inj_violation = sanitizer.is_parameterized(cleaned)
        if inj_violation:
            if self.allowed_tables:
                inj_violation.severity = "block"
            return inj_violation

        if not self.allowed_tables:
            return None  # No table restrictions configured

        # Table-scope enforcement on the sanitized, literal-stripped query
        analysis_query = sanitizer._strip_string_literals(cleaned).upper()
        words = re.findall(r'\b\w+\b', analysis_query)

        sql_noise = {
            "SELECT", "WHERE", "SET", "VALUES", "AND", "OR", "ON",
            "AS", "NOT", "NULL", "IN", "EXISTS", "BETWEEN", "LIKE",
            "IS", "CASE", "WHEN", "THEN", "ELSE", "END", "GROUP",
            "ORDER", "BY", "HAVING", "LIMIT", "OFFSET", "ASC", "DESC",
            "DISTINCT", "ALL", "UNION", "EXCEPT", "INTERSECT",
            "__LITERAL__",
        }
        table_keywords = {"FROM", "JOIN", "INTO", "UPDATE", "TABLE"}

        for i, word in enumerate(words):
            if word in table_keywords and i + 1 < len(words):
                table = words[i + 1].lower()
                if table not in self.allowed_tables and table.upper() not in sql_noise:
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
        policy: "SecurityPolicy | None" = None,
    ):
        self.policy = policy
        if policy is not None:
            self.content_filter = content_filter or ContentFilter()
            self.action_limiter = action_limiter or ActionLimiter(
                max_tool_calls=policy.max_tool_calls,
                max_tokens=policy.max_tokens,
                max_cost_usd=policy.max_cost_usd,
            )
            self.scope_guard = scope_guard or ScopeGuard(policy=policy)
        else:
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
