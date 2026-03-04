"""Domain tool: classify_request

Classify an incoming request by type, urgency, and required expertise.
"""

from forge.runtime.tools import Tool, ToolParameter


async def classify_request(request_text, available_teams) -> str:
    """Classify an incoming request by type, urgency, and required expertise."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Classify an incoming request by type, urgency, and required expertise.\n"
        f"  request_text: {request_text}\n"
        f"  available_teams: {available_teams}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


classify_request_tool = Tool(
    name="classify_request",
    description="Classify an incoming request by type, urgency, and required expertise.",
    parameters=[
        ToolParameter(name="request_text", type="string", description="The incoming request", required=True),
        ToolParameter(name="available_teams", type="string", description="JSON list of available teams", required=False),
    ],
    _fn=classify_request,
)
