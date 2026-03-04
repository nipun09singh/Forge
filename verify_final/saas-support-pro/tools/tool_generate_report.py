"""Domain tool: generate_report

Generate a formatted performance report.
"""

from forge.runtime.tools import Tool, ToolParameter


async def generate_report(report_type, time_range) -> str:
    """Generate a formatted performance report."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Generate a formatted performance report.\n"
        f"  report_type: {report_type}\n"
        f"  time_range: {time_range}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


generate_report_tool = Tool(
    name="generate_report",
    description="Generate a formatted performance report.",
    parameters=[
        ToolParameter(name="report_type", type="string", description="Type: 'summary', 'detailed', 'trends', 'alerts'", required=True),
        ToolParameter(name="time_range", type="string", description="Time range for the report", required=False),
    ],
    _fn=generate_report,
)
