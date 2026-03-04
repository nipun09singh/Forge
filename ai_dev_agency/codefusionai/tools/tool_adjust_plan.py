"""LLM-powered tool: adjust_plan

Modify an active plan — add, remove, or reassign steps.

Implementation notes: Modify the TaskPlan DAG — add/remove steps, change assignments

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def adjust_plan(plan_id, adjustment) -> str:
    """
    Modify an active plan — add, remove, or reassign steps.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "adjust_plan",
        "description": "Modify an active plan — add, remove, or reassign steps.",
        "implementation_approach": "Modify the TaskPlan DAG — add/remove steps, change assignments",
        "parameters": {
            "plan_id": plan_id,
            "adjustment": adjustment,
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


adjust_plan_tool = Tool(
    name="adjust_plan",
    description=(
        "Modify an active plan — add, remove, or reassign steps. "
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
        ToolParameter(
            name="adjustment",
            type="string",
            description="Description of what to change",
            required=True,
        ),
    ],
    _fn=adjust_plan,
)