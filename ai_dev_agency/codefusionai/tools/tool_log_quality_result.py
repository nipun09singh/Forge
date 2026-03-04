"""LLM-powered tool: log_quality_result

Log a quality review result for tracking and analytics.

Implementation notes: Append to quality log file or in-memory metrics store

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def log_quality_result(agent_name, score, passed, feedback) -> str:
    """
    Log a quality review result for tracking and analytics.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "log_quality_result",
        "description": "Log a quality review result for tracking and analytics.",
        "implementation_approach": "Append to quality log file or in-memory metrics store",
        "parameters": {
            "agent_name": agent_name,
            "score": score,
            "passed": passed,
            "feedback": feedback,
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


log_quality_result_tool = Tool(
    name="log_quality_result",
    description=(
        "Log a quality review result for tracking and analytics. "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="agent_name",
            type="string",
            description="Name of the agent whose output was reviewed",
            required=True,
        ),
        ToolParameter(
            name="score",
            type="number",
            description="Quality score (0-10)",
            required=True,
        ),
        ToolParameter(
            name="passed",
            type="boolean",
            description="Whether the output passed QA",
            required=True,
        ),
        ToolParameter(
            name="feedback",
            type="string",
            description="Review feedback",
            required=False,
        ),
    ],
    _fn=log_quality_result,
)