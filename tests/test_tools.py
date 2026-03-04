"""Tests for forge.runtime.tools"""

import pytest
from forge.runtime.tools import Tool, ToolParameter, ToolRegistry, tool


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
