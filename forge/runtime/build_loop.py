"""Self-correcting build loop — write, build, test, fix, repeat.

This is the "hot loop" that makes AI coding agents actually work.
Instead of writing code once and hoping, it:
1. Writes code
2. Runs build/test
3. If fails: reads the error, asks LLM to fix, writes fixed code
4. Repeats until tests pass or max attempts reached

This is what Devin, SWE-Agent, and OpenAI Codex do internally.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BuildResult:
    """Result of a build loop execution."""
    success: bool
    attempts: int
    final_output: str = ""
    files_created: list[str] = field(default_factory=list)
    build_log: list[dict[str, Any]] = field(default_factory=list)
    total_duration_ms: float = 0.0


class BuildLoop:
    """
    Self-correcting build-test-fix loop.
    
    The pattern:
      write code → run build → check errors → fix code → run build → ...
    
    Converges in 1-5 attempts for most tasks.
    """

    def __init__(
        self,
        max_attempts: int = 5,
        build_command: str = "",
        test_command: str = "",
        lint_command: str = "",
    ):
        self.max_attempts = max_attempts
        self.build_command = build_command
        self.test_command = test_command
        self.lint_command = lint_command

    async def run(
        self,
        task: str,
        workdir: str = "./workspace",
        llm_client: Any = None,
        model: str = "gpt-4",
    ) -> BuildResult:
        """
        Execute the build loop for a task.
        
        1. Ask LLM to write code
        2. Save files
        3. Run build/test commands
        4. If failure: feed errors back to LLM, get fix, repeat
        """
        from forge.runtime.integrations.command_tool import run_command
        from forge.runtime.integrations.file_tool import create_file_tool
        import os

        os.makedirs(workdir, exist_ok=True)
        os.environ.setdefault("AGENCY_DATA_DIR", workdir)
        _file_tool = create_file_tool(workdir)
        read_write_file = _file_tool._fn

        start_time = time.time()
        build_log = []
        files_created = []

        if not llm_client:
            return BuildResult(success=False, attempts=0, final_output="No LLM client available")

        # Initial conversation
        messages = [
            {"role": "system", "content": (
                "You are a software engineer. Write real, working code.\n"
                "When writing code, output it in this format:\n"
                "```filename.ext\n<code>\n```\n"
                "You can output multiple files. Each file block starts with ```filename\n"
                "After writing, I will try to build/run your code and report any errors.\n"
                "If there are errors, fix them.\n"
                "Focus on making the code WORK, not on explaining it."
            )},
            {"role": "user", "content": task},
        ]

        for attempt in range(self.max_attempts):
            logger.info(f"Build loop attempt {attempt + 1}/{self.max_attempts}")

            # Step 1: Ask LLM to write/fix code
            try:
                response = await llm_client.chat.completions.create(
                    model=model, messages=messages, temperature=0.3,
                )
                llm_output = response.choices[0].message.content or ""
                messages.append({"role": "assistant", "content": llm_output})
            except Exception as e:
                build_log.append({"attempt": attempt + 1, "phase": "llm_call", "error": str(e)})
                continue

            # Step 2: Extract and save code files
            extracted_files = self._extract_code_blocks(llm_output)
            for filename, code in extracted_files.items():
                filepath = f"{workdir}/{filename}"
                # Create parent directories
                parent = Path(filepath).parent
                if parent:
                    os.makedirs(parent, exist_ok=True)
                
                await read_write_file("write", filepath, code)
                if filename not in files_created:
                    files_created.append(filename)
                logger.info(f"  Wrote: {filename} ({len(code)} chars)")

            if not extracted_files:
                # LLM didn't output code blocks — it might have just explained
                build_log.append({
                    "attempt": attempt + 1,
                    "phase": "extract",
                    "note": "No code blocks found in LLM output",
                    "output_preview": llm_output[:200],
                })
                # Ask it to actually write the code
                messages.append({"role": "user", "content": (
                    "Please write the actual code. Output each file as:\n"
                    "```filename.ext\n<code>\n```"
                )})
                continue

            # Step 3: Run build/test commands
            all_passed = True
            error_output = ""

            for cmd_name, cmd in [("build", self.build_command), ("test", self.test_command), ("lint", self.lint_command)]:
                if not cmd:
                    continue

                result_json = await run_command(cmd, workdir=workdir, timeout=60)
                result = json.loads(result_json)

                build_log.append({
                    "attempt": attempt + 1,
                    "phase": cmd_name,
                    "command": cmd,
                    "exit_code": result.get("exit_code", -1),
                    "success": result.get("success", False),
                })

                if not result.get("success", False):
                    all_passed = False
                    error_output = result.get("stderr", "") or result.get("stdout", "")
                    logger.warning(f"  {cmd_name} FAILED: {error_output[:200]}")
                    break
                else:
                    logger.info(f"  {cmd_name} PASSED")

            # Step 4: If all passed, we're done!
            has_commands = bool(self.build_command or self.test_command or self.lint_command)
            if not has_commands:
                logger.warning("No build, test, or lint commands configured — cannot verify code")
            if all_passed and has_commands:
                duration = (time.time() - start_time) * 1000
                logger.info(f"Build loop SUCCESS in {attempt + 1} attempt(s)")
                return BuildResult(
                    success=True,
                    attempts=attempt + 1,
                    final_output=llm_output,
                    files_created=files_created,
                    build_log=build_log,
                    total_duration_ms=duration,
                )

            # Step 5: Feed errors back to LLM for fixing
            messages.append({"role": "user", "content": (
                f"The code has errors. Please fix them.\n\n"
                f"Error output:\n```\n{error_output[:2000]}\n```\n\n"
                f"Please output the COMPLETE fixed files (not just the changes)."
            )})

        # Max attempts exhausted
        duration = (time.time() - start_time) * 1000
        logger.warning(f"Build loop FAILED after {self.max_attempts} attempts")
        return BuildResult(
            success=False,
            attempts=self.max_attempts,
            final_output=f"Failed to produce working code after {self.max_attempts} attempts",
            files_created=files_created,
            build_log=build_log,
            total_duration_ms=duration,
        )

    def _extract_code_blocks(self, text: str) -> dict[str, str]:
        """Extract ```filename\ncode\n``` blocks from LLM output."""
        files = {}
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # Look for ```filename or ```language filename patterns
            if line.startswith("```") and len(line) > 3:
                # Extract filename from the opening fence
                header = line[3:].strip()
                # Skip pure language markers (```python, ```javascript, etc.)
                pure_languages = {"python", "javascript", "typescript", "html", "css", "json", "yaml", "yml",
                                  "bash", "sh", "sql", "markdown", "md", "toml", "xml", "java", "go", "rust",
                                  "c", "cpp", "c++", "ruby", "php", "swift", "kotlin", "dart", "r"}
                
                # Check if header looks like a filename (has extension or path separator)
                if "." in header or "/" in header or "\\" in header:
                    # It's a filename — possibly with language prefix like "python main.py"
                    parts = header.split()
                    filename = parts[-1] if len(parts) > 1 else parts[0]
                    
                    # Collect code until closing ```
                    code_lines = []
                    i += 1
                    while i < len(lines) and not lines[i].strip().startswith("```"):
                        code_lines.append(lines[i])
                        i += 1
                    
                    files[filename] = "\n".join(code_lines)
                elif header.lower() not in pure_languages:
                    # Treat as filename if it's not a known language
                    filename = header
                    code_lines = []
                    i += 1
                    while i < len(lines) and not lines[i].strip().startswith("```"):
                        code_lines.append(lines[i])
                        i += 1
                    files[filename] = "\n".join(code_lines)
            i += 1
        
        return files

    def __repr__(self) -> str:
        return f"BuildLoop(max_attempts={self.max_attempts}, build={self.build_command!r}, test={self.test_command!r})"
