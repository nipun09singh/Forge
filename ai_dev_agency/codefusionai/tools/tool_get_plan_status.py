"""LLM-powered tool: get_plan_status

Get the current status and progress of an active plan.

Implementation notes: Query the Planner for plan status, step completion, and blockers

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def get_plan_status(plan_id) -> str:
    """
    Get the current status and progress of an active plan.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "get_plan_status",
        "description": "Get the current status and progress of an active plan.",
        "implementation_approach": "Query the Planner for plan status, step completion, and blockers",
        "parameters": {
            "plan_id": plan_id,
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


get_plan_status_tool = Tool(
    name="get_plan_status",
    description=(
        "Get the current status and progress of an active plan. "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="plan_id",
            type="string",
            description="Plan identifier",
            required=True,
        ),
    ],
    _fn=get_plan_status,
)