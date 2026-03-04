"""LLM-powered tool: create_plan

Create an execution plan by decomposing a task into steps.

Implementation notes: Use the Planner module to decompose task into a DAG of PlanSteps

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def create_plan(task, context) -> str:
    """
    Create an execution plan by decomposing a task into steps.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "create_plan",
        "description": "Create an execution plan by decomposing a task into steps.",
        "implementation_approach": "Use the Planner module to decompose task into a DAG of PlanSteps",
        "parameters": {
            "task": task,
            "context": context,
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


create_plan_tool = Tool(
    name="create_plan",
    description=(
        "Create an execution plan by decomposing a task into steps. "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="task",
            type="string",
            description="The complex task to plan",
            required=True,
        ),
        ToolParameter(
            name="context",
            type="string",
            description="Additional context (JSON)",
            required=False,
        ),
    ],
    _fn=create_plan,
)