"""LLM-powered tool: get_pipeline_metrics

Get current pipeline metrics and conversion rates.

Implementation notes: Query CRM for lead counts per stage, conversion rates between stages

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def get_pipeline_metrics(stage) -> str:
    """
    Get current pipeline metrics and conversion rates.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "get_pipeline_metrics",
        "description": "Get current pipeline metrics and conversion rates.",
        "implementation_approach": "Query CRM for lead counts per stage, conversion rates between stages",
        "parameters": {
            "stage": stage,
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


get_pipeline_metrics_tool = Tool(
    name="get_pipeline_metrics",
    description=(
        "Get current pipeline metrics and conversion rates. "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="stage",
            type="string",
            description="Pipeline stage to analyze (or 'all')",
            required=False,
        ),
    ],
    _fn=get_pipeline_metrics,
)