"""LLM-powered tool: write_code

Automatically generate code based on given specifications

Implementation notes: Use advanced code generation algorithms and libraries

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def write_code(specification) -> str:
    """
    Automatically generate code based on given specifications

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "write_code",
        "description": "Automatically generate code based on given specifications",
        "implementation_approach": "Use advanced code generation algorithms and libraries",
        "parameters": {
            "specification": specification,
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


write_code_tool = Tool(
    name="write_code",
    description=(
        "Automatically generate code based on given specifications "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="specification",
            type="object",
            description="Specifications for the code to be written",
            required=True,
        ),
    ],
    _fn=write_code,
)