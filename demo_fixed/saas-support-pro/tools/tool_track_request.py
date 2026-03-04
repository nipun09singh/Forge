"""Domain tool: track_request

Track or update the status of a request.
"""

from forge.runtime.tools import Tool, ToolParameter


async def track_request(request_id, status) -> str:
    """Track or update the status of a request."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Track or update the status of a request.\n"
        f"  request_id: {request_id}\n"
        f"  status: {status}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


track_request_tool = Tool(
    name="track_request",
    description="Track or update the status of a request.",
    parameters=[
        ToolParameter(name="request_id", type="string", description="Request tracking ID", required=True),
        ToolParameter(name="status", type="string", description="New status", required=True),
    ],
    _fn=track_request,
)
