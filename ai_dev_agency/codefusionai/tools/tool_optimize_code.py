"""LLM-powered tool: optimize_code

Automatically optimize the given code

Implementation notes: Use code optimization algorithms and libraries

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def optimize_code(code) -> str:
    """
    Automatically optimize the given code

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "optimize_code",
        "description": "Automatically optimize the given code",
        "implementation_approach": "Use code optimization algorithms and libraries",
        "parameters": {
            "code": code,
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


optimize_code_tool = Tool(
    name="optimize_code",
    description=(
        "Automatically optimize the given code "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="code",
            type="string",
            description="Code to be optimized",
            required=True,
        ),
    ],
    _fn=optimize_code,
)