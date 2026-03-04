"""Git Tool — version control operations for agent workspaces."""

from __future__ import annotations

import json
import logging
from typing import Any

from forge.runtime.tools import Tool, ToolParameter

logger = logging.getLogger(__name__)


async def git_operation(operation: str, args: str = "", workdir: str = ".") -> str:
    """Execute a git operation."""
    from forge.runtime.integrations.command_tool import run_command

    # Map operations to git commands
    op = operation.lower().strip()
    
    command_map = {
        "init": "git init",
        "status": "git status",
        "add": f"git add {args}" if args else "git add .",
        "commit": f'git commit -m "{args}"' if args else 'git commit -m "Auto-commit by agent"',
        "branch": f"git branch {args}" if args else "git branch",
        "checkout": f"git checkout {args}",
        "diff": f"git diff {args}" if args else "git diff",
        "log": f"git log --oneline -20 {args}".strip(),
        "push": f"git push {args}" if args else "git push",
        "pull": f"git pull {args}" if args else "git pull",
        "clone": f"git clone {args}",
        "stash": f"git stash {args}" if args else "git stash",
        "reset": f"git reset {args}" if args else "git reset",
        "merge": f"git merge {args}",
    }

    if op not in command_map:
        return json.dumps({"error": f"Unknown git operation: {op}. Available: {list(command_map.keys())}"})

    cmd = command_map[op]
    result = await run_command(cmd, workdir=workdir, timeout=30)
    
    # Parse and enhance the result
    try:
        data = json.loads(result)
        data["operation"] = op
        data["git_command"] = cmd
        return json.dumps(data)
    except json.JSONDecodeError:
        return result


def create_git_tool() -> Tool:
    """Create a git operations tool."""
    return Tool(
        name="git_operation",
        description=(
            "Execute git version control operations: init, status, add, commit, branch, "
            "checkout, diff, log, push, pull, clone, stash, reset, merge. "
            "Use to version control code changes, create branches, and manage repositories."
        ),
        parameters=[
            ToolParameter(name="operation", type="string", description="Git operation: init, status, add, commit, branch, checkout, diff, log, push, pull, clone, stash, reset, merge"),
            ToolParameter(name="args", type="string", description="Additional arguments (e.g., branch name, commit message, file paths)", required=False),
            ToolParameter(name="workdir", type="string", description="Working directory (default: current)", required=False),
        ],
        _fn=git_operation,
    )
