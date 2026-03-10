"""Tests for forge.runtime.tools"""

import json
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest
from forge.runtime.tools import Tool, ToolParameter, ToolRegistry, tool


# ===========================================================================
# Original tool-framework tests (preserved)
# ===========================================================================

class TestTool:
    @pytest.mark.asyncio
    async def test_tool_execution(self, sample_tool):
        result = await sample_tool.run(message="hello")
        assert result == "Echo: hello"

    def test_tool_schema(self, sample_tool):
        schema = sample_tool.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "echo"
        assert "message" in schema["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_tool_without_impl(self):
        t = Tool(name="noop", description="Does nothing")
        with pytest.raises(NotImplementedError):
            await t.run()


class TestToolRegistry:
    def test_register_and_get(self, sample_tool):
        reg = ToolRegistry()
        reg.register(sample_tool)
        assert reg.get("echo") is sample_tool
        assert reg.get("nonexistent") is None

    def test_list_tools(self, sample_tool):
        reg = ToolRegistry()
        reg.register(sample_tool)
        assert len(reg.list_tools()) == 1

    def test_openai_schema(self, sample_tool):
        reg = ToolRegistry()
        reg.register(sample_tool)
        schemas = reg.get_openai_tools_schema()
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "echo"


class TestToolDecorator:
    def test_decorator_creates_tool(self):
        @tool(name="greet", description="Says hello")
        def greet(name: str) -> str:
            return f"Hello {name}"

        assert isinstance(greet, Tool)
        assert greet.name == "greet"
        assert len(greet.parameters) == 1


# ===========================================================================
# Integration tool tests — HTTP, File, Command, Email, Stripe, Twilio
# ===========================================================================


class TestHTTPTool:
    """Tests for http_tool with mocked urllib."""

    def test_create_http_tool(self):
        from forge.runtime.integrations.http_tool import create_http_tool
        tool = create_http_tool()
        assert tool.name == "http_request"
        param_names = [p.name for p in tool.parameters]
        assert "url" in param_names
        assert "method" in param_names

    @pytest.mark.asyncio
    async def test_http_get_mocked_response(self):
        import urllib.request
        from forge.runtime.integrations.http_tool import http_request
        from forge.runtime.integrations.rate_limiter import reset_all_limiters
        reset_all_limiters()

        fake_resp = MagicMock()
        fake_resp.status = 200
        fake_resp.headers = {"Content-Type": "application/json"}
        fake_resp.read.return_value = b'{"ok": true}'
        fake_resp.__enter__ = lambda s: s
        fake_resp.__exit__ = MagicMock(return_value=False)

        with patch.object(urllib.request, "urlopen", return_value=fake_resp), \
             patch("forge.runtime.integrations.http_tool.socket.getaddrinfo",
                   return_value=[(None, None, None, None, ("93.184.216.34",))]):
            result = json.loads(await http_request("https://example.com/api", method="GET"))
            assert result["status"] == 200
            assert "ok" in result["body"]

    def test_ssrf_blocks_private_ip(self):
        from forge.runtime.integrations.http_tool import _is_url_safe
        with patch("forge.runtime.integrations.http_tool.socket.getaddrinfo",
                   return_value=[(None, None, None, None, ("127.0.0.1",))]):
            safe, reason = _is_url_safe("http://localhost/secret")
            assert not safe
            assert "private" in reason.lower() or "internal" in reason.lower()

    def test_ssrf_blocks_metadata_endpoint(self):
        from forge.runtime.integrations.http_tool import _is_url_safe
        safe, reason = _is_url_safe("http://169.254.169.254/latest/meta-data")
        assert not safe
        assert "metadata" in reason.lower()

    def test_ssrf_blocks_non_http_scheme(self):
        from forge.runtime.integrations.http_tool import _is_url_safe
        safe, reason = _is_url_safe("ftp://files.example.com/data")
        assert not safe
        assert "http" in reason.lower()


class TestFileTool:
    """Tests for file_tool using a real temp directory."""

    @pytest.mark.asyncio
    async def test_write_and_read(self, monkeypatch):
        from forge.runtime.integrations.file_tool import create_file_tool
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("AGENCY_DATA_DIR", tmp)
            tool = create_file_tool(tmp)
            read_write_file = tool._fn
            write_res = json.loads(await read_write_file("write", "hello.txt", "Hello World"))
            assert write_res["success"] is True

            read_res = json.loads(await read_write_file("read", "hello.txt"))
            assert read_res["content"] == "Hello World"

    @pytest.mark.asyncio
    async def test_append(self, monkeypatch):
        from forge.runtime.integrations.file_tool import create_file_tool
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("AGENCY_DATA_DIR", tmp)
            tool = create_file_tool(tmp)
            read_write_file = tool._fn
            await read_write_file("write", "log.txt", "Line1\n")
            await read_write_file("append", "log.txt", "Line2\n")
            read_res = json.loads(await read_write_file("read", "log.txt"))
            assert "Line1" in read_res["content"]
            assert "Line2" in read_res["content"]

    @pytest.mark.asyncio
    async def test_list_directory(self, monkeypatch):
        from forge.runtime.integrations.file_tool import create_file_tool
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("AGENCY_DATA_DIR", tmp)
            tool = create_file_tool(tmp)
            read_write_file = tool._fn
            await read_write_file("write", "a.txt", "aaa")
            await read_write_file("write", "b.txt", "bbb")
            list_res = json.loads(await read_write_file("list", "."))
            names = [e["name"] for e in list_res["entries"]]
            assert "a.txt" in names
            assert "b.txt" in names

    @pytest.mark.asyncio
    async def test_delete(self, monkeypatch):
        from forge.runtime.integrations.file_tool import create_file_tool
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("AGENCY_DATA_DIR", tmp)
            tool = create_file_tool(tmp)
            read_write_file = tool._fn
            await read_write_file("write", "tmp.txt", "data")
            del_res = json.loads(await read_write_file("delete", "tmp.txt"))
            assert del_res["success"] is True
            read_res = json.loads(await read_write_file("read", "tmp.txt"))
            assert "error" in read_res

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, monkeypatch):
        from forge.runtime.integrations.file_tool import create_file_tool
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("AGENCY_DATA_DIR", tmp)
            tool = create_file_tool(tmp)
            read_write_file = tool._fn
            res = json.loads(await read_write_file("read", "../../../etc/passwd"))
            assert "error" in res
            assert "denied" in res["error"].lower() or "outside" in res["error"].lower()

    @pytest.mark.asyncio
    async def test_unknown_action(self, monkeypatch):
        from forge.runtime.integrations.file_tool import create_file_tool
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("AGENCY_DATA_DIR", tmp)
            tool = create_file_tool(tmp)
            read_write_file = tool._fn
            res = json.loads(await read_write_file("explode", "x.txt"))
            assert "error" in res


class TestCommandTool:
    """Tests for command_tool whitelist and execution."""

    @pytest.mark.asyncio
    async def test_allowed_command_runs(self):
        from forge.runtime.integrations.command_tool import run_command
        result = json.loads(await run_command("python --version", workdir="."))
        assert result.get("blocked") is not True
        assert result.get("success") is True or result.get("exit_code") == 0

    @pytest.mark.asyncio
    async def test_disallowed_command_blocked(self):
        from forge.runtime.integrations.command_tool import run_command
        result = json.loads(await run_command("nmap 192.168.1.1", workdir="."))
        assert result["blocked"] is True

    def test_whitelist_allows_git(self):
        from forge.runtime.integrations.command_tool import _check_command_whitelist
        ok, _ = _check_command_whitelist("git status")
        assert ok

    def test_whitelist_rejects_unknown_binary(self):
        from forge.runtime.integrations.command_tool import _check_command_whitelist
        ok, reason = _check_command_whitelist("evil_binary --steal-data")
        assert not ok
        assert "evil_binary" in reason


class TestEmailTool:
    """Tests for email_tool — verify error handling without real SMTP."""

    def test_create_email_tool(self):
        from forge.runtime.integrations.email_tool import create_email_tool
        tool = create_email_tool()
        assert tool.name == "send_email"
        param_names = [p.name for p in tool.parameters]
        assert "to" in param_names
        assert "subject" in param_names

    @pytest.mark.asyncio
    async def test_smtp_connection_error_handled(self):
        """Without a real SMTP server the tool should return an error, not crash."""
        from forge.runtime.integrations.email_tool import send_email
        from forge.runtime.integrations.rate_limiter import reset_all_limiters
        reset_all_limiters()
        result = json.loads(await send_email("test@example.com", "Test", "Body"))
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_email_with_mocked_smtp(self):
        from forge.runtime.integrations.email_tool import send_email
        from forge.runtime.integrations.rate_limiter import reset_all_limiters
        reset_all_limiters()

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = lambda s: s
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("forge.runtime.integrations.email_tool.smtplib.SMTP", return_value=mock_smtp):
            result = json.loads(await send_email("user@example.com", "Hello", "World"))
            assert result["success"] is True
            assert "user@example.com" in result["message"]
