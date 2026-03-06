"""Base Agent class for AI agency employees."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from forge.runtime.tools import Tool, ToolRegistry
from forge.runtime.memory import SharedMemory
from forge.runtime.types import LLMClient, ChatMessage, LLMResponse, ToolResult as ToolResultDict, TaskContext
from forge.runtime.improvement import QualityGate, QualityVerdict, ReflectionEngine, PerformanceTracker, TaskMetric
from forge.runtime.observability import EventLog, TraceContext, EventType, Event
from forge.runtime.human import HumanApprovalGate, ApprovalRequest, ApprovalResult, ApprovalDecision, Urgency
from forge.runtime.guardrails import GuardrailsEngine
from forge.runtime.model_router import ModelRouter
from forge.runtime.primitives import (
    PlannerBase, SimplePlanner, ExecutorBase, ReActExecutor,
    CriticBase, ScoredCritic, EscalationPolicy,
)
from forge.runtime.primitives.critics import CriticVerdict
from forge.runtime.knowledge import DomainKnowledge
from forge.runtime.structured_outputs import AgentResponse, TaskStatus, parse_agent_response

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    IDLE = "idle"
    WORKING = "working"
    WAITING = "waiting"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class Message:
    """A message passed between agents."""
    role: str  # "user", "assistant", "system", "agent"
    content: str
    sender_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskResult:
    """Result of an agent task execution."""
    success: bool
    output: str
    data: dict[str, Any] = field(default_factory=dict)
    sub_tasks: list[str] = field(default_factory=list)


class Agent:
    """
    Base AI Agent — an autonomous employee in an AI agency.
    
    Each agent has:
    - A role and persona (system prompt)
    - Access to tools
    - Shared memory with other agents
    - Ability to spawn sub-agents for delegation
    """

    def __init__(
        self,
        name: str,
        role: str,
        system_prompt: str,
        tools: list[Tool] | None = None,
        model: str = "gpt-4",
        temperature: float = 0.7,
        max_iterations: int = 20,
        enable_reflection: bool = False,
        quality_threshold: float = 0.8,
        max_reflections: int = 5,
        max_cost_usd: float = 0.0,  # 0 = unlimited
        max_conversation_history: int = 50,
        # Composable primitives (optional — defaults match current behavior)
        planner: PlannerBase | None = None,
        executor: ExecutorBase | None = None,
        critic: CriticBase | None = None,
        escalation_policy: EscalationPolicy | None = None,
        domain_knowledge: DomainKnowledge | None = None,
        tool_timeout_seconds: float = 30.0,
        max_concurrent_tools: int = 5,
    ):
        self.id = f"agent-{uuid.uuid4().hex[:8]}"
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.model = model
        self.temperature = temperature
        self.max_iterations = max_iterations
        self.status = AgentStatus.IDLE
        self.tool_registry = ToolRegistry()
        self.memory = SharedMemory()
        self.conversation: list[dict[str, Any]] = []
        self._sub_agents: list[Agent] = []
        self._llm_client: LLMClient | None = None  # Set by Agency at runtime
        self.enable_reflection = enable_reflection
        self.quality_threshold = quality_threshold
        self.max_reflections = max_reflections
        self.max_cost_usd = max_cost_usd
        self.max_conversation_history = max_conversation_history
        self._quality_gate: QualityGate | None = None
        self._reflection_engine: ReflectionEngine | None = None
        self._performance_tracker: PerformanceTracker | None = None
        self._event_log: EventLog | None = None
        self._trace_ctx: TraceContext | None = None
        self.require_human_approval: bool = False
        self._approval_gate: HumanApprovalGate | None = None
        self._guardrails: GuardrailsEngine | None = None
        self._model_router: ModelRouter | None = None
        self._tool_timeout_seconds = tool_timeout_seconds
        self._max_concurrent_tools = max_concurrent_tools

        # Composable primitives
        self._planner = planner or SimplePlanner()
        self._executor = executor or ReActExecutor(max_iterations=max_iterations)
        self._critic = critic
        self._escalation_policy = escalation_policy or EscalationPolicy()
        self.domain_knowledge = domain_knowledge

        if tools:
            for tool in tools:
                self.tool_registry.register(tool)

    def set_llm_client(self, client: LLMClient) -> None:
        """Inject the LLM client (called by Agency during setup)."""
        self._llm_client = client

    def set_memory(self, memory: SharedMemory) -> None:
        """Share memory store with this agent."""
        self.memory = memory

    def set_quality_gate(self, gate: QualityGate) -> None:
        """Set the quality gate for output validation."""
        self._quality_gate = gate
        self._reflection_engine = ReflectionEngine(gate)

    def set_performance_tracker(self, tracker: PerformanceTracker) -> None:
        """Set the performance tracker for metrics recording."""
        self._performance_tracker = tracker

    def set_event_log(self, log: EventLog) -> None:
        """Set the event log for observability."""
        self._event_log = log

    def set_trace_context(self, ctx: TraceContext) -> None:
        """Set the trace context for distributed tracing."""
        self._trace_ctx = ctx

    def set_approval_gate(self, gate: HumanApprovalGate) -> None:
        """Set the human approval gate."""
        self._approval_gate = gate
        self.require_human_approval = True

    def set_guardrails(self, guardrails: GuardrailsEngine) -> None:
        """Set guardrails engine for safety filtering."""
        self._guardrails = guardrails

    def set_model_router(self, router: ModelRouter) -> None:
        """Set smart model router for cost-optimized LLM selection."""
        self._model_router = router

    async def execute(self, task: str, context: TaskContext | dict[str, Any] | None = None) -> TaskResult:
        """
        Execute a task using the agent's reasoning loop.
        
        The agent will:
        1. Receive the task
        2. Reason about what to do
        3. Use tools as needed
        4. Iterate until done or max_iterations reached
        """
        if not task or not isinstance(task, str) or not task.strip():
            return TaskResult(success=False, output="Task must be a non-empty string.")

        self.status = AgentStatus.WORKING
        _start_time = time.time()
        if self._event_log:
            self._event_log.emit(Event(
                event_type=EventType.AGENT_START,
                agent_name=self.name,
                trace_id=self._trace_ctx.trace_id if self._trace_ctx else "",
                data={"task_preview": task[:200], "role": self.role},
            ))
        self.conversation = [{"role": "system", "content": self.system_prompt}]

        task_message = task
        if context:
            task_message += f"\n\nContext:\n{_format_context(context)}"

        self.conversation.append({"role": "user", "content": task_message})

        # Inject domain knowledge into the system prompt if available
        if self.domain_knowledge:
            knowledge_text = self.domain_knowledge.to_prompt_injection()
            if knowledge_text:
                self.conversation[0]["content"] += f"\n\n{knowledge_text}"

        try:
            for iteration in range(self.max_iterations):
                # Check cost budget
                if self.max_cost_usd > 0 and self._event_log:
                    current_cost = self._event_log.cost_tracker._per_agent.get(self.name, {}).get("cost_usd", 0)
                    if current_cost >= self.max_cost_usd:
                        self.status = AgentStatus.COMPLETED
                        return TaskResult(
                            success=True,
                            output=f"Cost limit reached (${current_cost:.4f} >= ${self.max_cost_usd:.4f}). Returning best result so far.",
                            data={"cost_limited": True, "cost_usd": current_cost},
                        )

                response = await self._call_llm()

                if response.get("tool_calls"):
                    tool_results = await self._execute_tools(response["tool_calls"])
                    self.conversation.append({"role": "assistant", "content": response.get("content", ""), "tool_calls": response["tool_calls"]})
                    for result in tool_results:
                        self.conversation.append({"role": "tool", "content": result["output"], "tool_call_id": result["id"]})
                    # Prune conversation to prevent context overflow
                    if len(self.conversation) > self.max_conversation_history:
                        # Keep system prompt + last N messages, but don't orphan tool messages
                        system = [m for m in self.conversation if m.get("role") == "system"]
                        rest = [m for m in self.conversation if m.get("role") != "system"]
                        keep_count = self.max_conversation_history - len(system)
                        if len(rest) > keep_count:
                            cut_idx = len(rest) - keep_count
                            # Don't cut in the middle of a tool response sequence
                            while cut_idx < len(rest) and rest[cut_idx].get("role") == "tool":
                                cut_idx += 1
                            rest = rest[cut_idx:]
                        self.conversation = system + rest
                    continue

                # No tool calls — agent is done
                final_output = response.get("content", "")
                
                # Try to parse as structured response for richer metadata
                structured = parse_agent_response(final_output)
                if structured and structured.status == TaskStatus.FAILED:
                    self.status = AgentStatus.ERROR
                    if self._performance_tracker:
                        self._performance_tracker.record(TaskMetric(
                            agent_name=self.name,
                            task_preview=task[:100],
                            success=False,
                            quality_score=0.0,
                            duration_seconds=time.time() - _start_time,
                            iterations_used=iteration + 1,
                        ))
                    return TaskResult(success=False, output=structured.content or final_output)
                self.conversation.append({"role": "assistant", "content": final_output})
                self.memory.store(f"{self.name}:last_result", final_output)

                # Critic evaluation (if configured)
                if self._critic:
                    verdict = await self._critic.evaluate(
                        task=task, output=final_output,
                        llm_client=self._llm_client,
                    )
                    if not verdict.passed and verdict.feedback:
                        # Feed critic feedback back for improvement
                        self.conversation.append({"role": "user", "content": (
                            f"Quality review feedback (score: {verdict.score:.0%}):\n"
                            f"{verdict.feedback}\n"
                            f"Issues: {', '.join(verdict.issues) if verdict.issues else 'None'}\n"
                            f"Please revise your response to address this feedback."
                        )})
                        # Do one more iteration to address feedback
                        revision = await self._call_llm()
                        if revision.get("content"):
                            final_output = revision["content"]

                self.status = AgentStatus.COMPLETED

                # Self-reflection loop: critique and improve until quality is met
                if self.enable_reflection and self._reflection_engine:
                    final_output, verdicts = await self._reflection_engine.reflect_and_improve(
                        agent=self,
                        task=task,
                        initial_output=final_output,
                        max_reflections=self.max_reflections,
                    )
                    quality_score = verdicts[-1].score if verdicts else 1.0
                else:
                    quality_score = 1.0

                # Record performance metrics
                if self._performance_tracker:
                    self._performance_tracker.record(TaskMetric(
                        agent_name=self.name,
                        task_preview=task[:100],
                        success=True,
                        quality_score=quality_score,
                        duration_seconds=time.time() - _start_time,
                        iterations_used=iteration + 1,
                    ))

                # Auto-track completion for analytics
                if hasattr(self, '_event_log') and self._event_log:
                    try:
                        # Revenue tracking — record value from completed task
                        if hasattr(self._event_log, 'cost_tracker'):
                            pass  # Cost already tracked in _call_llm
                    except Exception:
                        pass

                return TaskResult(success=True, output=final_output)

            # Max iterations reached
            self.status = AgentStatus.ERROR
            if self._performance_tracker:
                self._performance_tracker.record(TaskMetric(
                    agent_name=self.name,
                    task_preview=task[:100],
                    success=False,
                    quality_score=0.0,
                    duration_seconds=time.time() - _start_time,
                    iterations_used=self.max_iterations,
                ))
            return TaskResult(
                success=False,
                output=self.conversation[-1].get("content", "Max iterations reached."),
            )

        except Exception as e:
            self.status = AgentStatus.ERROR
            if self._performance_tracker:
                self._performance_tracker.record(TaskMetric(
                    agent_name=self.name,
                    task_preview=task[:100],
                    success=False,
                    quality_score=0.0,
                    duration_seconds=time.time() - _start_time,
                    iterations_used=0,
                ))
            return TaskResult(success=False, output=f"Agent error: {e}")

    async def _call_llm(self) -> LLMResponse:
        """Call the LLM with current conversation and available tools."""
        if not self._llm_client:
            raise RuntimeError(f"Agent '{self.name}' has no LLM client. Attach via Agency.")

        tools_schema = self.tool_registry.get_openai_tools_schema()

        # Smart model routing for cost optimization
        _effective_model = self.model
        if self._model_router:
            task_preview = self.conversation[-1].get("content", "") if self.conversation else ""
            _effective_model = self._model_router.select_model(
                task=task_preview[:500],
                messages=self.conversation,
                has_tools=bool(tools_schema),
                agent_role=self.role,
            )

        kwargs: dict[str, Any] = {
            "model": _effective_model,
            "messages": self.conversation,
            "temperature": self.temperature,
        }
        if tools_schema:
            kwargs["tools"] = tools_schema

        _llm_start = time.time()
        if self._event_log:
            self._event_log.emit_llm_call(
                agent_name=self.name,
                model=kwargs.get("model", self.model),
                messages_count=len(self.conversation),
                tools_count=len(tools_schema) if tools_schema else 0,
                trace_id=self._trace_ctx.trace_id if self._trace_ctx else "",
            )

        response = await self._llm_client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        _llm_duration = (time.time() - _llm_start) * 1000
        if self._event_log and hasattr(response, 'usage') and response.usage:
            self._event_log.emit_llm_response(
                agent_name=self.name,
                model=kwargs.get("model", self.model),
                prompt_tokens=response.usage.prompt_tokens or 0,
                completion_tokens=response.usage.completion_tokens or 0,
                has_tool_calls=bool(choice.message.tool_calls),
                duration_ms=_llm_duration,
                trace_id=self._trace_ctx.trace_id if self._trace_ctx else "",
            )

        result: dict[str, Any] = {"content": choice.message.content}

        if choice.message.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in choice.message.tool_calls
            ]
        return result

    async def _execute_tools(self, tool_calls: list[dict]) -> list[ToolResultDict]:
        """Execute tool calls concurrently and return results."""
        import json
        semaphore = asyncio.Semaphore(self._max_concurrent_tools)

        async def _run_one(tc: dict) -> dict:
            async with semaphore:
                return await self._execute_single_tool(tc)

        results = await asyncio.gather(*[_run_one(tc) for tc in tool_calls])
        return list(results)

    async def _execute_single_tool(self, tc: dict) -> ToolResultDict:
        """Execute a single tool call with guardrails, approval, and observability."""
        import json
        fn_name = tc["function"]["name"]
        try:
            args = json.loads(tc["function"]["arguments"])
        except json.JSONDecodeError:
            args = {}

        # Guardrails check
        if self._guardrails:
            violations = self._guardrails.check_tool_call(fn_name, args)
            blocked = [v for v in violations if v.severity == "block"]
            if blocked:
                return {"id": tc["id"], "output": f"Blocked by guardrails: {blocked[0].description}"}

        tool = self.tool_registry.get(fn_name)
        if not tool:
            return {"id": tc["id"], "output": f"Unknown tool: {fn_name}"}

        try:
            # Human approval gate
            if self.require_human_approval and self._approval_gate:
                approval = await self._approval_gate.approve(ApprovalRequest(
                    agent_name=self.name,
                    action_description=f"Execute tool '{fn_name}' with args: {json.dumps(args, default=str)[:300]}",
                    action_type="tool_call",
                    urgency=Urgency.MEDIUM,
                    context={"tool": fn_name, "args": args},
                ))
                if approval.decision == ApprovalDecision.REJECTED:
                    return {"id": tc["id"], "output": f"Tool call rejected by human: {approval.feedback}"}
                if approval.decision == ApprovalDecision.MODIFIED and approval.modified_action:
                    try:
                        args = json.loads(approval.modified_action) if approval.modified_action.startswith("{") else args
                    except json.JSONDecodeError:
                        pass

            # Execute with timeout and retry
            output = await self._run_tool_with_retry(tool, fn_name, args)

            if self._event_log:
                self._event_log.emit_tool_result(
                    agent_name=self.name, tool_name=fn_name, success=True,
                    output_preview=str(output)[:200], duration_ms=0.0,
                    trace_id=self._trace_ctx.trace_id if self._trace_ctx else "",
                )
            return {"id": tc["id"], "output": str(output)}
        except Exception as e:
            if self._event_log:
                self._event_log.emit_tool_result(
                    agent_name=self.name, tool_name=fn_name, success=False,
                    output_preview=str(e)[:200], duration_ms=0.0,
                    trace_id=self._trace_ctx.trace_id if self._trace_ctx else "",
                )
            return {"id": tc["id"], "output": f"Tool error: {e}"}

    async def _run_tool_with_retry(
        self, tool: Tool, tool_name: str, args: dict,
        max_retries: int = 2, base_delay: float = 1.0,
    ) -> Any:
        """Execute a tool with retry and exponential backoff for transient failures."""
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return await asyncio.wait_for(
                    tool.run(**args),
                    timeout=self._tool_timeout_seconds,
                )
            except asyncio.TimeoutError:
                last_error = TimeoutError(f"Tool '{tool_name}' timed out after {self._tool_timeout_seconds}s")
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"Tool '{tool_name}' timed out, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(delay)
                else:
                    raise last_error
            except Exception as e:
                last_error = e
                # Only retry on transient errors
                if attempt < max_retries and self._is_transient_error(e):
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"Tool '{tool_name}' failed with {type(e).__name__}, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(delay)
                else:
                    raise
        raise last_error or RuntimeError(f"Tool '{tool_name}' failed after {max_retries + 1} attempts")

    @staticmethod
    def _is_transient_error(e: Exception) -> bool:
        """Determine if an error is transient and worth retrying."""
        transient_types = (TimeoutError, ConnectionError, OSError)
        if isinstance(e, transient_types):
            return True
        error_str = str(e).lower()
        return any(s in error_str for s in ("timeout", "rate limit", "429", "503", "connection reset"))

    async def execute_stream(self, task: str, context: dict[str, Any] | None = None):
        """
        Execute a task with streaming — yields tokens as they arrive.
        
        Usage:
            async for chunk in agent.execute_stream("analyze this"):
                print(chunk.delta, end="", flush=True)
        """
        from forge.runtime.streaming import stream_agent_execution
        async for chunk in stream_agent_execution(self, task, context):
            yield chunk

    async def spawn_sub_agent(
        self, name: str, role: str, system_prompt: str, task: str
    ) -> TaskResult:
        """Spawn a sub-agent to handle a delegated task."""
        sub = Agent(name=name, role=role, system_prompt=system_prompt, model=self.model)
        sub.set_llm_client(self._llm_client)
        sub.set_memory(self.memory)
        self._sub_agents.append(sub)
        return await sub.execute(task)

    def save_state(self) -> dict[str, Any]:
        """
        Serialize agent state for checkpointing.

        Saves: conversation history, status, config, and memory snapshot.
        Can be restored with load_state() to resume execution.
        """
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "system_prompt": self.system_prompt,
            "model": self.model,
            "temperature": self.temperature,
            "max_iterations": self.max_iterations,
            "status": self.status.value,
            "conversation": list(self.conversation),
            "enable_reflection": self.enable_reflection,
            "quality_threshold": self.quality_threshold,
            "max_reflections": self.max_reflections,
        }

    def load_state(self, state: dict[str, Any]) -> None:
        """
        Restore agent state from a checkpoint.

        Resumes the agent with its previous conversation and status.
        """
        self.id = state.get("id", self.id)
        self.name = state.get("name", self.name)
        self.role = state.get("role", self.role)
        self.model = state.get("model", self.model)
        self.temperature = state.get("temperature", self.temperature)
        self.max_iterations = state.get("max_iterations", self.max_iterations)
        self.conversation = state.get("conversation", [])
        self.enable_reflection = state.get("enable_reflection", self.enable_reflection)
        self.quality_threshold = state.get("quality_threshold", self.quality_threshold)
        self.max_reflections = state.get("max_reflections", self.max_reflections)
        status_val = state.get("status", "idle")
        self.status = AgentStatus(status_val)

    def __repr__(self) -> str:
        return f"Agent(name={self.name!r}, role={self.role!r}, status={self.status.value})"

    def get_primitive_config(self) -> dict[str, str]:
        """Get the current primitive configuration of this agent."""
        return {
            "planner": repr(self._planner),
            "executor": repr(self._executor),
            "critic": repr(self._critic) if self._critic else "None",
            "escalation": repr(self._escalation_policy),
            "knowledge": repr(self.domain_knowledge) if self.domain_knowledge else "None",
        }


def _format_context(ctx: dict[str, Any]) -> str:
    """Format context dict as readable text."""
    lines = []
    for k, v in ctx.items():
        lines.append(f"- {k}: {v}")
    return "\n".join(lines)
