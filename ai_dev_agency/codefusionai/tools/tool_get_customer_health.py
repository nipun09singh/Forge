"""LLM-powered tool: get_customer_health

Get health score and risk assessment for a customer.

Implementation notes: Calculate health score from usage frequency, support tickets, sentiment, payment history

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def get_customer_health(customer_id) -> str:
    """
    Get health score and risk assessment for a customer.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "get_customer_health",
        "description": "Get health score and risk assessment for a customer.",
        "implementation_approach": "Calculate health score from usage frequency, support tickets, sentiment, payment history",
        "parameters": {
            "customer_id": customer_id,
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


get_customer_health_tool = Tool(
    name="get_customer_health",
    description=(
        "Get health score and risk assessment for a customer. "
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
    ],
    _fn=get_customer_health,
)