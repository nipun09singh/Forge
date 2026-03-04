"""Command Tool — sandboxed shell command execution for agent tools."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from forge.runtime.tools import Tool, ToolParameter

logger = logging.getLogger(__name__)

# Commands that are ALWAYS blocked (security)
BLOCKED_PATTERNS = [
    "rm -rf /",
    "rm -rf /*",
    "del /s /q c:\\",
    "format c:",
    "mkfs",
    "dd if=",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    ":(){:|:&};:",        # Fork bomb
    "curl | bash",
    "curl | sh",
    "wget | bash",
    "wget | sh",
    "> /dev/sda",
    "chmod -R 777 /",
    "mv / ",
]


def _is_command_safe(command: str) -> tuple[bool, str]:
    """Check if a command is safe to execute."""
    cmd_lower = command.lower().strip()

    for blocked in BLOCKED_PATTERNS:
        if blocked in cmd_lower:
            return False, f"Blocked dangerous pattern: '{blocked}'"

    # Block piping to shell interpreters from network tools
    if (("curl " in cmd_lower or "wget " in cmd_lower) and
        ("|" in cmd_lower and any(sh in cmd_lower.split("|")[-1] for sh in ["bash", "sh", "zsh", "python", "perl"]))):
        return False, "Blocked: piping network output to shell interpreter"

    return True, ""


async def run_command(
    command: str,
    workdir: str = ".",
    timeout: int = 30,
    shell: bool = True,
) -> str:
    """
    Execute a shell command in a sandboxed subprocess.

    Returns JSON with exit_code, stdout, stderr, and duration.
    Commands are checked against a blocklist for safety.
    """
    # Safety check
    safe, reason = _is_command_safe(command)
    if not safe:
        return json.dumps({
            "exit_code": -1,
            "stdout": "",
            "stderr": f"BLOCKED: {reason}",
            "blocked": True,
            "command": command,
        })

    # Ensure workdir exists
    work_path = Path(workdir).resolve()
    work_path.mkdir(parents=True, exist_ok=True)

    start_time = time.time()

    try:
        # Run the command
        if platform.system() == "Windows":
            process = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=str(work_path),
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                )
            )
        else:
            process = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    command if shell else shlex.split(command),
                    shell=shell,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=str(work_path),
                )
            )

        duration_ms = (time.time() - start_time) * 1000

        result = {
            "exit_code": process.returncode,
            "stdout": process.stdout[:10000] if process.stdout else "",
            "stderr": process.stderr[:5000] if process.stderr else "",
            "duration_ms": round(duration_ms, 1),
            "command": command,
            "workdir": str(work_path),
            "success": process.returncode == 0,
        }

        if process.returncode != 0:
            logger.warning(f"Command failed (exit {process.returncode}): {command[:80]}")
        else:
            logger.info(f"Command succeeded: {command[:80]} ({duration_ms:.0f}ms)")

        return json.dumps(result, default=str)

    except subprocess.TimeoutExpired:
        duration_ms = (time.time() - start_time) * 1000
        return json.dumps({
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds",
            "duration_ms": round(duration_ms, 1),
            "command": command,
            "success": False,
            "timeout": True,
        })
    except Exception as e:
        return json.dumps({
            "exit_code": -1,
            "stdout": "",
            "stderr": str(e),
            "command": command,
            "success": False,
            "error": str(e),
        })


def create_command_tool(default_workdir: str = "./workspace", default_timeout: int = 30) -> Tool:
    """Create a sandboxed command execution tool."""
    return Tool(
        name="run_command",
        description=(
            "Execute a shell command in a sandboxed subprocess. "
            "Use for: running scripts, installing packages, building projects, running tests, "
            "git operations, and any CLI tasks. "
            "Returns: exit_code, stdout, stderr, duration. "
            "Dangerous commands (rm -rf /, format, etc.) are blocked."
        ),
        parameters=[
            ToolParameter(name="command", type="string", description="The shell command to execute"),
            ToolParameter(name="workdir", type="string", description="Working directory (default: ./workspace)", required=False),
            ToolParameter(name="timeout", type="integer", description="Timeout in seconds (default: 30, max: 300)", required=False),
        ],
        _fn=run_command,
    )
