"""Tests for SemanticBudget and ContextCategory in forge.runtime.token_manager."""

import pytest
from forge.runtime.token_manager import (
    ContextCategory,
    SemanticBudget,
    TokenCounter,
)


def _make_msg(role: str, content: str, **extra) -> dict:
    """Helper to create a message dict."""
    msg = {"role": role, "content": content}
    msg.update(extra)
    return msg


def _make_large_conversation(n: int = 200, word_count: int = 500) -> list[dict]:
    """Create a conversation that will exceed token budget."""
    msgs = [_make_msg("system", "System prompt")]
    for i in range(n):
        msgs.append(_make_msg("user", f"msg{i} " + "x " * word_count))
    return msgs


class TestContextCategory:
    """Tests for ContextCategory dataclass."""

    def test_fields(self):
        cat = ContextCategory("research", 4000, pinned=True, priority=1)
        assert cat.name == "research"
        assert cat.budget_tokens == 4000
        assert cat.pinned is True
        assert cat.priority == 1


class TestSemanticBudgetPinnedSurvival:
    """Pinned categories survive pruning even when over budget."""

    def test_pinned_system_survives_pruning(self):
        """System messages (pinned, priority 0) are never pruned."""
        sb = SemanticBudget(model="gpt-3.5-turbo")
        msgs = _make_large_conversation(200, 500)
        # Tag everything
        sb.tag_message(msgs[0], "system")
        for m in msgs[1:]:
            sb.tag_message(m, "conversation")

        result = sb.prune_by_budget(msgs)
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "System prompt"
        assert len(result) < len(msgs)

    def test_pinned_research_survives_pruning(self):
        """Research-tagged messages (pinned) are never pruned."""
        sb = SemanticBudget(model="gpt-3.5-turbo")
        msgs = [_make_msg("system", "System prompt")]
        sb.tag_message(msgs[0], "system")

        # Add a research message
        research_msg = _make_msg("tool", "Important API docs from web search")
        msgs.append(research_msg)
        sb.tag_message(research_msg, "research")

        # Fill with lots of conversation to force pruning
        for i in range(200):
            m = _make_msg("user", f"padding{i} " + "x " * 500)
            msgs.append(m)
            sb.tag_message(m, "conversation")

        result = sb.prune_by_budget(msgs)
        assert len(result) < len(msgs), "Pruning should have removed messages"
        # Research message must survive
        assert any(m.get("content") == "Important API docs from web search" for m in result)

    def test_pinned_spec_survives_pruning(self):
        """Spec-tagged messages (pinned) are never pruned."""
        sb = SemanticBudget(model="gpt-3.5-turbo")
        msgs = [_make_msg("system", "System prompt")]
        sb.tag_message(msgs[0], "system")

        spec_msg = _make_msg("tool", "Project spec: build a REST API")
        msgs.append(spec_msg)
        sb.tag_message(spec_msg, "spec")

        for i in range(200):
            m = _make_msg("user", f"padding{i} " + "x " * 500)
            msgs.append(m)
            sb.tag_message(m, "conversation")

        result = sb.prune_by_budget(msgs)
        assert len(result) < len(msgs)
        assert any(m.get("content") == "Project spec: build a REST API" for m in result)


class TestSemanticBudgetPriorityOrder:
    """tool_results are pruned before conversation (higher priority number = pruned first)."""

    def test_tool_results_pruned_before_conversation(self):
        """tool_results (priority 5) pruned before conversation (priority 4)."""
        sb = SemanticBudget(model="gpt-3.5-turbo")
        msgs = [_make_msg("system", "System")]
        sb.tag_message(msgs[0], "system")

        # Add conversation messages first
        for i in range(50):
            m = _make_msg("user", f"conv{i} " + "y " * 200)
            msgs.append(m)
            sb.tag_message(m, "conversation")

        # Add tool_results as proper assistant+tool pairs (these should be pruned first)
        for i in range(50):
            tc_id = f"tc_tool_{i}"
            asst = _make_msg("assistant", "", tool_calls=[
                {"id": tc_id, "type": "function", "function": {"name": "run_command", "arguments": "{}"}}
            ])
            tool_resp = _make_msg("tool", f"tool_output{i} " + "z " * 200, tool_call_id=tc_id)
            msgs.append(asst)
            sb.tag_message(asst, "tool_results")
            msgs.append(tool_resp)
            sb.tag_message(tool_resp, "tool_results")

        result = sb.prune_by_budget(msgs)
        if len(result) < len(msgs):
            # Count how many tool vs conv messages remain
            remaining_tool = sum(1 for m in result if m.get("content", "").startswith("tool_output"))
            remaining_conv = sum(1 for m in result if m.get("content", "").startswith("conv"))
            # Tool results should be pruned more aggressively
            assert remaining_tool <= remaining_conv or remaining_tool == 0


class TestSemanticBudgetNoPruning:
    """No pruning when under budget."""

    def test_returns_unchanged_when_under_budget(self):
        """Conversations under budget are returned unchanged."""
        sb = SemanticBudget(model="gpt-4o")
        msgs = [
            _make_msg("system", "System prompt"),
            _make_msg("user", "Hello"),
            _make_msg("assistant", "Hi there!"),
        ]
        for m in msgs:
            sb.tag_message(m, "conversation")

        result = sb.prune_by_budget(msgs)
        assert result == msgs


class TestSemanticBudgetStatus:
    """Budget status returns correct per-category counts."""

    def test_budget_status_counts(self):
        """get_budget_status returns per-category usage."""
        sb = SemanticBudget(model="gpt-4o")
        sys_msg = _make_msg("system", "You are helpful.")
        user_msg = _make_msg("user", "Hello world")
        tool_msg = _make_msg("tool", "Search results here")

        sb.tag_message(sys_msg, "system")
        sb.tag_message(user_msg, "conversation")
        sb.tag_message(tool_msg, "research")

        status = sb.get_budget_status([sys_msg, user_msg, tool_msg])
        assert "system" in status
        assert "conversation" in status
        assert "research" in status
        assert status["system"]["used"] > 0
        assert status["conversation"]["used"] > 0
        assert status["research"]["used"] > 0
        assert status["system"]["pinned"] is True
        assert status["research"]["pinned"] is True
        assert status["conversation"]["pinned"] is False
        assert status["tool_results"]["used"] == 0  # nothing tagged here

    def test_budget_status_has_all_categories(self):
        """Status includes all default categories even if unused."""
        sb = SemanticBudget()
        status = sb.get_budget_status([])
        for cat in ("system", "research", "spec", "active_file", "conversation", "tool_results"):
            assert cat in status
            assert "used" in status[cat]
            assert "budget" in status[cat]


class TestSemanticBudgetToolPairs:
    """Assistant+tool pairs are preserved (not orphaned)."""

    def test_assistant_tool_pair_not_orphaned(self):
        """When assistant with tool_calls is pruned, its tool responses are also pruned."""
        sb = SemanticBudget(model="gpt-3.5-turbo")
        msgs = [_make_msg("system", "System")]
        sb.tag_message(msgs[0], "system")

        # Create an assistant + tool pair
        assistant_msg = _make_msg("assistant", "", tool_calls=[
            {"id": "tc1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}
        ])
        tool_response = _make_msg("tool", "file contents here", tool_call_id="tc1")
        msgs.append(assistant_msg)
        sb.tag_message(assistant_msg, "conversation")
        msgs.append(tool_response)
        sb.tag_message(tool_response, "tool_results")

        # Add lots of padding to force pruning
        for i in range(200):
            m = _make_msg("user", f"padding{i} " + "x " * 500)
            msgs.append(m)
            sb.tag_message(m, "conversation")

        result = sb.prune_by_budget(msgs)

        # Check: if the tool response was removed, the assistant must also be removed (and vice versa)
        has_tool_response = any(
            m.get("tool_call_id") == "tc1" for m in result
        )
        has_assistant_with_calls = any(
            m.get("tool_calls") and any(tc.get("id") == "tc1" for tc in m.get("tool_calls", []))
            for m in result
        )
        # They must be both present or both absent
        assert has_tool_response == has_assistant_with_calls, \
            "Assistant+tool pair was orphaned during pruning"


class TestSemanticBudgetFallbackCategory:
    """Unknown category falls back to conversation."""

    def test_unknown_category_falls_back(self):
        """Tagging with unknown category defaults to 'conversation'."""
        sb = SemanticBudget()
        msg = _make_msg("user", "test message")
        sb.tag_message(msg, "nonexistent_category")
        # Should have been stored with "conversation" category
        assert msg["_semantic_category"] == "conversation"


class TestSemanticBudgetIntegration:
    """Integration-style tests."""

    def test_mixed_categories_pruning(self):
        """Pruning with mixed categories respects all rules together."""
        sb = SemanticBudget(model="gpt-3.5-turbo")  # 16k limit
        msgs = []

        # System (pinned)
        sys_msg = _make_msg("system", "System prompt")
        msgs.append(sys_msg)
        sb.tag_message(sys_msg, "system")

        # Research (pinned)
        research_msg = _make_msg("tool", "API docs: important reference")
        msgs.append(research_msg)
        sb.tag_message(research_msg, "research")

        # Spec (pinned)
        spec_msg = _make_msg("tool", "Project spec: build MVP")
        msgs.append(spec_msg)
        sb.tag_message(spec_msg, "spec")

        # Add lots of tool_results and conversation to force pruning
        for i in range(100):
            tool_m = _make_msg("tool", f"tool_out{i} " + "z " * 200)
            msgs.append(tool_m)
            sb.tag_message(tool_m, "tool_results")

        for i in range(100):
            conv_m = _make_msg("user", f"conv{i} " + "y " * 200)
            msgs.append(conv_m)
            sb.tag_message(conv_m, "conversation")

        result = sb.prune_by_budget(msgs)

        # All pinned messages must survive
        contents = [m.get("content", "") for m in result]
        assert "System prompt" in contents
        assert "API docs: important reference" in contents
        assert "Project spec: build MVP" in contents

        # Pruning happened
        assert len(result) < len(msgs)


class TestSemanticBudgetEmbeddedCategory:
    """Category tag is embedded in the message dict, not a parallel list."""

    def test_category_survives_pruning(self):
        """After pruning, surviving messages still carry their _semantic_category tag."""
        sb = SemanticBudget(model="gpt-3.5-turbo")
        msgs = [_make_msg("system", "System prompt")]
        sb.tag_message(msgs[0], "system")

        research_msg = _make_msg("tool", "Important research")
        msgs.append(research_msg)
        sb.tag_message(research_msg, "research")

        for i in range(200):
            m = _make_msg("user", f"padding{i} " + "x " * 500)
            msgs.append(m)
            sb.tag_message(m, "conversation")

        result = sb.prune_by_budget(msgs)
        assert len(result) < len(msgs)
        # Research message survives with its embedded category
        for m in result:
            if m.get("content") == "Important research":
                assert m["_semantic_category"] == "research"
                break
        else:
            pytest.fail("Research message was pruned (should be pinned)")

    def test_get_category_reads_from_message(self):
        """_get_category reads _semantic_category from the message dict."""
        sb = SemanticBudget()
        msg = _make_msg("user", "hello")
        msg["_semantic_category"] = "research"
        assert sb._get_category(0, msg) == "research"

    def test_fallback_for_untagged_messages(self):
        """Untagged messages fall back to role-based inference."""
        sb = SemanticBudget()
        assert sb._get_category(0, _make_msg("system", "sys")) == "system"
        assert sb._get_category(0, _make_msg("tool", "out")) == "tool_results"
        assert sb._get_category(0, _make_msg("user", "hi")) == "conversation"
        assert sb._get_category(0, _make_msg("assistant", "hey")) == "conversation"
