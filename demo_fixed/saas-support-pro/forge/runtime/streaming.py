"""Streaming support — real-time token-by-token agent responses."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


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


async def stream_llm_response(
    client: Any,
    messages: list[dict],
    model: str = "gpt-4",
    temperature: float = 0.7,
    tools: list[dict] | None = None,
) -> AsyncIterator[TokenChunk]:
    """
    Stream an LLM response token by token.
    
    Yields TokenChunk objects with delta text.
    The final chunk has done=True and full_text set.
    """
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

    try:
        stream = await client.chat.completions.create(**kwargs)

        async for chunk in stream:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            # Text content
            if delta.content:
                full_text += delta.content
                yield TokenChunk(delta=delta.content, full_text=full_text)

            # Tool calls (accumulated)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    # Build up tool call data incrementally
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

            # Check for finish
            if chunk.choices[0].finish_reason:
                break

        # Final chunk
        metadata = {}
        if tool_calls_data:
            metadata["tool_calls"] = tool_calls_data
        if hasattr(stream, 'usage') and stream.usage:
            metadata["usage"] = {
                "prompt_tokens": stream.usage.prompt_tokens,
                "completion_tokens": stream.usage.completion_tokens,
            }

        yield TokenChunk(delta="", full_text=full_text, done=True, metadata=metadata)

    except Exception as e:
        logger.error(f"Streaming error: {e}")
        yield TokenChunk(delta="", full_text=full_text, done=True, metadata={"error": str(e)})


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
