"""Domain tool: get_customer_health

Get health score and risk assessment for a customer.
"""

from forge.runtime.tools import Tool, ToolParameter


async def get_customer_health(customer_id) -> str:
    """Get health score and risk assessment for a customer."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Get health score and risk assessment for a customer.\n"
        f"  customer_id: {customer_id}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


get_customer_health_tool = Tool(
    name="get_customer_health",
    description="Get health score and risk assessment for a customer.",
    parameters=[
        ToolParameter(name="customer_id", type="string", description="Customer identifier", required=True),
    ],
    _fn=get_customer_health,
)
