"""LLM-powered tool: run_tests

Automatically run tests on the given code

Implementation notes: Use unit testing and integration testing libraries

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def run_tests(code) -> str:
    """
    Automatically run tests on the given code

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "run_tests",
        "description": "Automatically run tests on the given code",
        "implementation_approach": "Use unit testing and integration testing libraries",
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


run_tests_tool = Tool(
    name="run_tests",
    description=(
        "Automatically run tests on the given code "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="code",
            type="string",
            description="Code to be tested",
            required=True,
        ),
    ],
    _fn=run_tests,
)