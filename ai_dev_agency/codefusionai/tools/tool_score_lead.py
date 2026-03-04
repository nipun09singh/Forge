"""LLM-powered tool: score_lead

Score a lead on fit, intent, and budget.

Implementation notes: Apply ICP scoring model to calculate fit/intent/budget scores

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def score_lead(lead_data) -> str:
    """
    Score a lead on fit, intent, and budget.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "score_lead",
        "description": "Score a lead on fit, intent, and budget.",
        "implementation_approach": "Apply ICP scoring model to calculate fit/intent/budget scores",
        "parameters": {
            "lead_data": lead_data,
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


score_lead_tool = Tool(
    name="score_lead",
    description=(
        "Score a lead on fit, intent, and budget. "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="lead_data",
            type="string",
            description="JSON with lead information (company, role, behavior signals)",
            required=True,
        ),
    ],
    _fn=score_lead,
)