"""LLM-powered tool: upsell_and_cross_sell_services

Upsell and cross-sell services to customers

Implementation notes: Use CRM systems and upselling and cross-selling strategies

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def upsell_and_cross_sell_services(customer_data) -> str:
    """
    Upsell and cross-sell services to customers

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "upsell_and_cross_sell_services",
        "description": "Upsell and cross-sell services to customers",
        "implementation_approach": "Use CRM systems and upselling and cross-selling strategies",
        "parameters": {
            "customer_data": customer_data,
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


upsell_and_cross_sell_services_tool = Tool(
    name="upsell_and_cross_sell_services",
    description=(
        "Upsell and cross-sell services to customers "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="customer_data",
            type="object",
            description="Data about the customers",
            required=True,
        ),
    ],
    _fn=upsell_and_cross_sell_services,
)