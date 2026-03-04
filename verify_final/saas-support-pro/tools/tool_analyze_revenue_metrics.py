"""Domain tool: analyze_revenue_metrics

Analyze key revenue metrics: MRR, ARR, ARPU, LTV, CAC, churn rate.
"""

from forge.runtime.tools import Tool, ToolParameter


async def analyze_revenue_metrics(metric, time_range, segment) -> str:
    """Analyze key revenue metrics: MRR, ARR, ARPU, LTV, CAC, churn rate."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Analyze key revenue metrics: MRR, ARR, ARPU, LTV, CAC, churn rate.\n"
        f"  metric: {metric}\n"
        f"  time_range: {time_range}\n"
        f"  segment: {segment}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


analyze_revenue_metrics_tool = Tool(
    name="analyze_revenue_metrics",
    description="Analyze key revenue metrics: MRR, ARR, ARPU, LTV, CAC, churn rate.",
    parameters=[
        ToolParameter(name="metric", type="string", description="Metric to analyze: mrr, arr, arpu, ltv, cac, churn, ltv_cac_ratio", required=True),
        ToolParameter(name="time_range", type="string", description="Time range", required=False),
        ToolParameter(name="segment", type="string", description="Customer segment to analyze", required=False),
    ],
    _fn=analyze_revenue_metrics,
)
