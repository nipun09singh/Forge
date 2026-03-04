"""Domain tool: generate_revenue_forecast

Generate a revenue forecast based on current trends.
"""

from forge.runtime.tools import Tool, ToolParameter


async def generate_revenue_forecast(months_ahead, growth_scenario) -> str:
    """Generate a revenue forecast based on current trends."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Generate a revenue forecast based on current trends.\n"
        f"  months_ahead: {months_ahead}\n"
        f"  growth_scenario: {growth_scenario}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


generate_revenue_forecast_tool = Tool(
    name="generate_revenue_forecast",
    description="Generate a revenue forecast based on current trends.",
    parameters=[
        ToolParameter(name="months_ahead", type="integer", description="How many months to forecast", required=True),
        ToolParameter(name="growth_scenario", type="string", description="Scenario: conservative, base, aggressive", required=False),
    ],
    _fn=generate_revenue_forecast,
)
