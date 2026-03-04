"""LLM-powered tool: query_metrics

Query operational metrics from the metrics store.

Implementation notes: Query in-memory metrics store or metrics database

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def query_metrics(metric_name, group_by, time_range) -> str:
    """
    Query operational metrics from the metrics store.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "query_metrics",
        "description": "Query operational metrics from the metrics store.",
        "implementation_approach": "Query in-memory metrics store or metrics database",
        "parameters": {
            "metric_name": metric_name,
            "group_by": group_by,
            "time_range": time_range,
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


query_metrics_tool = Tool(
    name="query_metrics",
    description=(
        "Query operational metrics from the metrics store. "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="metric_name",
            type="string",
            description="Metric to query (e.g., 'task_completion_rate', 'avg_quality_score')",
            required=True,
        ),
        ToolParameter(
            name="group_by",
            type="string",
            description="Group by: 'agent', 'team', 'hour', 'day'",
            required=False,
        ),
        ToolParameter(
            name="time_range",
            type="string",
            description="Time range filter",
            required=False,
        ),
    ],
    _fn=query_metrics,
)