"""Domain tool: get_performance_metrics

Retrieve performance metrics for an agent or the entire agency.
"""

from forge.runtime.tools import Tool, ToolParameter


async def get_performance_metrics(agent_name, time_range) -> str:
    """Retrieve performance metrics for an agent or the entire agency."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Retrieve performance metrics for an agent or the entire agency.\n"
        f"  agent_name: {agent_name}\n"
        f"  time_range: {time_range}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


get_performance_metrics_tool = Tool(
    name="get_performance_metrics",
    description="Retrieve performance metrics for an agent or the entire agency.",
    parameters=[
        ToolParameter(name="agent_name", type="string", description="Agent name (or 'all' for agency-wide)", required=True),
        ToolParameter(name="time_range", type="string", description="Time range: 'last_hour', 'last_day', 'last_week'", required=False),
    ],
    _fn=get_performance_metrics,
)
