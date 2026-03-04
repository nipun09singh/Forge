"""Executor primitives — different strategies for executing tasks."""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result from an executor."""
    success: bool
    output: str
    iterations: int = 1
    tool_calls_made: int = 0
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class ExecutorBase(ABC):
    """Base class for all executors."""

    @abstractmethod
    async def execute(
        self,
        task: str,
        system_prompt: str,
        tools_schema: list[dict] | None,
        tool_executor: Any,
        llm_client: Any,
        model: str,
        temperature: float,
        conversation: list[dict] | None = None,
    ) -> ExecutionResult:
        """Execute a task."""
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


class SingleShotExecutor(ExecutorBase):
    """One LLM call, no tool use. Best for classification, formatting, simple Q&A."""

    async def execute(self, task, system_prompt, tools_schema, tool_executor, llm_client, model, temperature, conversation=None):
        start = time.time()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

        try:
            response = await llm_client.chat.completions.create(
                model=model, messages=messages, temperature=temperature,
            )
            output = response.choices[0].message.content or ""
            return ExecutionResult(
                success=True, output=output, iterations=1,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return ExecutionResult(success=False, output=f"Error: {e}", duration_ms=(time.time() - start) * 1000)


class ReActExecutor(ExecutorBase):
    """
    Think-Act-Observe loop. The gold standard for tool-using agents.
    
    Each iteration:
    1. THINK — LLM reasons about what to do
    2. ACT — calls a tool (or produces final answer)
    3. OBSERVE — reads tool output
    4. Repeat until done or max_iterations
    """

    def __init__(self, max_iterations: int = 15):
        self.max_iterations = max_iterations

    async def execute(self, task, system_prompt, tools_schema, tool_executor, llm_client, model, temperature, conversation=None):
        start = time.time()
        messages = conversation or [{"role": "system", "content": system_prompt}]
        
        if not conversation:
            messages.append({"role": "user", "content": task})

        total_tool_calls = 0

        for iteration in range(self.max_iterations):
            try:
                kwargs = {"model": model, "messages": messages, "temperature": temperature}
                if tools_schema:
                    kwargs["tools"] = tools_schema

                response = await llm_client.chat.completions.create(**kwargs)
                choice = response.choices[0]

                # If tool calls — ACT
                if choice.message.tool_calls:
                    messages.append({
                        "role": "assistant",
                        "content": choice.message.content or "",
                        "tool_calls": [
                            {"id": tc.id, "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                            for tc in choice.message.tool_calls
                        ],
                    })

                    for tc in choice.message.tool_calls:
                        total_tool_calls += 1
                        try:
                            args = json.loads(tc.function.arguments)
                        except json.JSONDecodeError:
                            args = {}

                        # OBSERVE — get tool result
                        if tool_executor:
                            result = await tool_executor(tc.function.name, args)
                        else:
                            result = f"Tool '{tc.function.name}' not available"

                        messages.append({"role": "tool", "content": str(result), "tool_call_id": tc.id})
                    continue

                # No tool calls — agent is done (final THINK)
                output = choice.message.content or ""
                return ExecutionResult(
                    success=True, output=output,
                    iterations=iteration + 1,
                    tool_calls_made=total_tool_calls,
                    duration_ms=(time.time() - start) * 1000,
                )

            except Exception as e:
                return ExecutionResult(
                    success=False, output=f"Error at iteration {iteration + 1}: {e}",
                    iterations=iteration + 1,
                    tool_calls_made=total_tool_calls,
                    duration_ms=(time.time() - start) * 1000,
                )

        # Max iterations
        last_content = messages[-1].get("content", "") if messages else ""
        return ExecutionResult(
            success=False, output=f"Max iterations ({self.max_iterations}) reached. Last output: {last_content[:500]}",
            iterations=self.max_iterations,
            tool_calls_made=total_tool_calls,
            duration_ms=(time.time() - start) * 1000,
        )

    def __repr__(self) -> str:
        return f"ReActExecutor(max_iterations={self.max_iterations})"


class MultiStepExecutor(ExecutorBase):
    """Executes a pre-planned sequence of steps, checkpointing between each."""

    def __init__(self, checkpoint_between_steps: bool = True):
        self.checkpoint = checkpoint_between_steps

    async def execute(self, task, system_prompt, tools_schema, tool_executor, llm_client, model, temperature, conversation=None):
        # Delegates to ReAct for each step but tracks progress
        react = ReActExecutor(max_iterations=10)
        result = await react.execute(task, system_prompt, tools_schema, tool_executor, llm_client, model, temperature, conversation)
        result.metadata["executor_type"] = "multi_step"
        return result
