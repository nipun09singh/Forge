"""Token-aware context window management for Forge agents."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Model context window limits (tokens)
MODEL_CONTEXT_LIMITS: dict[str, int] = {
    "gpt-4": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-3.5-turbo": 16_384,
    "o1": 200_000,
    "o1-mini": 128_000,
    "o3-mini": 200_000,
    "claude-3-opus": 200_000,
    "claude-3-sonnet": 200_000,
    "claude-3-haiku": 200_000,
}

# Approximate tokens per character ratio (conservative estimate)
CHARS_PER_TOKEN = 3.5
# Overhead per message in the OpenAI API (role, metadata, separators)
MESSAGE_OVERHEAD_TOKENS = 4
# Overhead for the reply priming
REPLY_OVERHEAD_TOKENS = 3


class TokenCounter:
    """
    Manages conversation context within token budgets.
    
    Uses character-based estimation by default (fast, no dependencies).
    If tiktoken is available, uses it for accurate counts.
    """

    def __init__(self, model: str = "gpt-4o", reserve_tokens: int = 4000):
        self.model = model
        self.max_context_tokens = MODEL_CONTEXT_LIMITS.get(model, 128_000)
        self.reserve_tokens = reserve_tokens  # Reserve for response generation
        self._encoding = None
        self._use_tiktoken = False

        # Try to load tiktoken for accurate counting
        try:
            import tiktoken
            self._encoding = tiktoken.encoding_for_model(model)
            self._use_tiktoken = True
        except (ImportError, KeyError):
            logger.debug(f"tiktoken not available for {model}, using character estimation")

    def count_tokens(self, text: str) -> int:
        """Count tokens in a text string."""
        if not text:
            return 0
        if self._use_tiktoken and self._encoding:
            return len(self._encoding.encode(text))
        # Fallback: character-based estimation
        return max(1, int(len(text) / CHARS_PER_TOKEN))

    def count_message_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Count total tokens for a message list (including overhead)."""
        total = 0
        for msg in messages:
            total += MESSAGE_OVERHEAD_TOKENS
            content = msg.get("content") or ""
            total += self.count_tokens(content)
            # Tool calls in assistant messages add tokens
            if "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    fn = tc.get("function", {})
                    total += self.count_tokens(fn.get("name", ""))
                    total += self.count_tokens(fn.get("arguments", ""))
        total += REPLY_OVERHEAD_TOKENS
        return total

    @property
    def available_tokens(self) -> int:
        """Max tokens available for conversation (excluding response reserve)."""
        return self.max_context_tokens - self.reserve_tokens

    def needs_pruning(self, messages: list[dict[str, Any]]) -> bool:
        """Check if conversation exceeds token budget."""
        return self.count_message_tokens(messages) > self.available_tokens

    def prune_conversation(
        self,
        conversation: list[dict[str, Any]],
        pinned_message: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Prune conversation to fit within token budget.
        
        Strategy:
        1. Always keep system message (index 0)
        2. Keep pinned message (project state summary) if provided
        3. Truncate long tool outputs first (cheapest information loss)
        4. Drop oldest non-system messages until we fit
        5. Never split assistant+tool_calls from their tool responses
        
        Args:
            conversation: Full conversation history
            pinned_message: Optional pinned context message to always keep
            
        Returns:
            Pruned conversation that fits within token budget
        """
        target = self.available_tokens
        
        # Check if pruning is needed
        current = self.count_message_tokens(conversation)
        if current <= target:
            return conversation

        # Step 1: Keep system message
        system = conversation[:1]
        rest = conversation[1:]

        # Step 2: Truncate long tool outputs first (they're often verbose)
        max_tool_content = 1500  # ~400 tokens
        pruned = []
        for msg in rest:
            if msg.get("role") == "tool":
                content = msg.get("content", "")
                if len(content) > max_tool_content:
                    pruned.append({**msg, "content": content[:max_tool_content] + "\n...(truncated)"})
                else:
                    pruned.append(msg)
            else:
                pruned.append(msg)

        # Step 3: Build result from the end, adding messages until we hit budget
        # Account for system + pinned message tokens
        base_tokens = self.count_message_tokens(system)
        if pinned_message:
            base_tokens += self.count_message_tokens([pinned_message])
        
        remaining_budget = target - base_tokens
        
        # Walk backwards, collecting messages that fit
        selected: list[dict[str, Any]] = []
        accumulated_tokens = 0
        i = len(pruned) - 1
        
        while i >= 0:
            msg = pruned[i]
            msg_tokens = self.count_message_tokens([msg])
            
            # If this is a tool response, we need to keep the preceding assistant message too
            # Walk back to collect the full tool exchange
            if msg.get("role") == "tool":
                # Collect all tool responses for this exchange
                exchange = [msg]
                exchange_tokens = msg_tokens
                j = i - 1
                while j >= 0 and pruned[j].get("role") == "tool":
                    t = self.count_message_tokens([pruned[j]])
                    exchange.insert(0, pruned[j])
                    exchange_tokens += t
                    j -= 1
                # Include the assistant message with tool_calls
                if j >= 0 and "tool_calls" in pruned[j]:
                    exchange.insert(0, pruned[j])
                    exchange_tokens += self.count_message_tokens([pruned[j]])
                    j -= 1
                
                if accumulated_tokens + exchange_tokens <= remaining_budget:
                    selected = exchange + selected
                    accumulated_tokens += exchange_tokens
                    i = j
                else:
                    # Can't fit this exchange, skip it
                    i = j
            else:
                if accumulated_tokens + msg_tokens <= remaining_budget:
                    selected.insert(0, msg)
                    accumulated_tokens += msg_tokens
                i -= 1
        
        result = system
        if pinned_message:
            result = result + [pinned_message]
        result = result + selected
        
        logger.debug(
            f"Context pruned: {current} -> {self.count_message_tokens(result)} tokens "
            f"({len(conversation)} -> {len(result)} messages)"
        )
        return result


@dataclass
class ContextCategory:
    """A semantic category for context budget management."""
    name: str              # "system", "research", "spec", "active_file", "tool_results", "conversation"
    budget_tokens: int     # max tokens for this category
    pinned: bool           # if True, NEVER prune this content
    priority: int          # lower number = higher priority (pruned LAST)


class SemanticBudget:
    """Category-based token budget manager. Pins important context, prunes verbose context."""

    DEFAULT_CATEGORIES = {
        "system":       ContextCategory("system",       2000,  pinned=True,  priority=0),
        "research":     ContextCategory("research",     4000,  pinned=True,  priority=1),
        "spec":         ContextCategory("spec",         3000,  pinned=True,  priority=2),
        "active_file":  ContextCategory("active_file",  4000,  pinned=False, priority=3),
        "conversation": ContextCategory("conversation", 40000, pinned=False, priority=4),
        "tool_results": ContextCategory("tool_results", 5000,  pinned=False, priority=5),
    }

    def __init__(self, model: str = "gpt-4o", categories: dict | None = None):
        self.categories = categories or {k: ContextCategory(v.name, v.budget_tokens, v.pinned, v.priority) for k, v in self.DEFAULT_CATEGORIES.items()}
        self._counter = TokenCounter(model=model)

    def tag_message(self, message: dict, category: str) -> dict:
        """Tag a message with its semantic category by embedding it in the dict."""
        if category not in self.categories:
            category = "conversation"
        message["_semantic_category"] = category
        return message

    def get_budget_status(self, conversation: list[dict]) -> dict[str, dict]:
        """Return per-category token usage vs budget."""
        usage = {}
        for cat_name, cat in self.categories.items():
            cat_messages = [m for m in conversation if self._get_category(0, m) == cat_name]
            tokens = sum(self._counter.count_message_tokens([m]) for m in cat_messages)
            usage[cat_name] = {"used": tokens, "budget": cat.budget_tokens, "pinned": cat.pinned, "priority": cat.priority}
        return usage

    def prune_by_budget(self, conversation: list[dict]) -> list[dict]:
        """Prune conversation respecting categories and pinning."""
        total_budget = self._counter.available_tokens
        total_tokens = self._counter.count_message_tokens(conversation)

        if total_tokens <= total_budget:
            return conversation  # No pruning needed

        # Build category→messages index
        categorized: dict[str, list[int]] = {c: [] for c in self.categories}
        for i, msg in enumerate(conversation):
            cat = self._get_category(i, msg)
            categorized.setdefault(cat, []).append(i)

        # Sort categories by priority (highest number = prune first)
        prune_order = sorted(self.categories.values(), key=lambda c: c.priority, reverse=True)

        indices_to_remove: set[int] = set()

        for cat in prune_order:
            if cat.pinned:
                continue  # NEVER prune pinned categories

            if total_tokens <= total_budget:
                break

            # Prune oldest messages in this category first
            cat_indices = categorized.get(cat.name, [])
            for idx in cat_indices:
                if idx in indices_to_remove:
                    continue
                msg = conversation[idx]
                tokens_saved = self._counter.count_message_tokens([msg])

                # Don't orphan tool messages
                if msg.get("role") == "assistant" and msg.get("tool_calls"):
                    # Also remove all subsequent tool responses
                    j = idx + 1
                    while j < len(conversation) and conversation[j].get("role") == "tool":
                        tokens_saved += self._counter.count_message_tokens([conversation[j]])
                        indices_to_remove.add(j)
                        j += 1
                elif msg.get("role") == "tool":
                    # Don't remove a tool response without its assistant — skip, handle via the assistant
                    continue

                indices_to_remove.add(idx)
                total_tokens -= tokens_saved

                if total_tokens <= total_budget:
                    break

        return [msg for i, msg in enumerate(conversation) if i not in indices_to_remove]

    def _get_category(self, index: int, msg: dict) -> str:
        """Get category from message's embedded tag."""
        cat = msg.get("_semantic_category", "")
        if cat and cat in self.categories:
            return cat
        # Fallback: infer from role
        role = msg.get("role", "")
        if role == "system":
            return "system"
        if role == "tool":
            return "tool_results"
        return "conversation"
