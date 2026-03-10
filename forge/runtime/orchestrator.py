"""OrchestratorAgent — a single intelligent agent loop for building complete projects.

Based on 2025 research showing single-agent systems outperform multi-agent pipelines
for software development (UC Berkeley/DeepMind: 35% decline with multi-agent coordination).

Inspired by OpenAI Codex's agent loop: Think → Act → Observe → Repeat.

Instead of 13 agents with delegation chains, ONE orchestrator:
- Has ALL tools (file, command, HTTP, SQL, git, browser)
- Runs in an unbounded loop
- Reads the full project state before each decision
- Verifies every action (runs code, checks output)
- Keeps going until it decides the project meets quality standards
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from forge.runtime.types import LLMClient

from forge.runtime.guardrails import GuardrailsEngine
from forge.runtime.model_router import ModelRouter
from forge.runtime.observability import EventLog, TraceContext, MODEL_COSTS, Event, EventType
from forge.runtime.phase_gates import PhaseGateEnforcer
from forge.runtime.structured_outputs import parse_completion_signal
from forge.runtime.token_manager import TokenCounter, SemanticBudget
from forge.runtime.confidence import ConfidenceScorer, ConfidenceLevel

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorResult:
    """Result from an orchestrator run."""
    success: bool
    project_dir: str = ""
    files_created: list[str] = field(default_factory=list)
    iterations: int = 0
    duration_seconds: float = 0.0
    total_tokens: int = 0
    summary: str = ""
    quality_assessment: str = ""


class OrchestratorAgent:
    """
    A single intelligent agent loop that builds complete projects.

    Unlike the multi-agent pipeline (ProjectExecutor), this is ONE agent
    with ALL tools that keeps working until the project is done.

    The loop:
    1. Read the current project state (all files, structure)
    2. Think about what needs to happen next
    3. Do it (create files, run commands, fix bugs)
    4. Check if the project is complete and good enough
    5. If not → go to step 1
    6. If yes → done

    Usage:
        orch = OrchestratorAgent(llm_client, model="gpt-4o")
        result = await orch.build("Build an expense tracker CLI", workdir="./project")
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        model: str = "gpt-4o",
        max_iterations: int = 200,
        quality_bar: str = "production-ready",
        max_duration_seconds: float = 3600.0,
        max_cost_usd: float = 5.0,
        max_concurrent_tools: int = 5,
    ):
        self._llm_client: LLMClient | None = llm_client
        self.model = model
        self.max_iterations = max_iterations
        self.quality_bar = quality_bar
        self.max_duration_seconds = max_duration_seconds
        self.max_cost_usd = max_cost_usd
        self._max_concurrent_tools = max_concurrent_tools
        self._tools: list[Any] = []
        self._tool_map: dict[str, Any] = {}
        self._tool_library: dict = {}
        self._event_log: EventLog | None = None
        self._trace_ctx: TraceContext | None = None
        self._guardrails: GuardrailsEngine | None = None
        self._model_router: ModelRouter | None = None
        self._token_counter = TokenCounter(model=self.model)
        self._confidence_scorer = ConfidenceScorer()

    def set_llm_client(self, client: LLMClient | None) -> None:
        self._llm_client = client

    def set_event_log(self, log: EventLog) -> None:
        self._event_log = log

    def set_trace_context(self, ctx: TraceContext) -> None:
        self._trace_ctx = ctx

    def set_guardrails(self, guardrails: GuardrailsEngine) -> None:
        self._guardrails = guardrails

    def set_model_router(self, router: ModelRouter) -> None:
        """Set smart model router for cost-optimized LLM selection."""
        self._model_router = router

    async def _execute_single_tool_call(
        self, tc, project_dir, phase_enforcer, files_created,
    ) -> dict[str, Any]:
        """Execute a single tool call with all pre-checks. Returns a result dict.

        The returned dict contains the standard ``role``/``content``/``tool_call_id``
        fields plus a private ``_semantic_tag`` used by the caller to tag the
        message for the semantic budget.
        """
        fn_name = tc.function.name
        try:
            args = json.loads(tc.function.arguments)
        except json.JSONDecodeError:
            args = {}

        tool = self._tool_map.get(fn_name)

        # Phase gate check — block wrong-phase tools
        allowed, phase_reason = phase_enforcer.is_tool_allowed(fn_name)
        if not allowed:
            return {
                "role": "tool",
                "content": f"⛔ Phase gate: {phase_reason}",
                "tool_call_id": tc.id,
                "_semantic_tag": "tool_results",
            }

        # Guardrails check
        if self._guardrails:
            violations = self._guardrails.check_tool_call(fn_name, args)
            blocked = [v for v in violations if v.severity == "block"]
            if blocked:
                return {
                    "role": "tool",
                    "content": f"Blocked by guardrails: {blocked[0].description}",
                    "tool_call_id": tc.id,
                    "_semantic_tag": "tool_results",
                }

        if not tool:
            return {
                "role": "tool",
                "content": f"Unknown tool: {fn_name}",
                "tool_call_id": tc.id,
                "_semantic_tag": "tool_results",
            }

        # Confidence-gated autonomy check
        confidence = self._confidence_scorer.score_tool_call(fn_name, args)
        if confidence.level == ConfidenceLevel.LOW:
            logger.warning(
                f"LOW confidence ({confidence.score:.2f}) for tool '{fn_name}': {confidence.reasoning}"
            )
            if self._event_log:
                self._event_log.emit(Event(
                    event_type=EventType.TOOL_USE,
                    agent_name="orchestrator",
                    data={"tool": fn_name, "confidence": confidence.score, "confidence_level": "low", "reasoning": confidence.reasoning},
                    level="warning",
                    trace_id=self._trace_ctx.trace_id if self._trace_ctx else "",
                ))
            return {
                "role": "tool",
                "content": json.dumps({
                    "warning": f"LOW CONFIDENCE ({confidence.score:.2f}): {confidence.reasoning}",
                    "action_required": "This tool call has low confidence. The tool was NOT executed. Please reconsider or provide more context before retrying.",
                    "tool_name": fn_name,
                    "blocked": True,
                }),
                "tool_call_id": tc.id,
                "_semantic_tag": None,
            }
        elif confidence.level == ConfidenceLevel.MEDIUM:
            logger.info(
                f"  ⚠️ Medium confidence ({confidence.score:.2f}): {confidence.reasoning}"
            )

        try:
            # Set workdir for command/file tools
            if fn_name == "run_command" and "workdir" not in args:
                args["workdir"] = str(project_dir)
            if fn_name == "read_write_file":
                if "path" in args and not os.path.isabs(args["path"]):
                    args["path"] = str(project_dir / args["path"])

            if self._event_log:
                self._event_log.emit_tool_use(
                    agent_name="orchestrator",
                    tool_name=fn_name,
                    args=args,
                    trace_id=self._trace_ctx.trace_id if self._trace_ctx else "",
                )

            _tool_start = time.time()
            output = await tool.run(**args)
            _tool_duration = (time.time() - _tool_start) * 1000
            logger.info(f"  🔧 {fn_name}: {str(output)[:80]}")

            if self._event_log:
                self._event_log.emit_tool_result(
                    agent_name="orchestrator", tool_name=fn_name, success=True,
                    output_preview=str(output)[:200], duration_ms=_tool_duration,
                    trace_id=self._trace_ctx.trace_id if self._trace_ctx else "",
                )

            # Track files created during the loop
            if fn_name == "read_write_file" and "path" in args:
                rel = os.path.relpath(args["path"], str(project_dir))
                if rel not in files_created and not rel.startswith(".."):
                    files_created.append(rel)
                    phase_enforcer.record_file_created(rel)

            phase_enforcer.record_tool_use(fn_name)
            if fn_name == "run_command":
                phase_enforcer.record_command_output(
                    args.get("command", ""), str(output)
                )

            # Determine semantic tag
            if fn_name in ("web_search", "browse_web"):
                tag = "research"
            elif fn_name == "read_write_file" and args.get("action") == "write" and any(
                kw in str(args.get("path", "")).lower() for kw in ("spec", "plan", "design", "architecture")
            ):
                tag = "spec"
            else:
                tag = "tool_results"

            return {
                "role": "tool",
                "content": str(output)[:5000],
                "tool_call_id": tc.id,
                "_semantic_tag": tag,
            }
        except Exception as e:
            logger.warning(f"  ❌ {fn_name} error: {e}")
            if self._event_log:
                self._event_log.emit_tool_result(
                    agent_name="orchestrator", tool_name=fn_name, success=False,
                    output_preview=str(e)[:200], duration_ms=(time.time() - _tool_start) * 1000,
                    trace_id=self._trace_ctx.trace_id if self._trace_ctx else "",
                )
            return {
                "role": "tool",
                "content": f"Error: {e}",
                "tool_call_id": tc.id,
                "_semantic_tag": "tool_results",
            }

    def _ensure_tools(self) -> None:
        """Load primitive tools + discover_tool. The AI discovers everything else at runtime."""
        if self._tools:
            return
        try:
            from forge.runtime.integrations import BuiltinToolkit
            # Start with exactly 5 primitives
            self._tools = BuiltinToolkit.primitives()
            self._tool_library = BuiltinToolkit.library()
            # Add discover_tool as the 6th tool — the gateway to the library
            self._tools.append(self._create_discover_tool())
            self._tool_map = {t.name: t for t in self._tools}
        except ImportError:
            logger.warning("BuiltinToolkit not available")
            self._tool_library = {}

    def _create_discover_tool(self) -> Any:
        """Create the discover_tool meta-tool for runtime tool discovery."""
        from forge.runtime.tools import Tool, ToolParameter

        async def discover_tool(action: str = "list", tool_name: str = "") -> str:
            """Discover and load tools from the Forge library.

            Actions:
              - list: Show all available library tools with descriptions
              - load: Load a specific tool by name and make it available
            """
            if action == "list":
                catalog = []
                for name, entry in self._tool_library.items():
                    catalog.append({
                        "name": name,
                        "description": entry.get("description", ""),
                        "category": entry.get("category", ""),
                        "required_env_vars": entry.get("env_vars", []),
                    })
                return json.dumps(catalog, indent=2)
            elif action == "load":
                if not tool_name:
                    return json.dumps({"error": "tool_name is required for load action"})
                if tool_name in self._tool_map:
                    return json.dumps({"status": "already_loaded", "tool": tool_name})
                from forge.runtime.integrations import BuiltinToolkit
                tool = BuiltinToolkit.get_tool(tool_name)
                if tool is None:
                    return json.dumps({"error": f"Unknown tool: {tool_name}"})
                self._tools.append(tool)
                self._tool_map[tool.name] = tool
                return json.dumps({"status": "loaded", "tool": tool.name})
            else:
                return json.dumps({"error": f"Unknown action: {action}. Use 'list' or 'load'."})

        return Tool(
            name="discover_tool",
            description=(
                "Discover and load tools from the Forge library. "
                "Use action='list' to browse available integrations, "
                "action='load' with tool_name to activate one."
            ),
            parameters=[
                ToolParameter(name="action", type="string", description="Action to perform: 'list' or 'load'", required=False, default="list", enum=["list", "load"]),
                ToolParameter(name="tool_name", type="string", description="Name of the tool to load (required for 'load' action)", required=False, default=""),
            ],
            _fn=discover_tool,
        )

    def _get_tools_schema(self) -> list[dict]:
        """Get OpenAI function-calling schema for all tools."""
        self._ensure_tools()
        return [t.to_openai_schema() for t in self._tools]

    async def build(
        self,
        task: str,
        workdir: str = "./workspace/orchestrator",
    ) -> OrchestratorResult:
        """
        Build a complete project from a task description.

        The orchestrator works in a loop: think → act → observe → repeat
        until the project is done or max_iterations reached.
        """
        if not self._llm_client:
            return OrchestratorResult(success=False, summary="No LLM client")

        self._ensure_tools()
        project_dir = Path(workdir).resolve()
        project_dir.mkdir(parents=True, exist_ok=True)
        os.environ["AGENCY_DATA_DIR"] = str(project_dir)

        start_time = time.time()
        files_created: list[str] = []
        phase_enforcer = PhaseGateEnforcer(project_dir)
        total_tokens = 0
        total_cost = 0.0

        logger.info(f"=== ORCHESTRATOR START ===")
        logger.info(f"Task: {task[:100]}")
        logger.info(f"Workdir: {project_dir}")
        logger.info(f"Tools: {[t.name for t in self._tools]}")
        logger.info(f"Max iterations: {self.max_iterations}")

        # Initialize git
        try:
            git_tool = self._tool_map.get("git_operation")
            if git_tool:
                await git_tool.run(operation="init", workdir=str(project_dir))
        except Exception as e:
            logger.debug(f"Git init skipped: {e}")

        # Find Python executable
        python_path = "python"
        import sys
        for p in [
            sys.executable,
            os.path.join(os.path.dirname(sys.executable), "python.exe"),
            "python3",
        ]:
            if os.path.exists(p):
                python_path = p
                break

        # Build the system prompt for the orchestrator
        system_prompt = (
            "You are an autonomous AI engineer with unlimited capability. You can research, "
            "design, build, test, debug, and deploy complete production systems — entirely on your own.\n\n"
            f"PROJECT TASK: {task}\n"
            f"WORKING DIRECTORY: {project_dir}\n"
            f"PYTHON EXECUTABLE: {python_path}\n\n"
            
            "═══ HOW YOU WORK ═══\n\n"
            
            "PHASE 1 — RESEARCH:\n"
            "Use web_search and browse_web to research the domain, APIs, and best practices.\n"
            "- Read API documentation for any services needed\n"
            "- Understand the domain: what does this business actually need?\n"
            "- Save research artifacts as .json or .md files only.\n\n"
            
            "PHASE 2 — PLAN:\n"
            "Create a SPEC.md with architecture, file structure, dependencies, and acceptance criteria.\n"
            "- Architecture: what components, how they connect\n"
            "- File structure: list every file you'll create\n"
            "- Dependencies: what packages/APIs are needed\n"
            "- Acceptance criteria: how to verify it works\n\n"
            
            "PHASE 3 — BUILD:\n"
            "Create all project files using read_write_file.\n"
            "- Use read_write_file to create every source file\n"
            f"- Use run_command to install packages: '{python_path} -m pip install <package>'\n"
            "- Create proper project structure (src/, tests/, templates/, etc.)\n"
            "- Include: source code, tests, config, README, requirements.txt\n\n"
            
            "PHASE 4 — VERIFY:\n"
            f"Run tests with pytest ('{python_path} -m pytest tests/'), fix failures,\n"
            "ensure README and requirements.txt exist.\n"
            "- If tests fail: READ the error output carefully, FIX the code, re-run\n"
            "- Keep fixing until everything works\n\n"
            
            "PHASE 5 — SHIP:\n"
            "Initialize git repo, commit all files.\n"
            "- git init, git add, git commit\n"
            "- Ensure code is production-quality, not a prototype\n\n"
            
            "═══ RULES ═══\n"
            "1. ALWAYS use your tools. Never just describe what you'd do — DO IT.\n"
            "2. RESEARCH before building. Use browse_web to read docs for any API/SDK.\n"
            "3. TEST everything. Run the code. Fix errors. Repeat until it works.\n"
            "4. BUILD complete systems, not skeletons. Include ALL features requested.\n"
            "5. When you need an external service (Twilio, Stripe, Calendar, etc.):\n"
            "   → browse_web to read their documentation\n"
            "   → run_command to install their SDK\n"
            "   → create proper integration code with error handling\n"
            "6. For web dashboards: create real HTML with CSS styling.\n"
            f"7. Always use '{python_path}' not 'python' for running Python.\n"
            "8. When COMPLETELY satisfied the project is production-quality, respond with the JSON: {\"status\": \"DONE\", \"summary\": \"<brief summary>\"}. You may also simply say DONE.\n\n"
            
            "═══ AVAILABLE TOOLS ═══\n"
            "- read_write_file(action, path, content): Create/read/edit/list/delete files\n"
            "- run_command(command, workdir): Execute ANY shell command (install, test, build, deploy)\n"
            "- browse_web(url): Read ANY webpage (API docs, tutorials, references)\n"
            "- web_search(query): Search the internet (DuckDuckGo) for market research, docs, competitors\n"
            "- http_request(url, method, headers, body): Make HTTP requests to test APIs\n\n"
            "═══ TOOL LIBRARY ═══\n"
            "You have 5 primitive tools plus a `discover_tool` that lets you browse and load specialized "
            "integrations (SMS, payments, calendar, etc.) from the Forge library. "
            "Use `discover_tool(action='list')` during RESEARCH to see what's available, then "
            "`discover_tool(action='load', tool_name='send_sms')` when you need it.\n\n"
            "START BUILDING NOW. Create the project structure first, then implement each file."
        )

        conversation: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Build this project: {task}. Create all necessary files using your tools."},
        ]

        # Semantic context budget manager
        semantic_budget = SemanticBudget(model=self.model)
        semantic_budget.tag_message(conversation[0], "system")
        semantic_budget.tag_message(conversation[1], "conversation")

        tools_schema = self._get_tools_schema()
        iterations = 0
        project_complete = False

        for iteration in range(self.max_iterations):
            iterations = iteration + 1
            _iter_span = self._trace_ctx.new_span() if self._trace_ctx else None
            logger.info(f"\n--- Iteration {iterations}/{self.max_iterations} ---")

            elapsed = time.time() - start_time
            if elapsed > self.max_duration_seconds:
                logger.warning(f"  ⏰ Orchestrator timeout after {elapsed:.0f}s (limit: {self.max_duration_seconds}s)")
                break

            phase_enforcer.tick()

            try:
                # Smart model routing for cost optimization
                _effective_model = self.model
                if self._model_router:
                    task_preview = conversation[-1].get("content", "") if conversation else ""
                    _effective_model = self._model_router.select_model(
                        task=task_preview[:500],
                        messages=conversation,
                        has_tools=bool(tools_schema),
                        agent_role="orchestrator",
                    )

                # THINK: Call LLM with current conversation + tools
                kwargs: dict[str, Any] = {
                    "model": _effective_model,
                    "messages": conversation,
                    "temperature": 0.3,
                }
                if tools_schema:
                    kwargs["tools"] = tools_schema

                if self._event_log:
                    self._event_log.emit_llm_call(
                        agent_name="orchestrator",
                        model=_effective_model,
                        messages_count=len(conversation),
                        tools_count=len(tools_schema) if tools_schema else 0,
                        trace_id=self._trace_ctx.trace_id if self._trace_ctx else "",
                    )

                _llm_start = time.time()
                response = await self._llm_client.chat.completions.create(**kwargs)
                _llm_duration = (time.time() - _llm_start) * 1000
                choice = response.choices[0]

                if self._event_log and hasattr(response, 'usage') and response.usage:
                    self._event_log.emit_llm_response(
                        agent_name="orchestrator",
                        model=_effective_model,
                        prompt_tokens=getattr(response.usage, 'prompt_tokens', 0) or 0,
                        completion_tokens=getattr(response.usage, 'completion_tokens', 0) or 0,
                        has_tool_calls=bool(choice.message.tool_calls),
                        duration_ms=_llm_duration,
                        trace_id=self._trace_ctx.trace_id if self._trace_ctx else "",
                    )

                # Track token usage and cost using per-model rates
                if hasattr(response, 'usage') and response.usage:
                    prompt_tok = getattr(response.usage, 'prompt_tokens', 0) or 0
                    completion_tok = getattr(response.usage, 'completion_tokens', 0) or 0
                    total_tokens += prompt_tok + completion_tok
                    costs = MODEL_COSTS.get(_effective_model, MODEL_COSTS.get("gpt-4", {"input": 0.03, "output": 0.06}))
                    total_cost += (prompt_tok / 1000 * costs["input"]) + (completion_tok / 1000 * costs["output"])

                    # Record outcome in model router feedback loop
                    if self._model_router:
                        self._model_router.record_outcome(
                            task_id=task_preview[:500] if conversation else "orchestrator",
                            model_used=_effective_model,
                            success=True,
                            tokens_used=prompt_tok + completion_tok,
                            cost=(prompt_tok / 1000 * costs["input"]) + (completion_tok / 1000 * costs["output"]),
                        )

                # Check cost budget
                if total_cost > self.max_cost_usd:
                    logger.warning(f"  💰 Cost budget exceeded: ${total_cost:.4f} > ${self.max_cost_usd:.2f}")
                    break

                # ACT: If tool calls, execute them
                if choice.message.tool_calls:
                    # Add assistant message with tool calls
                    conversation.append({
                        "role": "assistant",
                        "content": choice.message.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                            }
                            for tc in choice.message.tool_calls
                        ],
                    })
                    semantic_budget.tag_message(conversation[-1], "conversation")

                    # Execute tool calls in parallel with concurrency limit
                    semaphore = asyncio.Semaphore(self._max_concurrent_tools)

                    async def _run_one(tc):
                        async with semaphore:
                            return await self._execute_single_tool_call(
                                tc, project_dir, phase_enforcer, files_created,
                            )

                    results = await asyncio.gather(
                        *[_run_one(tc) for tc in choice.message.tool_calls],
                        return_exceptions=True,
                    )

                    # Append results to conversation in original order
                    for i, result in enumerate(results):
                        if isinstance(result, Exception):
                            tc = choice.message.tool_calls[i]
                            msg = {
                                "role": "tool",
                                "content": f"Error: {result}",
                                "tool_call_id": tc.id,
                            }
                            conversation.append(msg)
                            semantic_budget.tag_message(msg, "tool_results")
                        else:
                            tag = result.pop("_semantic_tag", "tool_results")
                            conversation.append(result)
                            if tag:
                                semantic_budget.tag_message(result, tag)

                    continue  # Loop back for more thinking

                # OBSERVE: No tool calls — agent produced text response
                text_output = choice.message.content or ""
                
                # Content filtering on output
                if self._guardrails:
                    output_violations = self._guardrails.check_output(text_output)
                    if output_violations:
                        text_output = self._guardrails.redact_output(text_output)
                        logger.debug(f"  🛡️ Output filtered: {[v.rule for v in output_violations]}")
                
                conversation.append({"role": "assistant", "content": text_output})
                semantic_budget.tag_message(conversation[-1], "conversation")

                # Check for completion signal (structured JSON or string patterns)
                completion = parse_completion_signal(text_output)
                if completion and len(files_created) >= 1:
                    # Score output confidence before accepting completion
                    output_confidence = self._confidence_scorer.score_output(text_output, task)
                    if output_confidence.level == ConfidenceLevel.LOW:
                        # Don't accept LOW confidence completion — nudge to improve
                        conversation.append({"role": "user", "content": f"Your response has low confidence ({output_confidence.score:.2f}): {output_confidence.reasoning}. Please improve your answer or use tools to verify."})
                        semantic_budget.tag_message(conversation[-1], "conversation")
                        continue

                    # Enforce phase gates before accepting completion
                    can_complete, blockers = phase_enforcer.can_complete()
                    if not can_complete:
                        feedback = phase_enforcer.get_blocker_feedback()
                        conversation.append({"role": "user", "content": feedback})
                        semantic_budget.tag_message(conversation[-1], "conversation")
                        logger.info(f"  ⛔ Completion blocked: {len(blockers)} unmet requirements")
                        continue
                    project_complete = True
                    logger.info(f"  ✅ Agent declares project complete: {completion.summary[:80]}")
                    break

                # If agent just talks without acting, nudge with phase context
                phase_instruction = phase_enforcer.get_phase_instruction()
                conversation.append({
                    "role": "user",
                    "content": (
                        "You haven't used any tools in this response. "
                        "Please USE your tools (read_write_file, run_command) to actually create files. "
                        "Don't describe what you would do — DO it.\n" +
                        phase_instruction
                    ),
                })
                semantic_budget.tag_message(conversation[-1], "conversation")

            except Exception as e:
                logger.error(f"  Iteration {iterations} error: {e}")
                conversation.append({
                    "role": "user",
                    "content": f"An error occurred: {e}. Please continue building the project.",
                })
                semantic_budget.tag_message(conversation[-1], "conversation")

            if _iter_span and self._trace_ctx:
                self._trace_ctx.end_span()

            # Smart context management — semantic budget pruning
            conversation = semantic_budget.prune_by_budget(conversation)

        # OBSERVE: Scan for created files
        for f in project_dir.rglob("*"):
            if f.is_file() and ".git" not in str(f):
                rel = str(f.relative_to(project_dir))
                if rel not in files_created:
                    files_created.append(rel)

        duration = time.time() - start_time

        # Build summary
        summary_lines = [
            f"Task: {task[:80]}",
            f"Status: {'COMPLETE' if project_complete else 'PARTIAL'}",
            f"Iterations: {iterations}",
            f"Files created: {len(files_created)}",
            f"Duration: {duration:.1f}s",
            "",
            "Files:",
        ]
        for f in sorted(files_created):
            summary_lines.append(f"  {f}")

        result = OrchestratorResult(
            success=project_complete,
            project_dir=str(project_dir),
            files_created=sorted(files_created),
            iterations=iterations,
            duration_seconds=round(duration, 1),
            total_tokens=total_tokens,
            summary="\n".join(summary_lines),
        )

        logger.info(f"\n=== ORCHESTRATOR COMPLETE ===")
        logger.info(result.summary)

        return result

    def __repr__(self) -> str:
        return f"OrchestratorAgent(model={self.model}, max_iter={self.max_iterations})"
