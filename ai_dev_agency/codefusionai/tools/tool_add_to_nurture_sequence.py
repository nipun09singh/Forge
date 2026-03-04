"""LLM-powered tool: add_to_nurture_sequence

Add a lead to an automated nurture sequence.

Implementation notes: Enroll lead in drip campaign, schedule follow-ups

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def add_to_nurture_sequence(lead_id, sequence_name) -> str:
    """
    Add a lead to an automated nurture sequence.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "add_to_nurture_sequence",
        "description": "Add a lead to an automated nurture sequence.",
        "implementation_approach": "Enroll lead in drip campaign, schedule follow-ups",
        "parameters": {
            "lead_id": lead_id,
            "sequence_name": sequence_name,
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


add_to_nurture_sequence_tool = Tool(
    name="add_to_nurture_sequence",
    description=(
        "Add a lead to an automated nurture sequence. "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="lead_id",
            type="string",
            description="Lead identifier",
            required=True,
        ),
        ToolParameter(
            name="sequence_name",
            type="string",
            description="Which nurture sequence to use",
            required=True,
        ),
    ],
    _fn=add_to_nurture_sequence,
)