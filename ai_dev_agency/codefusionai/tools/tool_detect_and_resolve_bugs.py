"""LLM-powered tool: detect_and_resolve_bugs

Automatically detect and resolve bugs in the code

Implementation notes: Use static and dynamic analysis tools for bug detection and resolution

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def detect_and_resolve_bugs(code) -> str:
    """
    Automatically detect and resolve bugs in the code

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "detect_and_resolve_bugs",
        "description": "Automatically detect and resolve bugs in the code",
        "implementation_approach": "Use static and dynamic analysis tools for bug detection and resolution",
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


detect_and_resolve_bugs_tool = Tool(
    name="detect_and_resolve_bugs",
    description=(
        "Automatically detect and resolve bugs in the code "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="code",
            type="string",
            description="Code to be analyzed for bugs",
            required=True,
        ),
    ],
    _fn=detect_and_resolve_bugs,
)