"""LLM-powered tool: route_to_team

Route a classified request to a specific team.

Implementation notes: Use the Router to send task to the specified team

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def route_to_team(request_id, team_name, priority) -> str:
    """
    Route a classified request to a specific team.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "route_to_team",
        "description": "Route a classified request to a specific team.",
        "implementation_approach": "Use the Router to send task to the specified team",
        "parameters": {
            "request_id": request_id,
            "team_name": team_name,
            "priority": priority,
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


route_to_team_tool = Tool(
    name="route_to_team",
    description=(
        "Route a classified request to a specific team. "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="request_id",
            type="string",
            description="Request tracking ID",
            required=True,
        ),
        ToolParameter(
            name="team_name",
            type="string",
            description="Target team name",
            required=True,
        ),
        ToolParameter(
            name="priority",
            type="string",
            description="Priority level",
            required=False,
        ),
    ],
    _fn=route_to_team,
)