"""LLM-powered tool: track_request

Track or update the status of a request.

Implementation notes: Update request status in shared memory or tracking store

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def track_request(request_id, status) -> str:
    """
    Track or update the status of a request.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "track_request",
        "description": "Track or update the status of a request.",
        "implementation_approach": "Update request status in shared memory or tracking store",
        "parameters": {
            "request_id": request_id,
            "status": status,
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


track_request_tool = Tool(
    name="track_request",
    description=(
        "Track or update the status of a request. "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="request_id",
            type="string",
            description="Request tracking ID",
            required=True,
        ),
        ToolParameter(
            name="status",
            type="string",
            description="New status",
            required=True,
        ),
    ],
    _fn=track_request,
)