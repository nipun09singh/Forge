"""LLM-powered tool: set_alert

Set an alert threshold for a metric.

Implementation notes: Register alert rule in monitoring system

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def set_alert(metric_name, threshold, condition) -> str:
    """
    Set an alert threshold for a metric.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "set_alert",
        "description": "Set an alert threshold for a metric.",
        "implementation_approach": "Register alert rule in monitoring system",
        "parameters": {
            "metric_name": metric_name,
            "threshold": threshold,
            "condition": condition,
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


set_alert_tool = Tool(
    name="set_alert",
    description=(
        "Set an alert threshold for a metric. "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
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