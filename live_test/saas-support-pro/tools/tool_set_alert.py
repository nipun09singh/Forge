"""Custom tool: set_alert"""

from forge.runtime import Tool, ToolParameter


async def set_alert(metric_name, threshold, condition) -> str:
    """
    Set an alert threshold for a metric.

    Implementation notes: Register alert rule in monitoring system
    """
    # TODO: Implement this tool
    # This is a generated stub — replace with real logic
    result = {
        "tool": "set_alert",
        "metric_name": metric_name,
        "threshold": threshold,
        "condition": condition,
    }
    return str(result)


set_alert_tool = Tool(
    name="set_alert",
    description="Set an alert threshold for a metric.",
    parameters=[
        ToolParameter(
            name="metric_name",
            type="string",
            description="Metric to monitor",
            required=True,
        ),
        ToolParameter(
            name="threshold",
            type="number",
            description="Alert threshold value",
            required=True,
        ),
        ToolParameter(
            name="condition",
            type="string",
            description="Condition: 'above', 'below'",
            required=True,
        ),
    ],
    _fn=set_alert,
)