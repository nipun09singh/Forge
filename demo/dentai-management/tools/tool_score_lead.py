"""Domain tool: score_lead

Score a lead on fit, intent, and budget.
"""

from forge.runtime.tools import Tool, ToolParameter


async def score_lead(lead_data) -> str:
    """Score a lead on fit, intent, and budget."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Score a lead on fit, intent, and budget.\n"
        f"  lead_data: {lead_data}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


score_lead_tool = Tool(
    name="score_lead",
    description="Score a lead on fit, intent, and budget.",
    parameters=[
        ToolParameter(name="lead_data", type="string", description="JSON with lead information (company, role, behavior signals)", required=True),
    ],
    _fn=score_lead,
)
