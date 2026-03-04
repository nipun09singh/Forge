"""LLM-powered tool: deploy_application

Automatically deploy the application to the specified environment

Implementation notes: Use CI/CD pipelines for deployment

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def deploy_application(environment) -> str:
    """
    Automatically deploy the application to the specified environment

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "deploy_application",
        "description": "Automatically deploy the application to the specified environment",
        "implementation_approach": "Use CI/CD pipelines for deployment",
        "parameters": {
            "environment": environment,
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


deploy_application_tool = Tool(
    name="deploy_application",
    description=(
        "Automatically deploy the application to the specified environment "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="environment",
            type="string",
            description="The environment to deploy the application to",
            required=True,
        ),
    ],
    _fn=deploy_application,
)