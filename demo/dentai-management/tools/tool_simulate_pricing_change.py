"""Domain tool: simulate_pricing_change

Simulate the revenue impact of a pricing change.
"""

from forge.runtime.tools import Tool, ToolParameter


async def simulate_pricing_change(current_price, new_price, expected_churn_impact) -> str:
    """Simulate the revenue impact of a pricing change."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Simulate the revenue impact of a pricing change.\n"
        f"  current_price: {current_price}\n"
        f"  new_price: {new_price}\n"
        f"  expected_churn_impact: {expected_churn_impact}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


simulate_pricing_change_tool = Tool(
    name="simulate_pricing_change",
    description="Simulate the revenue impact of a pricing change.",
    parameters=[
        ToolParameter(name="current_price", type="number", description="Current price point", required=True),
        ToolParameter(name="new_price", type="number", description="Proposed new price", required=True),
        ToolParameter(name="expected_churn_impact", type="number", description="Expected change in churn rate (e.g., 0.02 for 2% increase)", required=True),
    ],
    _fn=simulate_pricing_change,
)
