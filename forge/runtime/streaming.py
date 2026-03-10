"""Streaming support — real-time token-by-token agent responses.

Supports multiple LLM providers (OpenAI, Anthropic, and generic fallback)
through a unified StreamProvider abstraction. All providers emit the same
TokenChunk output format so callers don't need to know the underlying API.
"""

from __future__ import annotations

import abc
import asyncio
import json
import logging
from typing import Any, AsyncIterator, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# Optional provider SDK imports — none of these are hard dependencies.
try:
    import openai as _openai_mod
except ImportError:
    _openai_mod = None  # type: ignore[assignment]

try:
    import anthropic as _anthropic_mod
except ImportError:
    _anthropic_mod = None  # type: ignore[assignment]


class StreamingResponse:
    """
    Collects streamed tokens and provides both streaming and final access.
    
    Usage:
        async for chunk in agent.execute_stream(task):
            print(chunk.delta, end="", flush=True)
        print(chunk.full_text)  # complete response
    """

    def __init__(self) -> None:
        self.chunks: list[str] = []
        self.full_text: str = ""
        self.done: bool = False
        self.tool_calls: list[dict] = []
        self.usage: dict[str, int] = {}

    def append(self, delta: str) -> None:
        self.chunks.append(delta)
        self.full_text += delta

    def finalize(self) -> None:
        self.done = True


class TokenChunk:
    """A single chunk of streamed tokens."""

    def __init__(self, delta: str, full_text: str = "", done: bool = False, metadata: dict | None = None):
        self.delta = delta
        self.full_text = full_text
        self.done = done
        self.metadata = metadata or {}


# ---------------------------------------------------------------------------
# StreamProvider protocol & implementations
# ---------------------------------------------------------------------------

@runtime_checkable
class StreamProvider(Protocol):
    """Protocol that all streaming providers must satisfy."""

    async def stream(
        self,
        client: Any,
        messages: list[dict],
        model: str,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[TokenChunk]:
        ...  # pragma: no cover


class OpenAIStreamProvider:
    """Streams via the OpenAI SDK (``client.chat.completions.create``)."""

    async def stream(
        self,
        client: Any,
        messages: list[dict],
        model: str,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[TokenChunk]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools

        full_text = ""
        tool_calls_data: list[dict] = []

        stream = await client.chat.completions.create(**kwargs)

        async for chunk in stream:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            # Text content
            if delta.content:
                full_text += delta.content
                yield TokenChunk(delta=delta.content, full_text=full_text)

            # Tool calls (accumulated incrementally)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    while len(tool_calls_data) <= idx:
                        tool_calls_data.append({"id": "", "function": {"name": "", "arguments": ""}})
                    if tc.id:
                        tool_calls_data[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls_data[idx]["function"]["name"] = tc.function.name
                        if tc.function.arguments:
                            tool_calls_data[idx]["function"]["arguments"] += tc.function.arguments

            if chunk.choices[0].finish_reason:
                break

        metadata: dict[str, Any] = {}
        if tool_calls_data:
            metadata["tool_calls"] = tool_calls_data
        if hasattr(stream, "usage") and stream.usage:
            metadata["usage"] = {
                "prompt_tokens": stream.usage.prompt_tokens,
                "completion_tokens": stream.usage.completion_tokens,
            }

        yield TokenChunk(delta="", full_text=full_text, done=True, metadata=metadata)


class AnthropicStreamProvider:
    """Streams via the Anthropic SDK (``client.messages.create``)."""

    async def stream(
        self,
        client: Any,
        messages: list[dict],
        model: str,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[TokenChunk]:
        # Anthropic separates the system prompt from messages.
        system_prompt: str | None = None
        api_messages: list[dict] = []
        for msg in messages:
            if msg.get("role") == "system":
                system_prompt = msg.get("content", "")
            else:
                api_messages.append(msg)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": 4096,
            "stream": True,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        full_text = ""
        tool_calls_data: list[dict] = []
        current_tool: dict[str, Any] | None = None

        stream = await client.messages.create(**kwargs)

        async for event in stream:
            event_type = getattr(event, "type", None)

            if event_type == "content_block_start":
                block = getattr(event, "content_block", None)
                if block and getattr(block, "type", None) == "tool_use":
                    current_tool = {
                        "id": getattr(block, "id", ""),
                        "function": {
                            "name": getattr(block, "name", ""),
                            "arguments": "",
                        },
                    }

            elif event_type == "content_block_delta":
                delta = getattr(event, "delta", None)
                if delta is None:
                    continue
                delta_type = getattr(delta, "type", None)

                if delta_type == "text_delta":
                    text = getattr(delta, "text", "")
                    if text:
                        full_text += text
                        yield TokenChunk(delta=text, full_text=full_text)

                elif delta_type == "input_json_delta" and current_tool is not None:
                    partial = getattr(delta, "partial_json", "")
                    current_tool["function"]["arguments"] += partial

            elif event_type == "content_block_stop":
                if current_tool is not None:
                    tool_calls_data.append(current_tool)
                    current_tool = None

            elif event_type == "message_delta":
                # May contain usage info; handled after the loop.
                pass

            elif event_type == "message_stop":
                break

        metadata: dict[str, Any] = {}
        if tool_calls_data:
            metadata["tool_calls"] = tool_calls_data

        # Try to extract usage from the stream's final message snapshot.
        if hasattr(stream, "get_final_message"):
            try:
                final_msg = await stream.get_final_message()
                if hasattr(final_msg, "usage") and final_msg.usage:
                    metadata["usage"] = {
                        "prompt_tokens": getattr(final_msg.usage, "input_tokens", 0),
                        "completion_tokens": getattr(final_msg.usage, "output_tokens", 0),
                    }
            except Exception:
                pass

        yield TokenChunk(delta="", full_text=full_text, done=True, metadata=metadata)

    @staticmethod
    def _convert_tools(openai_tools: list[dict]) -> list[dict]:
        """Convert OpenAI-format tool schemas to Anthropic format."""
        anthropic_tools: list[dict] = []
        for tool in openai_tools:
            fn = tool.get("function", {})
            anthropic_tools.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            })
        return anthropic_tools


class GenericStreamProvider:
    """Fallback provider — makes a non-streaming call and yields the full
    response as a single chunk.  Works with any client that exposes
    ``client.chat.completions.create()``."""

    async def stream(
        self,
        client: Any,
        messages: list[dict],
        model: str,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[TokenChunk]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools

        response = await client.chat.completions.create(**kwargs)

        full_text = ""
        tool_calls_data: list[dict] = []
        metadata: dict[str, Any] = {}

        if response.choices:
            choice = response.choices[0]
            full_text = choice.message.content or ""

            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    tool_calls_data.append({
                        "id": tc.id,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    })

        if tool_calls_data:
            metadata["tool_calls"] = tool_calls_data
        if hasattr(response, "usage") and response.usage:
            metadata["usage"] = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            }

        if full_text:
            yield TokenChunk(delta=full_text, full_text=full_text)

        yield TokenChunk(delta="", full_text=full_text, done=True, metadata=metadata)


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------

def detect_provider(client: Any, model: str = "") -> StreamProvider:
    """Return the appropriate ``StreamProvider`` for the given *client* and *model*.

    Detection strategy (in order):
    1. Client type — ``openai.AsyncOpenAI`` → OpenAI, ``anthropic.AsyncAnthropic`` → Anthropic
    2. Model name prefix — ``gpt-*`` / ``o1-*`` / ``o3-*`` → OpenAI, ``claude-*`` → Anthropic
    3. Fallback → GenericStreamProvider (non-streaming)
    """
    # --- Check client type ---------------------------------------------------
    if _openai_mod is not None:
        openai_types = (
            getattr(_openai_mod, "AsyncOpenAI", None),
            getattr(_openai_mod, "OpenAI", None),
        )
        openai_types = tuple(t for t in openai_types if t is not None)
        if openai_types and isinstance(client, openai_types):
            return OpenAIStreamProvider()

    if _anthropic_mod is not None:
        anthropic_types = (
            getattr(_anthropic_mod, "AsyncAnthropic", None),
            getattr(_anthropic_mod, "Anthropic", None),
        )
        anthropic_types = tuple(t for t in anthropic_types if t is not None)
        if anthropic_types and isinstance(client, anthropic_types):
            return AnthropicStreamProvider()

    # --- Check model name prefix ---------------------------------------------
    model_lower = model.lower()
    if model_lower.startswith(("gpt-", "o1-", "o3-")):
        return OpenAIStreamProvider()
    if model_lower.startswith("claude-"):
        return AnthropicStreamProvider()

    # --- Fallback to generic (non-streaming) ---------------------------------
    return GenericStreamProvider()


# ---------------------------------------------------------------------------
# Public streaming entry-point
# ---------------------------------------------------------------------------

async def stream_llm_response(
    client: Any,
    messages: list[dict],
    model: str = "gpt-4",
    temperature: float = 0.7,
    tools: list[dict] | None = None,
    provider: StreamProvider | None = None,
) -> AsyncIterator[TokenChunk]:
    """
    Stream an LLM response token by token.
    
    Yields TokenChunk objects with delta text.
    The final chunk has done=True and full_text set.

    The *provider* is auto-detected from the client/model when not supplied.
    """
    if provider is None:
        provider = detect_provider(client, model)

    try:
        async for chunk in provider.stream(
            client=client,
            messages=messages,
            model=model,
            tools=tools,
            temperature=temperature,
        ):
            yield chunk
    except Exception as e:
        logger.error(f"Streaming error: {e}")
        yield TokenChunk(delta="", full_text="", done=True, metadata={"error": str(e)})


async def stream_agent_execution(
    agent: Any,  # Agent instance
    task: str,
    context: dict[str, Any] | None = None,
) -> AsyncIterator[TokenChunk]:
    """
    Stream an agent's execution, yielding tokens as the LLM produces them.
    
    For tool-calling iterations, yields status messages between tool calls.
    """
    from forge.runtime.agent import AgentStatus

    agent.status = AgentStatus.WORKING
    agent.conversation = [{"role": "system", "content": agent.system_prompt}]

    task_message = task
    if context:
        task_message += "\n\nContext:\n" + "\n".join(f"- {k}: {v}" for k, v in context.items())
    agent.conversation.append({"role": "user", "content": task_message})

    if not agent._llm_client:
        yield TokenChunk(delta="Error: No LLM client configured.", done=True)
        return

    tools_schema = agent.tool_registry.get_openai_tools_schema()

    for iteration in range(agent.max_iterations):
        full_response = ""
        tool_calls = []

        # Stream the LLM response
        kwargs: dict[str, Any] = {
            "model": agent.model,
            "temperature": agent.temperature,
        }
        if tools_schema:
            kwargs["tools"] = tools_schema

        async for chunk in stream_llm_response(
            client=agent._llm_client,
            messages=agent.conversation,
            **kwargs,
        ):
            if chunk.done:
                full_response = chunk.full_text
                tool_calls = chunk.metadata.get("tool_calls", [])
            else:
                yield chunk

        # Handle tool calls
        if tool_calls:
            agent.conversation.append({
                "role": "assistant",
                "content": full_response,
                "tool_calls": tool_calls,
            })

            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}

                yield TokenChunk(delta=f"\n\U0001f527 Using tool: {fn_name}...\n")

                tool = agent.tool_registry.get(fn_name)
                if tool:
                    try:
                        output = await tool.run(**args)
                        agent.conversation.append({
                            "role": "tool",
                            "content": str(output),
                            "tool_call_id": tc["id"],
                        })
                        yield TokenChunk(delta=f"   \u2705 {fn_name} complete\n")
                    except Exception as e:
                        agent.conversation.append({
                            "role": "tool",
                            "content": f"Error: {e}",
                            "tool_call_id": tc["id"],
                        })
                        yield TokenChunk(delta=f"   \u274c {fn_name} error: {e}\n")
                else:
                    agent.conversation.append({
                        "role": "tool",
                        "content": f"Unknown tool: {fn_name}",
                        "tool_call_id": tc["id"],
                    })

            continue  # Next iteration

        # No tool calls — done
        agent.conversation.append({"role": "assistant", "content": full_response})
        agent.memory.store(f"{agent.name}:last_result", full_response)
        agent.status = AgentStatus.COMPLETED
        yield TokenChunk(delta="", full_text=full_response, done=True)
        return

    # Max iterations
    agent.status = AgentStatus.COMPLETED
    yield TokenChunk(delta="", full_text="Max iterations reached.", done=True)
