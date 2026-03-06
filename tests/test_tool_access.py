"""Tests for role-based tool access control."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from forge.runtime.tool_access import ToolAccessPolicy, TOOL_CATEGORY_MAP
from forge.runtime.integrations import BuiltinToolkit
from forge.runtime.agent import Agent
from forge.runtime.tools import Tool, ToolParameter


# ---------------------------------------------------------------------------
# ToolAccessPolicy unit tests
# ---------------------------------------------------------------------------

class TestToolAccessPolicy:
    """Tests for the ToolAccessPolicy class."""

    def setup_method(self):
        self.policy = ToolAccessPolicy()

    # -- Role defaults --

    def test_admin_allowed_everything(self):
        assert self.policy.is_allowed("admin", "run_command")
        assert self.policy.is_allowed("admin", "query_database")
        assert self.policy.is_allowed("admin", "send_email")
        assert self.policy.is_allowed("admin", "git_operation")

    def test_developer_allowed_command(self):
        assert self.policy.is_allowed("developer", "run_command")
        assert self.policy.is_allowed("developer", "read_write_file")
        assert self.policy.is_allowed("developer", "http_request")
        assert self.policy.is_allowed("developer", "git_operation")

    def test_developer_denied_email(self):
        assert not self.policy.is_allowed("developer", "send_email")

    def test_support_denied_command(self):
        assert not self.policy.is_allowed("support", "run_command")

    def test_support_allowed_search_and_email(self):
        assert self.policy.is_allowed("support", "web_search")
        assert self.policy.is_allowed("support", "send_email")
        assert self.policy.is_allowed("support", "http_request")

    def test_analyst_denied_command(self):
        assert not self.policy.is_allowed("analyst", "run_command")

    def test_analyst_allowed_sql_and_search(self):
        assert self.policy.is_allowed("analyst", "query_database")
        assert self.policy.is_allowed("analyst", "web_search")

    def test_unknown_role_uses_default(self):
        assert not self.policy.is_allowed("intern", "run_command")
        assert self.policy.is_allowed("intern", "web_search")

    def test_role_case_insensitive(self):
        assert self.policy.is_allowed("Admin", "run_command")
        assert self.policy.is_allowed("DEVELOPER", "run_command")
        assert not self.policy.is_allowed("SUPPORT", "run_command")

    def test_unknown_tool_denied_by_default(self):
        assert not self.policy.is_allowed("developer", "totally_unknown_tool")
        assert self.policy.is_allowed("admin", "totally_unknown_tool")

    # -- Explicit allow/deny overrides --

    def test_denied_tools_overrides_role(self):
        """Denied list always wins, even for admin."""
        assert not self.policy.is_allowed(
            "admin", "run_command", denied_tools=["run_command"]
        )

    def test_allowed_tools_overrides_role(self):
        """Explicit allowlist limits to only those tools."""
        assert self.policy.is_allowed(
            "support", "run_command", allowed_tools=["run_command"]
        )
        assert not self.policy.is_allowed(
            "support", "send_email", allowed_tools=["run_command"]
        )

    def test_denied_takes_precedence_over_allowed(self):
        """deny + allow: deny wins."""
        assert not self.policy.is_allowed(
            "admin",
            "run_command",
            allowed_tools=["run_command"],
            denied_tools=["run_command"],
        )

    def test_allowed_tools_with_glob_pattern(self):
        assert self.policy.is_allowed(
            "support", "web_search", allowed_tools=["web_*"]
        )
        assert not self.policy.is_allowed(
            "support", "run_command", allowed_tools=["web_*"]
        )

    def test_denied_tools_with_glob_pattern(self):
        assert not self.policy.is_allowed(
            "admin", "run_command", denied_tools=["run_*"]
        )
        assert self.policy.is_allowed(
            "admin", "web_search", denied_tools=["run_*"]
        )

    # -- Introspection --

    def test_allowed_tool_categories(self):
        cats = self.policy.allowed_tool_categories("developer")
        assert "command" in cats
        assert "file" in cats

    def test_allowed_tool_categories_unknown_role(self):
        cats = self.policy.allowed_tool_categories("nobody")
        assert cats == self.policy.ROLE_TOOL_DEFAULTS["default"]


# ---------------------------------------------------------------------------
# BuiltinToolkit role-aware methods
# ---------------------------------------------------------------------------

class TestBuiltinToolkitRoleAware:
    """Tests for role-aware BuiltinToolkit methods."""

    def test_primitives_no_role_includes_command(self):
        tools = BuiltinToolkit.primitives()
        names = [t.name for t in tools]
        assert "run_command" in names

    def test_primitives_developer_includes_command(self):
        tools = BuiltinToolkit.primitives(role="developer")
        names = [t.name for t in tools]
        assert "run_command" in names

    def test_primitives_admin_includes_command(self):
        tools = BuiltinToolkit.primitives(role="admin")
        names = [t.name for t in tools]
        assert "run_command" in names

    def test_primitives_support_excludes_command(self):
        tools = BuiltinToolkit.primitives(role="support")
        names = [t.name for t in tools]
        assert "run_command" not in names
        assert "http_request" in names

    def test_primitives_analyst_excludes_command(self):
        tools = BuiltinToolkit.primitives(role="analyst")
        names = [t.name for t in tools]
        assert "run_command" not in names

    def test_safe_tools_excludes_command(self):
        tools = BuiltinToolkit.safe_tools()
        names = [t.name for t in tools]
        assert "run_command" not in names
        assert "read_write_file" in names
        assert "http_request" in names
        assert "web_search" in names
        assert "browse_web" in names


# ---------------------------------------------------------------------------
# Agent integration tests
# ---------------------------------------------------------------------------

def _make_tool(name: str) -> Tool:
    """Create a minimal no-op tool with the given name."""
    async def _noop(**kwargs):
        return f"{name} executed"
    return Tool(name=name, description=f"Tool: {name}", _fn=_noop)


class TestAgentToolAccess:
    """Tests for role-based access in Agent._execute_single_tool."""

    def _make_agent(self, role="developer", allowed=None, denied=None, tools=None):
        if tools is None:
            tools = [_make_tool("run_command"), _make_tool("web_search"), _make_tool("send_email")]
        return Agent(
            name="TestBot",
            role=role,
            system_prompt="test",
            tools=tools,
            allowed_tools=allowed,
            denied_tools=denied,
        )

    def _make_tc(self, tool_name, args=None):
        import json
        return {
            "id": "call-1",
            "function": {"name": tool_name, "arguments": json.dumps(args or {})},
        }

    @pytest.mark.asyncio
    async def test_developer_can_run_command(self):
        agent = self._make_agent(role="developer")
        result = await agent._execute_single_tool(self._make_tc("run_command"))
        assert "denied" not in result["output"].lower()

    @pytest.mark.asyncio
    async def test_support_blocked_from_command(self):
        agent = self._make_agent(role="support")
        result = await agent._execute_single_tool(self._make_tc("run_command"))
        assert "denied" in result["output"].lower()

    @pytest.mark.asyncio
    async def test_support_can_search(self):
        agent = self._make_agent(role="support")
        result = await agent._execute_single_tool(self._make_tc("web_search"))
        assert "denied" not in result["output"].lower()

    @pytest.mark.asyncio
    async def test_explicit_denied_overrides_role(self):
        agent = self._make_agent(role="admin", denied=["run_command"])
        result = await agent._execute_single_tool(self._make_tc("run_command"))
        assert "denied" in result["output"].lower()

    @pytest.mark.asyncio
    async def test_explicit_allowed_permits_blocked_tool(self):
        agent = self._make_agent(role="support", allowed=["run_command"])
        result = await agent._execute_single_tool(self._make_tc("run_command"))
        assert "denied" not in result["output"].lower()

    @pytest.mark.asyncio
    async def test_admin_unrestricted_by_default(self):
        agent = self._make_agent(role="admin")
        for tool in ["run_command", "web_search", "send_email"]:
            result = await agent._execute_single_tool(self._make_tc(tool))
            assert "denied" not in result["output"].lower(), f"{tool} should be allowed for admin"

    @pytest.mark.asyncio
    async def test_agent_stores_access_fields(self):
        agent = self._make_agent(
            role="support",
            allowed=["web_search"],
            denied=["run_command"],
        )
        assert agent.allowed_tools == ["web_search"]
        assert agent.denied_tools == ["run_command"]

    @pytest.mark.asyncio
    async def test_denied_glob_pattern(self):
        agent = self._make_agent(role="admin", denied=["run_*"])
        result = await agent._execute_single_tool(self._make_tc("run_command"))
        assert "denied" in result["output"].lower()
