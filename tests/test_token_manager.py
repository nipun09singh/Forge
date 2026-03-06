"""Tests for forge.runtime.token_manager."""

import pytest
from forge.runtime.token_manager import TokenCounter, MODEL_CONTEXT_LIMITS


class TestTokenCounter:
    """Tests for TokenCounter."""

    def test_init_default_model(self):
        """Default model is gpt-4o with 128k context."""
        tc = TokenCounter()
        assert tc.model == "gpt-4o"
        assert tc.max_context_tokens == 128_000

    def test_init_custom_model(self):
        """Custom model uses correct context limits."""
        tc = TokenCounter(model="gpt-3.5-turbo")
        assert tc.max_context_tokens == 16_384

    def test_init_unknown_model_defaults(self):
        """Unknown model defaults to 128k."""
        tc = TokenCounter(model="unknown-model-xyz")
        assert tc.max_context_tokens == 128_000

    def test_count_tokens_empty(self):
        """Empty string returns 0 tokens."""
        tc = TokenCounter()
        assert tc.count_tokens("") == 0

    def test_count_tokens_nonempty(self):
        """Non-empty string returns positive token count."""
        tc = TokenCounter()
        count = tc.count_tokens("Hello world, this is a test.")
        assert count > 0

    def test_count_message_tokens(self):
        """Message list token counting includes overhead."""
        tc = TokenCounter()
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        count = tc.count_message_tokens(messages)
        assert count > 0
        # Should be more than just content tokens (includes overhead)
        content_only = tc.count_tokens("You are helpful.") + tc.count_tokens("Hello")
        assert count > content_only

    def test_count_message_tokens_with_tool_calls(self):
        """Tool calls in assistant messages add to token count."""
        tc = TokenCounter()
        messages = [
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "read_file", "arguments": '{"path": "/tmp/test.txt"}'}}
            ]},
        ]
        count = tc.count_message_tokens(messages)
        assert count > 0

    def test_available_tokens(self):
        """Available tokens accounts for reserve."""
        tc = TokenCounter(reserve_tokens=4000)
        assert tc.available_tokens == tc.max_context_tokens - 4000

    def test_needs_pruning_short_conversation(self):
        """Short conversation doesn't need pruning."""
        tc = TokenCounter()
        messages = [
            {"role": "system", "content": "Hi"},
            {"role": "user", "content": "Hello"},
        ]
        assert tc.needs_pruning(messages) is False

    def test_needs_pruning_long_conversation(self):
        """Very long conversation needs pruning."""
        tc = TokenCounter(model="gpt-3.5-turbo")  # 16k limit
        # Create a conversation that exceeds 16k tokens
        messages = [{"role": "system", "content": "System prompt"}]
        for i in range(200):
            messages.append({"role": "user", "content": "x " * 500})  # ~250 tokens each
        assert tc.needs_pruning(messages) is True


class TestConversationPruning:
    """Tests for conversation pruning logic."""

    def test_no_pruning_when_under_budget(self):
        """Conversations under budget are returned unchanged."""
        tc = TokenCounter()
        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Hello"},
        ]
        result = tc.prune_conversation(messages)
        assert result == messages

    def test_system_message_always_kept(self):
        """System message is never pruned."""
        tc = TokenCounter(model="gpt-3.5-turbo")
        messages = [{"role": "system", "content": "Important system prompt"}]
        for i in range(200):
            messages.append({"role": "user", "content": "x " * 500})
        result = tc.prune_conversation(messages)
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "Important system prompt"

    def test_recent_messages_preferred(self):
        """Pruning keeps recent messages over old ones."""
        tc = TokenCounter(model="gpt-3.5-turbo")
        messages = [{"role": "system", "content": "System"}]
        for i in range(200):
            messages.append({"role": "user", "content": f"Message {i}: " + "x " * 100})
        result = tc.prune_conversation(messages)
        # Last message should be present
        assert any("Message 199" in m.get("content", "") for m in result)
        # First non-system message should be pruned
        assert not any("Message 0" in m.get("content", "") for m in result)

    def test_tool_exchanges_kept_intact(self):
        """Tool call + tool responses are not split during pruning."""
        tc = TokenCounter(model="gpt-3.5-turbo")
        messages = [{"role": "system", "content": "System"}]
        # Add padding
        for i in range(100):
            messages.append({"role": "user", "content": "padding " * 100})
        # Add a tool exchange at the end
        messages.append({"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "test", "arguments": "{}"}}
        ]})
        messages.append({"role": "tool", "content": "tool result", "tool_call_id": "tc1"})
        messages.append({"role": "user", "content": "Final message"})

        result = tc.prune_conversation(messages)
        # If tool response is present, assistant with tool_calls should also be present
        has_tool_response = any(m.get("role") == "tool" for m in result)
        has_tool_call_assistant = any("tool_calls" in m for m in result)
        if has_tool_response:
            assert has_tool_call_assistant

    def test_long_tool_outputs_truncated(self):
        """Long tool outputs are truncated before dropping messages."""
        tc = TokenCounter(model="gpt-3.5-turbo")
        messages = [{"role": "system", "content": "System"}]
        for i in range(100):
            messages.append({"role": "user", "content": "padding " * 50})
        messages.append({"role": "tool", "content": "x" * 5000, "tool_call_id": "tc1"})

        result = tc.prune_conversation(messages)
        for m in result:
            if m.get("role") == "tool":
                assert len(m["content"]) <= 1600  # 1500 + truncation marker

    def test_pinned_message_kept(self):
        """Pinned message is always included in pruned output."""
        tc = TokenCounter(model="gpt-3.5-turbo")
        messages = [{"role": "system", "content": "System"}]
        for i in range(200):
            messages.append({"role": "user", "content": "padding " * 100})

        pinned = {"role": "user", "content": "[PROJECT STATE]: Important context"}
        result = tc.prune_conversation(messages, pinned_message=pinned)
        assert any(m.get("content", "").startswith("[PROJECT STATE]") for m in result)

    def test_pruned_is_shorter(self):
        """Pruned conversation has fewer tokens."""
        tc = TokenCounter(model="gpt-3.5-turbo")
        messages = [{"role": "system", "content": "System"}]
        for i in range(200):
            messages.append({"role": "user", "content": "x " * 500})

        result = tc.prune_conversation(messages)
        assert tc.count_message_tokens(result) < tc.count_message_tokens(messages)
        assert tc.count_message_tokens(result) <= tc.available_tokens


class TestModelContextLimits:
    """Tests for model context limit constants."""

    def test_known_models_have_limits(self):
        """All commonly used models have defined limits."""
        assert "gpt-4o" in MODEL_CONTEXT_LIMITS
        assert "gpt-4" in MODEL_CONTEXT_LIMITS
        assert "gpt-3.5-turbo" in MODEL_CONTEXT_LIMITS

    def test_limits_are_positive(self):
        """All limits are positive integers."""
        for model, limit in MODEL_CONTEXT_LIMITS.items():
            assert isinstance(limit, int)
            assert limit > 0
