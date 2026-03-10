"""Command Tool — sandboxed shell command execution for agent tools."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

from forge.runtime.tools import Tool, ToolParameter

if TYPE_CHECKING:
    from forge.runtime.policies import SecurityPolicy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Whitelist: only these base command names are allowed.
# Set FORGE_COMMAND_WHITELIST_DISABLED=1 to bypass (trusted environments).
# ---------------------------------------------------------------------------
ALLOWED_COMMANDS: frozenset[str] = frozenset({
    # Python
    "python", "python3", "python3.11", "python3.12", "python3.13", "py",
    "pip", "pip3", "pipx", "uv", "poetry", "conda",
    "pytest", "mypy", "ruff", "black", "isort", "flake8", "pylint", "pyright",
    # Node / JS
    "node", "npm", "npx", "yarn", "pnpm", "bun", "deno", "tsc", "tsx",
    "eslint", "prettier", "jest", "vitest", "mocha",
    # Build tools
    "make", "cmake", "cargo", "go", "rustc", "gcc", "g++", "javac", "java",
    "dotnet", "msbuild",
    # Version control
    "git", "gh", "svn",
    # File / text utilities
    "ls", "dir", "cat", "head", "tail", "grep", "rg", "find", "fd",
    "echo", "printf", "wc", "sort", "uniq", "cut", "awk", "sed", "tr",
    "diff", "patch", "tee", "xargs",
    # File management
    "mkdir", "cp", "mv", "touch", "ln", "rm", "rmdir",
    "xcopy", "copy", "move", "del", "ren", "type",
    # Network
    "curl", "wget", "ssh", "scp", "rsync",
    # Archive
    "tar", "zip", "unzip", "gzip", "gunzip",
    # System info (safe subset)
    "whoami", "hostname", "uname", "which", "where", "pwd",
    "ps", "top", "htop", "df", "du", "free", "uptime", "date",
    # Docker
    "docker", "docker-compose", "podman",
    # Misc dev tools
    "jq", "yq", "tree", "less", "more", "file", "stat", "realpath",
    "chmod", "chown", "chgrp",
})

# Secondary defense: patterns that are ALWAYS blocked (all lowercase for
# case-insensitive matching against the lowered command string).
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
    ":(){:|:&};:",        # fork bomb
    "curl | bash",
    "curl | sh",
    "wget | bash",
    "wget | sh",
    "> /dev/sda",
    "chmod -r 777 /",     # lowercase – matched against lowered input
    "mv / ",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_whitelist_enabled() -> bool:
    """Return True unless the whitelist is explicitly disabled."""
    return os.environ.get("FORGE_COMMAND_WHITELIST_DISABLED", "0") != "1"


def _extract_base_command(segment: str) -> str:
    """Return the lowercase base-name of the first token in *segment*.

    Handles ``/usr/bin/python``, ``C:\\Python\\python.exe``, and leading
    env-var assignments like ``FOO=bar python script.py``.
    """
    token = segment.strip()
    # Strip leading env-var assignments (POSIX only: VAR=val cmd …)
    while re.match(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s", token):
        token = re.sub(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s+", "", token, count=1)

    try:
        if platform.system() == "Windows":
            parts = shlex.split(token, posix=False)
        else:
            parts = shlex.split(token)
        first = parts[0] if parts else token
    except ValueError:
        first = token.split()[0] if token.split() else token

    # Path(...).stem strips directory *and* extension (.exe, .cmd, .bat …)
    return Path(first).stem.lower()


def _extract_commands_from_pipeline(command: str) -> list[str]:
    """Return the base command name for every segment in a pipeline/chain."""
    segments = re.split(r"\|{1,2}|&&|;", command)
    bases: list[str] = []
    for seg in segments:
        seg = seg.strip()
        # Skip pure redirects / empty segments
        if not seg or seg.startswith(">") or seg.startswith("<"):
            continue
        base = _extract_base_command(seg)
        if base:
            bases.append(base)
    return bases


def _check_command_whitelist(
    command: str,
    allowed_commands: frozenset[str] = ALLOWED_COMMANDS,
) -> tuple[bool, str]:
    """Validate every command in *command* against the whitelist."""
    if not _is_whitelist_enabled():
        return True, ""

    if _needs_shell(command):
        bases = _extract_commands_from_pipeline(command)
    else:
        bases = [_extract_base_command(command)]

    for base in bases:
        if base not in allowed_commands:
            return False, (
                f"Command '{base}' is not in the allowed commands whitelist. "
                f"Set FORGE_COMMAND_WHITELIST_DISABLED=1 to disable this check."
            )
    return True, ""


def _needs_shell(command: str) -> bool:
    """Check if command requires shell interpretation."""
    shell_operators = ['|', '&&', '||', '>', '<', '>>', '<<', ';', '`', '$(']
    return any(op in command for op in shell_operators)


def _parse_command(command: str) -> list[str]:
    """Parse *command* into an argv list, respecting platform quoting rules."""
    try:
        if platform.system() == "Windows":
            return shlex.split(command, posix=False)
        return shlex.split(command)
    except ValueError:
        # Unmatched quotes – fall back to naive split
        return command.split()


def _is_command_safe(
    command: str,
    allowed_commands: frozenset[str] = ALLOWED_COMMANDS,
    blocked_patterns: list[str] | None = None,
) -> tuple[bool, str]:
    """Check if a command is safe to execute (whitelist + denylist)."""
    effective_blocked = blocked_patterns if blocked_patterns is not None else BLOCKED_PATTERNS

    # --- Primary defense: whitelist ---
    allowed, reason = _check_command_whitelist(command, allowed_commands)
    if not allowed:
        return False, reason

    # --- Secondary defense: denylist (case-insensitive) ---
    cmd_lower = command.lower().strip()

    for blocked in effective_blocked:
        if blocked in cmd_lower:
            return False, f"Blocked dangerous pattern: '{blocked}'"

    # Block piping to shell interpreters from network tools
    if ("curl " in cmd_lower or "wget " in cmd_lower) and "|" in cmd_lower:
        pipe_segments = cmd_lower.split("|")
        for segment in pipe_segments[1:]:
            if any(sh in segment.strip() for sh in ["bash", "sh", "zsh", "python", "perl", "ruby", "node"]):
                return False, "Blocked: piping to shell interpreter"

    # Block encoded payload execution
    if "base64" in cmd_lower and ("|" in cmd_lower or ">" in cmd_lower):
        return False, "Blocked: base64 decoding with piping/redirect"

    # Block reading sensitive system files
    sensitive_paths = ["/etc/shadow", "/etc/passwd", "/etc/sudoers", ".ssh/", "id_rsa"]
    if any(sp in cmd_lower for sp in sensitive_paths):
        return False, "Blocked: accessing sensitive system files"

    # Block environment variable dumping (credential exposure)
    if cmd_lower.strip() in ("env", "printenv", "set"):
        return False, "Blocked: environment variable dump (may expose secrets)"

    return True, ""


async def run_command(
    command: str,
    workdir: str = ".",
    timeout: int = 30,
    shell: bool | None = None,
    background: bool = False,
    _allowed_commands: frozenset[str] = ALLOWED_COMMANDS,
    _blocked_patterns: list[str] | None = None,
) -> str:
    """
    Execute a shell command in a sandboxed subprocess.

    Returns JSON with exit_code, stdout, stderr, and duration.
    Commands are checked against a blocklist for safety.
    """
    # Safety check
    safe, reason = _is_command_safe(command, _allowed_commands, _blocked_patterns)
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

    use_shell = shell if shell is not None else _needs_shell(command)

    # Build the argv / command form appropriate for shell vs. non-shell.
    # When shell=False we always pass a list; when shell=True a raw string.
    if use_shell:
        run_cmd: str | list[str] = command
    else:
        run_cmd = _parse_command(command)

    if background:
        try:
            import subprocess as sp
            if platform.system() == "Windows":
                process = sp.Popen(
                    run_cmd, shell=use_shell, cwd=str(work_path),
                    stdout=sp.DEVNULL, stderr=sp.DEVNULL,
                    creationflags=sp.CREATE_NEW_PROCESS_GROUP,
                )
            else:
                process = sp.Popen(
                    run_cmd, shell=use_shell, cwd=str(work_path),
                    stdout=sp.DEVNULL, stderr=sp.DEVNULL,
                    start_new_session=True,
                )
            return json.dumps({
                "background": True,
                "pid": process.pid,
                "command": command,
                "success": True,
                "message": f"Process started in background with PID {process.pid}",
            })
        except Exception as e:
            return json.dumps({"background": True, "success": False, "error": str(e)})

    start_time = time.time()

    try:
        if platform.system() == "Windows":
            process = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    run_cmd,
                    shell=use_shell,
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
                    run_cmd,
                    shell=use_shell,
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


def create_command_tool(
    default_workdir: str = "./workspace",
    default_timeout: int = 30,
    policy: "SecurityPolicy | None" = None,
) -> Tool:
    """Create a sandboxed command execution tool.

    When a *policy* is provided, its ``shell_allowed_commands`` and
    ``shell_blocked_patterns`` override the module-level defaults.
    """
    effective_allowed = (
        policy.shell_allowed_commands if policy is not None else ALLOWED_COMMANDS
    )
    effective_blocked = (
        policy.shell_blocked_patterns if policy is not None else None
    )

    async def _run(
        command: str,
        workdir: str = default_workdir,
        timeout: int = default_timeout,
        background: bool = False,
    ) -> str:
        return await run_command(
            command,
            workdir=workdir,
            timeout=timeout,
            background=background,
            _allowed_commands=effective_allowed,
            _blocked_patterns=effective_blocked,
        )

    return Tool(
        name="run_command",
        description=(
            "Execute a shell command in a sandboxed subprocess. "
            "Use for: running scripts, installing packages, building projects, running tests, "
            "git operations, and any CLI tasks. "
            "Returns: exit_code, stdout, stderr, duration. "
            "Commands are validated against an allowlist and dangerous patterns are blocked. "
            "Set FORGE_COMMAND_WHITELIST_DISABLED=1 to bypass the allowlist in trusted environments."
        ),
        parameters=[
            ToolParameter(name="command", type="string", description="The shell command to execute"),
            ToolParameter(name="workdir", type="string", description="Working directory (default: ./workspace)", required=False),
            ToolParameter(name="timeout", type="integer", description="Timeout in seconds (default: 30, max: 300)", required=False),
            ToolParameter(name="background", type="boolean", description="If true, start process in background (for servers). Returns PID.", required=False),
        ],
        _fn=_run,
    )
