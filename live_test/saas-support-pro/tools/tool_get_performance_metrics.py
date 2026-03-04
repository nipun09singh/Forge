"""Custom tool: get_performance_metrics"""

from forge.runtime import Tool, ToolParameter


async def get_performance_metrics(agent_name, time_range) -> str:
    """
    Retrieve performance metrics for an agent or the entire agency.

    Implementation notes: Query the performance tracker for success rates, avg quality scores, error counts
    """
    # TODO: Implement this tool
    # This is a generated stub — replace with real logic
    result = {
        "tool": "get_performance_metrics",
        "agent_name": agent_name,
        "time_range": time_range,
    }
    return str(result)


get_performance_metrics_tool = Tool(
    name="get_performance_metrics",
    description="Retrieve performance metrics for an agent or the entire agency.",
    parameters=[
        ToolParameter(
            name="agent_name",
            type="string",
            description="Agent name (or 'all' for agency-wide)",
            required=True,
        ),
        ToolParameter(
            name="time_range",
            type="string",
            description="Time range: 'last_hour', 'last_day', 'last_week'",
            required=False,
        ),
    ],
    _fn=get_performance_metrics,
)