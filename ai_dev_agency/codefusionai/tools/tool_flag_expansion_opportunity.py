"""LLM-powered tool: flag_expansion_opportunity

Flag a customer for upsell/expansion opportunity.

Implementation notes: Log opportunity to CRM pipeline, notify sales/growth team

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def flag_expansion_opportunity(customer_id, opportunity_type, estimated_value) -> str:
    """
    Flag a customer for upsell/expansion opportunity.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "flag_expansion_opportunity",
        "description": "Flag a customer for upsell/expansion opportunity.",
        "implementation_approach": "Log opportunity to CRM pipeline, notify sales/growth team",
        "parameters": {
            "customer_id": customer_id,
            "opportunity_type": opportunity_type,
            "estimated_value": estimated_value,
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


flag_expansion_opportunity_tool = Tool(
    name="flag_expansion_opportunity",
    description=(
        "Flag a customer for upsell/expansion opportunity. "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="customer_id",
            type="string",
            description="Customer identifier",
            required=True,
        ),
        ToolParameter(
            name="opportunity_type",
            type="string",
            description="Type: upsell, cross_sell, plan_upgrade, add_seats",
            required=True,
        ),
        ToolParameter(
            name="estimated_value",
            type="string",
            description="Estimated additional revenue",
            required=True,
        ),
    ],
    _fn=flag_expansion_opportunity,
)