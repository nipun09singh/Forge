"""LLM-powered tool: generate_revenue_forecast

Generate a revenue forecast based on current trends.

Implementation notes: Use historical growth rates, churn, and expansion data to project forward

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def generate_revenue_forecast(months_ahead, growth_scenario) -> str:
    """
    Generate a revenue forecast based on current trends.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "generate_revenue_forecast",
        "description": "Generate a revenue forecast based on current trends.",
        "implementation_approach": "Use historical growth rates, churn, and expansion data to project forward",
        "parameters": {
            "months_ahead": months_ahead,
            "growth_scenario": growth_scenario,
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


generate_revenue_forecast_tool = Tool(
    name="generate_revenue_forecast",
    description=(
        "Generate a revenue forecast based on current trends. "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="months_ahead",
            type="integer",
            description="How many months to forecast",
            required=True,
        ),
        ToolParameter(
            name="growth_scenario",
            type="string",
            description="Scenario: conservative, base, aggressive",
            required=False,
        ),
    ],
    _fn=generate_revenue_forecast,
)