"""LLM-powered tool: generate_report

Generate a formatted performance report.

Implementation notes: Aggregate metrics and format into a readable report with charts/tables

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def generate_report(report_type, time_range) -> str:
    """
    Generate a formatted performance report.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "generate_report",
        "description": "Generate a formatted performance report.",
        "implementation_approach": "Aggregate metrics and format into a readable report with charts/tables",
        "parameters": {
            "report_type": report_type,
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


generate_report_tool = Tool(
    name="generate_report",
    description=(
        "Generate a formatted performance report. "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="report_type",
            type="string",
            description="Type: 'summary', 'detailed', 'trends', 'alerts'",
            required=True,
        ),
        ToolParameter(
            name="time_range",
            type="string",
            description="Time range for the report",
            required=False,
        ),
    ],
    _fn=generate_report,
)