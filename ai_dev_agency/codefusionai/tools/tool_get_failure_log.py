"""LLM-powered tool: get_failure_log

Retrieve recent failures and their details.

Implementation notes: Query failure/error log for recent issues with stack traces and context

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def get_failure_log(agent_name, limit) -> str:
    """
    Retrieve recent failures and their details.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "get_failure_log",
        "description": "Retrieve recent failures and their details.",
        "implementation_approach": "Query failure/error log for recent issues with stack traces and context",
        "parameters": {
            "agent_name": agent_name,
            "limit": limit,
        },
        "instructions": (
            "Execute this task using the available tools: "
            "run_command (to execute shell commands), "
            "read_write_file (to create/read files), "
            "http_request (to call APIs). "
            "Be specific and actually perform the actions, don't just describe them. "
            "Create real files, run real commands, produce real output."
        ),
    }
    return json.dumps(task, indent=2, default=str)


get_failure_log_tool = Tool(
    name="get_failure_log",
    description=(
        "Retrieve recent failures and their details. "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="agent_name",
            type="string",
            description="Agent name (or 'all')",
            required=False,
        ),
        ToolParameter(
            name="limit",
            type="integer",
            description="Max failures to return",
            required=False,
        ),
    ],
    _fn=get_failure_log,
)