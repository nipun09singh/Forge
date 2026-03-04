"""LLM-powered tool: analyze_growth_metrics

Analyze growth metrics: conversion rates, viral coefficient, CAC, LTV, retention curves.

Implementation notes: Query growth metrics store for funnel data, calculate viral coefficient k-factor

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def analyze_growth_metrics(metric_type, time_range) -> str:
    """
    Analyze growth metrics: conversion rates, viral coefficient, CAC, LTV, retention curves.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "analyze_growth_metrics",
        "description": "Analyze growth metrics: conversion rates, viral coefficient, CAC, LTV, retention curves.",
        "implementation_approach": "Query growth metrics store for funnel data, calculate viral coefficient k-factor",
        "parameters": {
            "metric_type": metric_type,
            "time_range": time_range,
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


analyze_growth_metrics_tool = Tool(
    name="analyze_growth_metrics",
    description=(
        "Analyze growth metrics: conversion rates, viral coefficient, CAC, LTV, retention curves. "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="metric_type",
            type="string",
            description="Metric to analyze: conversion, viral_coefficient, cac, ltv, retention",
            required=True,
        ),
        ToolParameter(
            name="time_range",
            type="string",
            description="Time range for analysis",
            required=False,
        ),
    ],
    _fn=analyze_growth_metrics,
)