"""Role-based tool access control for Forge agents."""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Mapping from tool name to category (used by role-based defaults)
TOOL_CATEGORY_MAP: dict[str, list[str]] = {
    "run_command": ["command"],
    "read_write_file": ["file", "file_read"],
    "http_request": ["http"],
    "web_search": ["search"],
    "browse_web": ["search"],
    "query_database": ["sql"],
    "send_email": ["email", "communication"],
    "send_webhook": ["http"],
    "git_operation": ["git"],
    "send_sms": ["communication"],
    "stripe_payment": ["payment"],
    "calendar": ["calendar"],
}


def _get_tool_categories(tool_name: str) -> list[str]:
    """Return categories for a given tool name."""
    return TOOL_CATEGORY_MAP.get(tool_name, [])


@dataclass
class ToolAccessPolicy:
    """Policy engine that determines which tools an agent role may use.

    Resolution order (first match wins):
    1. Explicit ``denied_tools`` on the agent → block
    2. Explicit ``allowed_tools`` on the agent → allow only those
    3. Role-based category defaults from ``ROLE_TOOL_DEFAULTS``
    """

    # Role → list of allowed tool *categories*.  "*" means unrestricted.
    ROLE_TOOL_DEFAULTS: dict[str, list[str]] = field(default_factory=lambda: {
        "support": ["search", "http", "email", "file_read"],
        "developer": ["command", "file", "http", "search", "git", "sql"],
        "analyst": ["search", "http", "sql", "file_read"],
        "admin": ["*"],
        "default": ["search", "http", "file_read", "email"],
    })

    def _role_key(self, agent_role: str) -> str:
        """Normalise a role string to its lookup key."""
        key = agent_role.strip().lower()
        return key if key in self.ROLE_TOOL_DEFAULTS else "default"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_allowed(
        self,
        agent_role: str,
        tool_name: str,
        *,
        allowed_tools: list[str] | None = None,
        denied_tools: list[str] | None = None,
    ) -> bool:
        """Return ``True`` if *tool_name* is permitted for the given role.

        Parameters
        ----------
        agent_role:
            The agent's role string (e.g. ``"developer"``, ``"support"``).
        tool_name:
            The concrete tool name (e.g. ``"run_command"``).
        allowed_tools:
            Per-agent explicit allowlist.  If set, only these tools are
            permitted (overrides role defaults).
        denied_tools:
            Per-agent explicit denylist.  Checked first — always wins.
        """
        # 1. Explicit deny always wins
        if denied_tools and self._matches_any(tool_name, denied_tools):
            return False

        # 2. Explicit allow — if specified, only those tools are permitted
        if allowed_tools is not None:
            return self._matches_any(tool_name, allowed_tools)

        # 3. Role-based category defaults
        return self._role_allows(agent_role, tool_name)

    def allowed_tool_categories(self, agent_role: str) -> list[str]:
        """Return the category list for a role (useful for introspection)."""
        key = self._role_key(agent_role)
        return list(self.ROLE_TOOL_DEFAULTS[key])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _matches_any(self, tool_name: str, patterns: list[str]) -> bool:
        """Check if *tool_name* matches any pattern (supports fnmatch globs)."""
        for pattern in patterns:
            if fnmatch.fnmatch(tool_name, pattern):
                return True
        return False

    def _role_allows(self, agent_role: str, tool_name: str) -> bool:
        """Check if the role's default categories permit *tool_name*."""
        key = self._role_key(agent_role)
        categories = self.ROLE_TOOL_DEFAULTS[key]

        # Wildcard means everything is allowed
        if "*" in categories:
            return True

        tool_cats = _get_tool_categories(tool_name)
        if not tool_cats:
            # Unknown tools are denied under role defaults
            return False

        return bool(set(tool_cats) & set(categories))
