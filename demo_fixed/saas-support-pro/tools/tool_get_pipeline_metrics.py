"""Domain tool: get_pipeline_metrics

Get current pipeline metrics and conversion rates.
"""

from forge.runtime.tools import Tool, ToolParameter


async def get_pipeline_metrics(stage) -> str:
    """Get current pipeline metrics and conversion rates."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Get current pipeline metrics and conversion rates.\n"
        f"  stage: {stage}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


get_pipeline_metrics_tool = Tool(
    name="get_pipeline_metrics",
    description="Get current pipeline metrics and conversion rates.",
    parameters=[
        ToolParameter(name="stage", type="string", description="Pipeline stage to analyze (or 'all')", required=False),
    ],
    _fn=get_pipeline_metrics,
)
