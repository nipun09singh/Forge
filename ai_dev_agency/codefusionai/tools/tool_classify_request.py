"""LLM-powered tool: classify_request

Classify an incoming request by type, urgency, and required expertise.

Implementation notes: Use NLP/LLM to classify intent, urgency (low/medium/high/critical), and match to teams

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def classify_request(request_text, available_teams) -> str:
    """
    Classify an incoming request by type, urgency, and required expertise.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "classify_request",
        "description": "Classify an incoming request by type, urgency, and required expertise.",
        "implementation_approach": "Use NLP/LLM to classify intent, urgency (low/medium/high/critical), and match to teams",
        "parameters": {
            "request_text": request_text,
            "available_teams": available_teams,
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


classify_request_tool = Tool(
    name="classify_request",
    description=(
        "Classify an incoming request by type, urgency, and required expertise. "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="request_text",
            type="string",
            description="The incoming request",
            required=True,
        ),
        ToolParameter(
            name="available_teams",
            type="string",
            description="JSON list of available teams",
            required=False,
        ),
    ],
    _fn=classify_request,
)