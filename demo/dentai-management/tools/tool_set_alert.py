"""Domain tool: set_alert

Set an alert threshold for a metric.
"""

from forge.runtime.tools import Tool, ToolParameter


async def set_alert(metric_name, threshold, condition) -> str:
    """Set an alert threshold for a metric."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Set an alert threshold for a metric.\n"
        f"  metric_name: {metric_name}\n"
        f"  threshold: {threshold}\n"
        f"  condition: {condition}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


set_alert_tool = Tool(
    name="set_alert",
    description="Set an alert threshold for a metric.",
    parameters=[
        ToolParameter(name="metric_name", type="string", description="Metric to monitor", required=True),
        ToolParameter(name="threshold", type="number", description="Alert threshold value", required=True),
        ToolParameter(name="condition", type="string", description="Condition: 'above', 'below'", required=True),
    ],
    _fn=set_alert,
)
