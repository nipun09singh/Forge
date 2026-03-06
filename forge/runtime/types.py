"""Core type definitions for Forge runtime.

Replaces pervasive use of `Any` with proper, descriptive types
that enable IDE autocomplete and static analysis.
"""

from __future__ import annotations

from typing import TypedDict, Literal, Protocol, Any, runtime_checkable


# ── LLM Client ──────────────────────────────────────────────

@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM clients (e.g., AsyncOpenAI).
    
    Using a Protocol instead of importing AsyncOpenAI directly
    allows flexibility for different LLM providers.
    """
    @property
    def chat(self) -> Any:
        """Access chat completions API."""
        ...


# ── Message Types ───────────────────────────────────────────

class ToolCallFunction(TypedDict, total=False):
    """Function details in a tool call."""
    name: str
    arguments: str


class ToolCall(TypedDict, total=False):
    """A tool call from the LLM."""
    id: str
    type: str
    function: ToolCallFunction


class ChatMessage(TypedDict, total=False):
    """OpenAI-compatible chat message."""
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None
    tool_calls: list[ToolCall]
    tool_call_id: str


class ToolResult(TypedDict):
    """Result from executing a tool."""
    id: str
    output: str


# ── Task Context ────────────────────────────────────────────

class TaskContext(TypedDict, total=False):
    """Context passed with task execution requests."""
    workdir: str
    agent_name: str
    agent_id: str
    iteration: int
    user_input: str
    parent_task: str
    metadata: dict[str, str]


# ── LLM Response ────────────────────────────────────────────

class LLMResponse(TypedDict, total=False):
    """Parsed response from an LLM call."""
    content: str | None
    tool_calls: list[ToolCall]
