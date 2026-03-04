"""Domain tool: analyze_growth_metrics

Analyze growth metrics: conversion rates, viral coefficient, CAC, LTV, retention curves.
"""

from forge.runtime.tools import Tool, ToolParameter


async def analyze_growth_metrics(metric_type, time_range) -> str:
    """Analyze growth metrics: conversion rates, viral coefficient, CAC, LTV, retention curves."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Analyze growth metrics: conversion rates, viral coefficient, CAC, LTV, retention curves.\n"
        f"  metric_type: {metric_type}\n"
        f"  time_range: {time_range}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


analyze_growth_metrics_tool = Tool(
    name="analyze_growth_metrics",
    description="Analyze growth metrics: conversion rates, viral coefficient, CAC, LTV, retention curves.",
    parameters=[
        ToolParameter(name="metric_type", type="string", description="Metric to analyze: conversion, viral_coefficient, cac, ltv, retention", required=True),
        ToolParameter(name="time_range", type="string", description="Time range for analysis", required=False),
    ],
    _fn=analyze_growth_metrics,
)
