"""Domain tool: query_metrics

Query operational metrics from the metrics store.
"""

from forge.runtime.tools import Tool, ToolParameter


async def query_metrics(metric_name, group_by, time_range) -> str:
    """Query operational metrics from the metrics store."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Query operational metrics from the metrics store.\n"
        f"  metric_name: {metric_name}\n"
        f"  group_by: {group_by}\n"
        f"  time_range: {time_range}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


query_metrics_tool = Tool(
    name="query_metrics",
    description="Query operational metrics from the metrics store.",
    parameters=[
        ToolParameter(name="metric_name", type="string", description="Metric to query (e.g., 'task_completion_rate', 'avg_quality_score')", required=True),
        ToolParameter(name="group_by", type="string", description="Group by: 'agent', 'team', 'hour', 'day'", required=False),
        ToolParameter(name="time_range", type="string", description="Time range filter", required=False),
    ],
    _fn=query_metrics,
)
