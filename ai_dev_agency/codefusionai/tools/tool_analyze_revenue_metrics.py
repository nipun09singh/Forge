"""LLM-powered tool: analyze_revenue_metrics

Analyze key revenue metrics: MRR, ARR, ARPU, LTV, CAC, churn rate.

Implementation notes: Query billing/subscription data, calculate growth rates and trends

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def analyze_revenue_metrics(metric, time_range, segment) -> str:
    """
    Analyze key revenue metrics: MRR, ARR, ARPU, LTV, CAC, churn rate.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "analyze_revenue_metrics",
        "description": "Analyze key revenue metrics: MRR, ARR, ARPU, LTV, CAC, churn rate.",
        "implementation_approach": "Query billing/subscription data, calculate growth rates and trends",
        "parameters": {
            "metric": metric,
            "time_range": time_range,
            "segment": segment,
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


analyze_revenue_metrics_tool = Tool(
    name="analyze_revenue_metrics",
    description=(
        "Analyze key revenue metrics: MRR, ARR, ARPU, LTV, CAC, churn rate. "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="metric",
            type="string",
            description="Metric to analyze: mrr, arr, arpu, ltv, cac, churn, ltv_cac_ratio",
            required=True,
        ),
        ToolParameter(
            name="time_range",
            type="string",
            description="Time range",
            required=False,
        ),
        ToolParameter(
            name="segment",
            type="string",
            description="Customer segment to analyze",
            required=False,
        ),
    ],
    _fn=analyze_revenue_metrics,
)