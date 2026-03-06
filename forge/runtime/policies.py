"""Configurable security policies for Forge agents.

``SecurityPolicy`` centralises every security-related constant that was
previously hard-coded across guardrails, command_tool, and rate_limiter.
All current defaults are preserved — this module only makes them
**overridable** per-agent, per-domain, or per-environment.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults — identical to the values that were previously hard-coded.
# ---------------------------------------------------------------------------

_DEFAULT_SQL_ALLOWED_TYPES: frozenset[str] = frozenset({
    "SELECT", "INSERT", "UPDATE", "DELETE", "WITH",
})

_DEFAULT_SQL_BLOCKED_STATEMENTS: frozenset[str] = frozenset({
    "DROP", "ALTER", "CREATE", "TRUNCATE", "EXEC", "EXECUTE",
    "GRANT", "REVOKE", "ATTACH", "DETACH", "PRAGMA", "VACUUM",
    "RENAME", "REPLACE",
})

_DEFAULT_SQL_DANGEROUS_FUNCTIONS: frozenset[str] = frozenset({
    "LOAD_FILE", "INTO OUTFILE", "INTO DUMPFILE",
    "BENCHMARK", "SLEEP", "WAITFOR",
    "PG_SLEEP", "DBMS_PIPE", "UTL_HTTP",
    "XP_CMDSHELL", "SP_EXECUTESQL",
})

_DEFAULT_SHELL_ALLOWED_COMMANDS: frozenset[str] = frozenset({
    # Python
    "python", "python3", "python3.11", "python3.12", "python3.13", "py",
    "pip", "pip3", "pipx", "uv", "poetry", "conda",
    "pytest", "mypy", "ruff", "black", "isort", "flake8", "pylint", "pyright",
    # Node / JS
    "node", "npm", "npx", "yarn", "pnpm", "bun", "deno", "tsc", "tsx",
    "eslint", "prettier", "jest", "vitest", "mocha",
    # Build tools
    "make", "cmake", "cargo", "go", "rustc", "gcc", "g++", "javac", "java",
    "dotnet", "msbuild",
    # Version control
    "git", "gh", "svn",
    # File / text utilities
    "ls", "dir", "cat", "head", "tail", "grep", "rg", "find", "fd",
    "echo", "printf", "wc", "sort", "uniq", "cut", "awk", "sed", "tr",
    "diff", "patch", "tee", "xargs",
    # File management
    "mkdir", "cp", "mv", "touch", "ln", "rm", "rmdir",
    "xcopy", "copy", "move", "del", "ren", "type",
    # Network
    "curl", "wget", "ssh", "scp", "rsync",
    # Archive
    "tar", "zip", "unzip", "gzip", "gunzip",
    # System info (safe subset)
    "whoami", "hostname", "uname", "which", "where", "pwd",
    "ps", "top", "htop", "df", "du", "free", "uptime", "date",
    # Docker
    "docker", "docker-compose", "podman",
    # Misc dev tools
    "jq", "yq", "tree", "less", "more", "file", "stat", "realpath",
    "chmod", "chown", "chgrp",
})

_DEFAULT_SHELL_BLOCKED_PATTERNS: list[str] = [
    "rm -rf /",
    "rm -rf /*",
    "del /s /q c:\\",
    "format c:",
    "mkfs",
    "dd if=",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    ":(){:|:&};:",        # fork bomb
    "curl | bash",
    "curl | sh",
    "wget | bash",
    "wget | sh",
    "> /dev/sda",
    "chmod -r 777 /",
    "mv / ",
]


def _env_int(name: str, default: int) -> int:
    """Read an integer from an environment variable with a fallback."""
    val = os.environ.get(name)
    if val is not None:
        try:
            return int(val)
        except ValueError:
            pass
    return default


def _env_set(name: str, default: frozenset[str]) -> frozenset[str]:
    """Read a comma-separated set from an environment variable."""
    val = os.environ.get(name)
    if val is not None:
        return frozenset(item.strip() for item in val.split(",") if item.strip())
    return default


def _env_list(name: str, default: list[str]) -> list[str]:
    """Read a comma-separated list from an environment variable."""
    val = os.environ.get(name)
    if val is not None:
        return [item.strip() for item in val.split(",") if item.strip()]
    return list(default)


@dataclass(frozen=True)
class SecurityPolicy:
    """Unified, immutable security policy for a Forge agency or agent.

    Every field has the same default that was previously hard-coded.
    Override via constructor kwargs, ``from_env()``, or ``from_file()``.
    """

    # --- SQL ---
    sql_allowed_types: frozenset[str] = field(
        default_factory=lambda: _DEFAULT_SQL_ALLOWED_TYPES,
    )
    sql_blocked_statements: frozenset[str] = field(
        default_factory=lambda: _DEFAULT_SQL_BLOCKED_STATEMENTS,
    )
    sql_dangerous_functions: frozenset[str] = field(
        default_factory=lambda: _DEFAULT_SQL_DANGEROUS_FUNCTIONS,
    )

    # --- Shell / Command ---
    shell_allowed_commands: frozenset[str] = field(
        default_factory=lambda: _DEFAULT_SHELL_ALLOWED_COMMANDS,
    )
    shell_blocked_patterns: list[str] = field(
        default_factory=lambda: list(_DEFAULT_SHELL_BLOCKED_PATTERNS),
    )

    # --- Rate limits ---
    rate_limit_email_per_hour: int = 20
    rate_limit_sms_per_hour: int = 10
    rate_limit_stripe_per_hour: int = 20
    rate_limit_stripe_amount_per_hour: int = 50_000  # cents
    rate_limit_http_per_minute: int = 100
    rate_limit_webhook_per_minute: int = 30

    # --- Action limits (per-task guardrails) ---
    max_tool_calls: int = 50
    max_tokens: int = 100_000
    max_cost_usd: float = 5.0

    # -----------------------------------------------------------------------
    # Factory classmethods
    # -----------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> SecurityPolicy:
        """Create a policy populated from environment variables.

        Recognised variables (all optional — unset means use default):

        * ``FORGE_SQL_ALLOWED_TYPES`` — comma-separated (e.g. "SELECT,INSERT")
        * ``FORGE_SQL_BLOCKED_STATEMENTS`` — comma-separated
        * ``FORGE_SQL_DANGEROUS_FUNCTIONS`` — comma-separated
        * ``FORGE_SHELL_ALLOWED_COMMANDS`` — comma-separated
        * ``FORGE_SHELL_BLOCKED_PATTERNS`` — comma-separated
        * ``RATE_LIMIT_EMAIL_PER_HOUR``
        * ``RATE_LIMIT_SMS_PER_HOUR``
        * ``RATE_LIMIT_STRIPE_PER_HOUR``
        * ``RATE_LIMIT_STRIPE_AMOUNT_PER_HOUR``
        * ``RATE_LIMIT_HTTP_PER_MINUTE``
        * ``RATE_LIMIT_WEBHOOK_PER_MINUTE``
        * ``FORGE_MAX_TOOL_CALLS``
        * ``FORGE_MAX_TOKENS_PER_TASK``
        * ``FORGE_MAX_COST_PER_TASK``
        """
        return cls(
            sql_allowed_types=_env_set(
                "FORGE_SQL_ALLOWED_TYPES", _DEFAULT_SQL_ALLOWED_TYPES,
            ),
            sql_blocked_statements=_env_set(
                "FORGE_SQL_BLOCKED_STATEMENTS", _DEFAULT_SQL_BLOCKED_STATEMENTS,
            ),
            sql_dangerous_functions=_env_set(
                "FORGE_SQL_DANGEROUS_FUNCTIONS", _DEFAULT_SQL_DANGEROUS_FUNCTIONS,
            ),
            shell_allowed_commands=_env_set(
                "FORGE_SHELL_ALLOWED_COMMANDS", _DEFAULT_SHELL_ALLOWED_COMMANDS,
            ),
            shell_blocked_patterns=_env_list(
                "FORGE_SHELL_BLOCKED_PATTERNS", _DEFAULT_SHELL_BLOCKED_PATTERNS,
            ),
            rate_limit_email_per_hour=_env_int("RATE_LIMIT_EMAIL_PER_HOUR", 20),
            rate_limit_sms_per_hour=_env_int("RATE_LIMIT_SMS_PER_HOUR", 10),
            rate_limit_stripe_per_hour=_env_int("RATE_LIMIT_STRIPE_PER_HOUR", 20),
            rate_limit_stripe_amount_per_hour=_env_int("RATE_LIMIT_STRIPE_AMOUNT_PER_HOUR", 50_000),
            rate_limit_http_per_minute=_env_int("RATE_LIMIT_HTTP_PER_MINUTE", 100),
            rate_limit_webhook_per_minute=_env_int("RATE_LIMIT_WEBHOOK_PER_MINUTE", 30),
            max_tool_calls=_env_int("FORGE_MAX_TOOL_CALLS", 50),
            max_tokens=_env_int("FORGE_MAX_TOKENS_PER_TASK", 100_000),
            max_cost_usd=float(os.getenv("FORGE_MAX_COST_PER_TASK", "5.0")),
        )

    @classmethod
    def from_file(cls, path: str | Path) -> SecurityPolicy:
        """Load a policy from a JSON or YAML file.

        The file should contain a flat or nested object whose keys match the
        field names of this dataclass.  Unknown keys are silently ignored.

        Supports ``.json``, ``.yaml``, and ``.yml`` extensions.
        """
        p = Path(path)
        text = p.read_text(encoding="utf-8")

        if p.suffix in (".yaml", ".yml"):
            try:
                import yaml  # type: ignore[import-untyped]
                data: dict[str, Any] = yaml.safe_load(text) or {}
            except ImportError:
                raise ImportError(
                    "PyYAML is required for YAML policy files. "
                    "Install it with: pip install pyyaml"
                )
        else:
            data = json.loads(text)

        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> SecurityPolicy:
        """Build a SecurityPolicy from a plain dictionary."""
        kwargs: dict[str, Any] = {}

        # Sets — accept lists or comma-separated strings
        _set_fields = {
            "sql_allowed_types",
            "sql_blocked_statements",
            "sql_dangerous_functions",
            "shell_allowed_commands",
        }
        for key in _set_fields:
            if key in data:
                val = data[key]
                if isinstance(val, str):
                    val = [v.strip() for v in val.split(",") if v.strip()]
                kwargs[key] = frozenset(val)

        # List
        if "shell_blocked_patterns" in data:
            val = data["shell_blocked_patterns"]
            if isinstance(val, str):
                val = [v.strip() for v in val.split(",") if v.strip()]
            kwargs["shell_blocked_patterns"] = list(val)

        # Numeric fields
        _int_fields = {
            "rate_limit_email_per_hour",
            "rate_limit_sms_per_hour",
            "rate_limit_stripe_per_hour",
            "rate_limit_stripe_amount_per_hour",
            "rate_limit_http_per_minute",
            "rate_limit_webhook_per_minute",
            "max_tool_calls",
            "max_tokens",
        }
        for key in _int_fields:
            if key in data:
                kwargs[key] = int(data[key])

        if "max_cost_usd" in data:
            kwargs["max_cost_usd"] = float(data["max_cost_usd"])

        return cls(**kwargs)

    # -----------------------------------------------------------------------
    # Utilities
    # -----------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise the policy to a JSON-compatible dictionary."""
        return {
            "sql_allowed_types": sorted(self.sql_allowed_types),
            "sql_blocked_statements": sorted(self.sql_blocked_statements),
            "sql_dangerous_functions": sorted(self.sql_dangerous_functions),
            "shell_allowed_commands": sorted(self.shell_allowed_commands),
            "shell_blocked_patterns": list(self.shell_blocked_patterns),
            "rate_limit_email_per_hour": self.rate_limit_email_per_hour,
            "rate_limit_sms_per_hour": self.rate_limit_sms_per_hour,
            "rate_limit_stripe_per_hour": self.rate_limit_stripe_per_hour,
            "rate_limit_stripe_amount_per_hour": self.rate_limit_stripe_amount_per_hour,
            "rate_limit_http_per_minute": self.rate_limit_http_per_minute,
            "rate_limit_webhook_per_minute": self.rate_limit_webhook_per_minute,
            "max_tool_calls": self.max_tool_calls,
            "max_tokens": self.max_tokens,
            "max_cost_usd": self.max_cost_usd,
        }
