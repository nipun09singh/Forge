"""Tests for forge.runtime.agent"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from forge.runtime.agent import Agent, AgentStatus, TaskResult, Message


class TestAgent:
    def test_agent_creation(self, sample_agent):
        assert sample_agent.name == "TestAgent"
        assert sample_agent.role == "specialist"
        assert sample_agent.status == AgentStatus.IDLE
        assert sample_agent.id.startswith("agent-")

    def test_agent_has_tools(self, sample_agent):
        tools = sample_agent.tool_registry.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "echo"

    def test_set_llm_client(self, sample_agent, mock_llm_client):
        sample_agent.set_llm_client(mock_llm_client)
        assert sample_agent._llm_client is mock_llm_client

    def test_set_memory(self, sample_agent):
        from forge.runtime.memory import SharedMemory
        mem = SharedMemory()
        sample_agent.set_memory(mem)
        assert sample_agent.memory is mem

    @pytest.mark.asyncio
    async def test_execute_without_llm_raises(self, sample_agent):
        result = await sample_agent.execute("test task")
        assert result.success is False
        assert "no LLM client" in result.output.lower() or "error" in result.output.lower()

    @pytest.mark.asyncio
    async def test_execute_with_llm(self, sample_agent_with_llm):
        result = await sample_agent_with_llm.execute("test task")
        assert result.success is True
        assert result.output == "Test response from mock LLM"
        assert sample_agent_with_llm.status == AgentStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_sets_status(self, sample_agent_with_llm):
        await sample_agent_with_llm.execute("test")
        assert sample_agent_with_llm.status == AgentStatus.COMPLETED

    def test_agent_repr(self, sample_agent):
        r = repr(sample_agent)
        assert "TestAgent" in r
        assert "specialist" in r


class TestTaskResult:
    def test_success_result(self):
        r = TaskResult(success=True, output="done")
        assert r.success
        assert r.output == "done"
        assert r.data == {}
        assert r.sub_tasks == []

    def test_failure_result(self):
        r = TaskResult(success=False, output="failed")
        assert not r.success


class TestMessage:
    def test_message_creation(self):
        m = Message(role="user", content="hello")
        assert m.role == "user"
        assert m.content == "hello"
        assert m.sender_id is None
