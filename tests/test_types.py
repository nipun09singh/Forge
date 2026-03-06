"""Tests for forge.runtime.types."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from forge.runtime.types import (
    LLMClient, ChatMessage, ToolCall, ToolCallFunction,
    ToolResult, TaskContext, LLMResponse,
)


class TestLLMClientProtocol:
    """Tests for LLMClient Protocol."""

    def test_mock_satisfies_protocol(self):
        """An AsyncMock with .chat attribute satisfies LLMClient."""
        client = AsyncMock()
        client.chat = MagicMock()
        assert isinstance(client, LLMClient)

    def test_real_pattern_satisfies(self):
        """Object with .chat property satisfies LLMClient."""
        class FakeClient:
            @property
            def chat(self):
                return MagicMock()
        assert isinstance(FakeClient(), LLMClient)

    def test_empty_object_fails(self):
        """Object without .chat doesn't satisfy LLMClient."""
        class NoChat:
            pass
        assert not isinstance(NoChat(), LLMClient)


class TestChatMessage:
    """Tests for ChatMessage TypedDict."""

    def test_full_message(self):
        msg: ChatMessage = {
            "role": "assistant",
            "content": "Hello",
            "tool_calls": [],
            "tool_call_id": "tc_123",
        }
        assert msg["role"] == "assistant"
        assert msg["content"] == "Hello"

    def test_minimal_message(self):
        """ChatMessage with only required fields (total=False means all optional)."""
        msg: ChatMessage = {"role": "user"}
        assert msg["role"] == "user"

    def test_system_message(self):
        msg: ChatMessage = {"role": "system", "content": "You are helpful."}
        assert msg["role"] == "system"

    def test_tool_message(self):
        msg: ChatMessage = {"role": "tool", "content": "result", "tool_call_id": "tc_1"}
        assert msg["tool_call_id"] == "tc_1"


class TestToolResult:
    """Tests for ToolResult TypedDict."""

    def test_creation(self):
        result: ToolResult = {"id": "call_123", "output": "File created"}
        assert result["id"] == "call_123"
        assert result["output"] == "File created"


class TestTaskContext:
    """Tests for TaskContext TypedDict."""

    def test_full_context(self):
        ctx: TaskContext = {
            "workdir": "/tmp/project",
            "agent_name": "TestAgent",
            "agent_id": "agent-abc123",
            "iteration": 5,
        }
        assert ctx["workdir"] == "/tmp/project"
        assert ctx["iteration"] == 5

    def test_empty_context(self):
        """All fields are optional."""
        ctx: TaskContext = {}
        assert len(ctx) == 0


class TestLLMResponse:
    """Tests for LLMResponse TypedDict."""

    def test_text_response(self):
        resp: LLMResponse = {"content": "Hello world"}
        assert resp["content"] == "Hello world"

    def test_tool_call_response(self):
        resp: LLMResponse = {
            "content": None,
            "tool_calls": [
                {"id": "tc_1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}
            ],
        }
        assert len(resp["tool_calls"]) == 1
        assert resp["tool_calls"][0]["function"]["name"] == "read_file"


class TestToolCall:
    """Tests for ToolCall TypedDict."""

    def test_creation(self):
        tc: ToolCall = {
            "id": "call_abc",
            "type": "function",
            "function": {"name": "echo", "arguments": '{"message": "hi"}'},
        }
        assert tc["id"] == "call_abc"
        assert tc["function"]["name"] == "echo"


class TestToolCallFunction:
    """Tests for ToolCallFunction TypedDict."""

    def test_creation(self):
        fn: ToolCallFunction = {"name": "read_file", "arguments": '{"path": "main.py"}'}
        assert fn["name"] == "read_file"
        assert fn["arguments"] == '{"path": "main.py"}'

    def test_empty(self):
        """All fields optional (total=False)."""
        fn: ToolCallFunction = {}
        assert len(fn) == 0
