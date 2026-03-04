"""Domain tool: route_to_team

Route a classified request to a specific team.
"""

from forge.runtime.tools import Tool, ToolParameter


async def route_to_team(request_id, team_name, priority) -> str:
    """Route a classified request to a specific team."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Route a classified request to a specific team.\n"
        f"  request_id: {request_id}\n"
        f"  team_name: {team_name}\n"
        f"  priority: {priority}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


route_to_team_tool = Tool(
    name="route_to_team",
    description="Route a classified request to a specific team.",
    parameters=[
        ToolParameter(name="request_id", type="string", description="Request tracking ID", required=True),
        ToolParameter(name="team_name", type="string", description="Target team name", required=True),
        ToolParameter(name="priority", type="string", description="Priority level", required=False),
    ],
    _fn=route_to_team,
)
