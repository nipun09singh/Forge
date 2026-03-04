"""Custom tool: route_to_team"""

from forge.runtime import Tool, ToolParameter


async def route_to_team(request_id, team_name, priority) -> str:
    """
    Route a classified request to a specific team.

    Implementation notes: Use the Router to send task to the specified team
    """
    # TODO: Implement this tool
    # This is a generated stub — replace with real logic
    result = {
        "tool": "route_to_team",
        "request_id": request_id,
        "team_name": team_name,
        "priority": priority,
    }
    return str(result)


route_to_team_tool = Tool(
    name="route_to_team",
    description="Route a classified request to a specific team.",
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