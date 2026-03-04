"""LLM-powered tool: generate_insights_and_recommendations

Generate data-driven insights and recommendations

Implementation notes: Use data analytics and machine learning algorithms

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def generate_insights_and_recommendations(data) -> str:
    """
    Generate data-driven insights and recommendations

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "generate_insights_and_recommendations",
        "description": "Generate data-driven insights and recommendations",
        "implementation_approach": "Use data analytics and machine learning algorithms",
        "parameters": {
            "data": data,
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


generate_insights_and_recommendations_tool = Tool(
    name="generate_insights_and_recommendations",
    description=(
        "Generate data-driven insights and recommendations "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="data",
            type="object",
            description="Data to be analyzed for insights and recommendations",
            required=True,
        ),
    ],
    _fn=generate_insights_and_recommendations,
)