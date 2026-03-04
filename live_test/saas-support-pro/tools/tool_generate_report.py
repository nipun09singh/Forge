"""Custom tool: generate_report"""

from forge.runtime import Tool, ToolParameter


async def generate_report(report_type, time_range) -> str:
    """
    Generate a formatted performance report.

    Implementation notes: Aggregate metrics and format into a readable report with charts/tables
    """
    # TODO: Implement this tool
    # This is a generated stub — replace with real logic
    result = {
        "tool": "generate_report",
        "report_type": report_type,
        "time_range": time_range,
    }
    return str(result)


generate_report_tool = Tool(
    name="generate_report",
    description="Generate a formatted performance report.",
    parameters=[
        ToolParameter(
            name="report_type",
            type="string",
            description="Type: 'summary', 'detailed', 'trends', 'alerts'",
            required=True,
        ),
        ToolParameter(
            name="time_range",
            type="string",
            description="Time range for the report",
            required=False,
        ),
    ],
    _fn=generate_report,
)