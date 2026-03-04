"""LLM-powered tool: get_performance_metrics

Retrieve performance metrics for an agent or the entire agency.

Implementation notes: Query the performance tracker for success rates, avg quality scores, error counts

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def get_performance_metrics(agent_name, time_range) -> str:
    """
    Retrieve performance metrics for an agent or the entire agency.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "get_performance_metrics",
        "description": "Retrieve performance metrics for an agent or the entire agency.",
        "implementation_approach": "Query the performance tracker for success rates, avg quality scores, error counts",
        "parameters": {
            "agent_name": agent_name,
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


get_performance_metrics_tool = Tool(
    name="get_performance_metrics",
    description=(
        "Retrieve performance metrics for an agent or the entire agency. "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
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