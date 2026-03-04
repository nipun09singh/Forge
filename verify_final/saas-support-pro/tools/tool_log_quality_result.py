"""Domain tool: log_quality_result

Log a quality review result for tracking and analytics.
"""

from forge.runtime.tools import Tool, ToolParameter


async def log_quality_result(agent_name, score, passed, feedback) -> str:
    """Log a quality review result for tracking and analytics."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Log a quality review result for tracking and analytics.\n"
        f"  agent_name: {agent_name}\n"
        f"  score: {score}\n"
        f"  passed: {passed}\n"
        f"  feedback: {feedback}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


log_quality_result_tool = Tool(
    name="log_quality_result",
    description="Log a quality review result for tracking and analytics.",
    parameters=[
        ToolParameter(name="agent_name", type="string", description="Name of the agent whose output was reviewed", required=True),
        ToolParameter(name="score", type="number", description="Quality score (0-10)", required=True),
        ToolParameter(name="passed", type="boolean", description="Whether the output passed QA", required=True),
        ToolParameter(name="feedback", type="string", description="Review feedback", required=False),
    ],
    _fn=log_quality_result,
)
