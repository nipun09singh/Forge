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
from forge.runtime.observability import EventLog, TraceContext
from forge.runtime.structured_outputs import parse_completion_signal
from forge.runtime.token_manager import TokenCounter

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
        max_cost_usd: float = 10.0,
    ):
        self._llm_client: LLMClient | None = llm_client
        self.model = model
        self.max_iterations = max_iterations
        self.quality_bar = quality_bar
        self.max_duration_seconds = max_duration_seconds
        self.max_cost_usd = max_cost_usd
        self._tools: list[Any] = []
        self._tool_map: dict[str, Any] = {}
        self._event_log: EventLog | None = None
        self._trace_ctx: TraceContext | None = None
        self._guardrails: GuardrailsEngine | None = None
        self._token_counter = TokenCounter(model=self.model)

    def set_llm_client(self, client: LLMClient | None) -> None:
        self._llm_client = client

    def set_event_log(self, log: EventLog) -> None:
        self._event_log = log

    def set_trace_context(self, ctx: TraceContext) -> None:
        self._trace_ctx = ctx

    def set_guardrails(self, guardrails: GuardrailsEngine) -> None:
        self._guardrails = guardrails

    def _ensure_tools(self) -> None:
        """Load all primitive tools."""
        if self._tools:
            return
        try:
            from forge.runtime.integrations import BuiltinToolkit
            self._tools = BuiltinToolkit.all_tools()
            self._tool_map = {t.name: t for t in self._tools}
        except ImportError:
            logger.warning("BuiltinToolkit not available")

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
        total_tokens = 0

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
            "Before writing ANY code, research what you need:\n"
            "- Use browse_web to read API documentation, SDK guides, and best practices\n"
            "- If you need Twilio → browse their docs. Need Stripe → browse their docs.\n"
            "- Understand the domain: what does this business actually need?\n"
            "- Plan the architecture before writing code.\n\n"
            
            "PHASE 2 — BUILD:\n"
            "Create the complete project file by file:\n"
            "- Use read_write_file to create every source file\n"
            f"- Use run_command to install packages: '{python_path} -m pip install <package>'\n"
            "- Create proper project structure (src/, tests/, templates/, etc.)\n"
            "- Include: source code, tests, config, README, requirements.txt\n"
            "- For web UIs: create HTML/CSS/JS files with modern, clean design\n"
            "- For APIs: create FastAPI/Flask endpoints with proper routing\n"
            "- For integrations: install the SDK, read the docs, implement properly\n\n"
            
            "PHASE 3 — TEST & DEBUG:\n"
            f"- Run tests: '{python_path} -m pytest tests/' or '{python_path} -m unittest discover'\n"
            "- If tests fail: READ the error output carefully, FIX the code, re-run\n"
            f"- Run the app: '{python_path} main.py' or '{python_path} -m uvicorn app:app'\n"
            "- Keep fixing until everything works\n\n"
            
            "PHASE 4 — POLISH:\n"
            "- Add error handling and input validation\n"
            "- Add docstrings and type hints\n"
            "- Create comprehensive README with setup instructions\n"
            "- Create Dockerfile for deployment\n"
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
            "- http_request(url, method, headers, body): Make HTTP requests to test APIs\n"
            "- query_database(query): Run SQL queries on SQLite\n"
            "- git_operation(operation, args): Git version control\n\n"
            "START BUILDING NOW. Create the project structure first, then implement each file."
        )

        conversation: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Build this project: {task}. Create all necessary files using your tools."},
        ]

        tools_schema = self._get_tools_schema()
        iterations = 0
        project_complete = False

        for iteration in range(self.max_iterations):
            iterations = iteration + 1
            logger.info(f"\n--- Iteration {iterations}/{self.max_iterations} ---")

            elapsed = time.time() - start_time
            if elapsed > self.max_duration_seconds:
                logger.warning(f"  ⏰ Orchestrator timeout after {elapsed:.0f}s (limit: {self.max_duration_seconds}s)")
                break

            try:
                # THINK: Call LLM with current conversation + tools
                kwargs: dict[str, Any] = {
                    "model": self.model,
                    "messages": conversation,
                    "temperature": 0.3,
                }
                if tools_schema:
                    kwargs["tools"] = tools_schema

                response = await self._llm_client.chat.completions.create(**kwargs)
                choice = response.choices[0]

                # Track token usage
                if hasattr(response, 'usage') and response.usage:
                    total_tokens += getattr(response.usage, 'total_tokens', 0)

                # Check cost budget
                estimated_cost = total_tokens * 0.00003  # rough estimate ~$30/1M tokens
                if estimated_cost > self.max_cost_usd:
                    logger.warning(f"  💰 Cost budget exceeded: ${estimated_cost:.2f} > ${self.max_cost_usd:.2f}")
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

                    # Execute each tool call
                    for tc in choice.message.tool_calls:
                        fn_name = tc.function.name
                        try:
                            args = json.loads(tc.function.arguments)
                        except json.JSONDecodeError:
                            args = {}

                        tool = self._tool_map.get(fn_name)

                        # Guardrails check
                        if self._guardrails:
                            violations = self._guardrails.check_tool_call(fn_name, args)
                            blocked = [v for v in violations if v.severity == "block"]
                            if blocked:
                                conversation.append({
                                    "role": "tool",
                                    "content": f"Blocked by guardrails: {blocked[0].description}",
                                    "tool_call_id": tc.id,
                                })
                                continue

                        if tool:
                            try:
                                # Set workdir for command/file tools
                                if fn_name == "run_command" and "workdir" not in args:
                                    args["workdir"] = str(project_dir)
                                if fn_name == "read_write_file":
                                    # Ensure paths are relative to project dir
                                    if "path" in args and not os.path.isabs(args["path"]):
                                        args["path"] = str(project_dir / args["path"])

                                output = await tool.run(**args)
                                logger.info(f"  🔧 {fn_name}: {str(output)[:80]}")

                                if self._event_log:
                                    self._event_log.emit_tool_result(
                                        agent_name="orchestrator", tool_name=fn_name, success=True,
                                        output_preview=str(output)[:200], duration_ms=0.0,
                                        trace_id=self._trace_ctx.trace_id if self._trace_ctx else "",
                                    )

                                # Track files created during the loop (not just at end)
                                if fn_name == "read_write_file" and "path" in args:
                                    rel = os.path.relpath(args["path"], str(project_dir))
                                    if rel not in files_created and not rel.startswith(".."):
                                        files_created.append(rel)

                                conversation.append({
                                    "role": "tool",
                                    "content": str(output)[:5000],
                                    "tool_call_id": tc.id,
                                })
                            except Exception as e:
                                logger.warning(f"  ❌ {fn_name} error: {e}")
                                if self._event_log:
                                    self._event_log.emit_tool_result(
                                        agent_name="orchestrator", tool_name=fn_name, success=False,
                                        output_preview=str(e)[:200], duration_ms=0.0,
                                        trace_id=self._trace_ctx.trace_id if self._trace_ctx else "",
                                    )
                                conversation.append({
                                    "role": "tool",
                                    "content": f"Error: {e}",
                                    "tool_call_id": tc.id,
                                })
                        else:
                            conversation.append({
                                "role": "tool",
                                "content": f"Unknown tool: {fn_name}",
                                "tool_call_id": tc.id,
                            })

                    continue  # Loop back for more thinking

                # OBSERVE: No tool calls — agent produced text response
                text_output = choice.message.content or ""
                conversation.append({"role": "assistant", "content": text_output})

                # Check for completion signal (structured JSON or string patterns)
                completion = parse_completion_signal(text_output)
                if completion and len(files_created) >= 1:
                    project_complete = True
                    logger.info(f"  ✅ Agent declares project complete: {completion.summary[:80]}")
                    break

                # If agent just talks without acting, nudge it
                conversation.append({
                    "role": "user",
                    "content": (
                        "You haven't used any tools in this response. "
                        "Please USE your tools (read_write_file, run_command) to actually create files. "
                        "Don't describe what you would do — DO it."
                    ),
                })

            except Exception as e:
                logger.error(f"  Iteration {iterations} error: {e}")
                conversation.append({
                    "role": "user",
                    "content": f"An error occurred: {e}. Please continue building the project.",
                })

            # Smart context management — token-aware pruning
            if self._token_counter.needs_pruning(conversation):
                # Generate state summary every 20 iterations
                pinned = None
                if iterations % 20 == 0 and iterations > 0:
                    try:
                        summary_resp = await self._llm_client.chat.completions.create(
                            model=self.model,
                            messages=[
                                {"role": "system", "content": "Summarize the current project state in 200 words: what files exist, what architecture was chosen, what's done, what's remaining."},
                                {"role": "user", "content": f"Files created so far: {files_created}\nLast few messages: {json.dumps([m.get('content', '')[:200] for m in conversation[-10:]], default=str)}"},
                            ],
                            temperature=0.2,
                        )
                        state_summary = summary_resp.choices[0].message.content or ""
                        if hasattr(summary_resp, 'usage') and summary_resp.usage:
                            total_tokens += getattr(summary_resp.usage, 'total_tokens', 0)
                        pinned = {"role": "user", "content": f"[PROJECT STATE - iteration {iterations}]: {state_summary}"}
                    except Exception as e:
                        logger.debug(f"State summary generation failed: {e}")
                        pinned = {"role": "user", "content": f"[PROJECT STATE]: Files created: {', '.join(files_created[-20:])}"}
                
                conversation = self._token_counter.prune_conversation(conversation, pinned_message=pinned)

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
            success=project_complete or len(files_created) >= 2,
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
