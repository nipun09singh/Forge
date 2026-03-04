"""Domain tool: flag_expansion_opportunity

Flag a customer for upsell/expansion opportunity.
"""

from forge.runtime.tools import Tool, ToolParameter


async def flag_expansion_opportunity(customer_id, opportunity_type, estimated_value) -> str:
    """Flag a customer for upsell/expansion opportunity."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Flag a customer for upsell/expansion opportunity.\n"
        f"  customer_id: {customer_id}\n"
        f"  opportunity_type: {opportunity_type}\n"
        f"  estimated_value: {estimated_value}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


flag_expansion_opportunity_tool = Tool(
    name="flag_expansion_opportunity",
    description="Flag a customer for upsell/expansion opportunity.",
    parameters=[
        ToolParameter(name="customer_id", type="string", description="Customer identifier", required=True),
        ToolParameter(name="opportunity_type", type="string", description="Type: upsell, cross_sell, plan_upgrade, add_seats", required=True),
        ToolParameter(name="estimated_value", type="string", description="Estimated additional revenue", required=True),
    ],
    _fn=flag_expansion_opportunity,
)
