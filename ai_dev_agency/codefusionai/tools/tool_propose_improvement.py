"""LLM-powered tool: propose_improvement

Record a proposed improvement for review.

Implementation notes: Log proposal to improvement backlog for human review or auto-apply

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def propose_improvement(target, change_type, description, expected_impact) -> str:
    """
    Record a proposed improvement for review.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "propose_improvement",
        "description": "Record a proposed improvement for review.",
        "implementation_approach": "Log proposal to improvement backlog for human review or auto-apply",
        "parameters": {
            "target": target,
            "change_type": change_type,
            "description": description,
            "expected_impact": expected_impact,
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


propose_improvement_tool = Tool(
    name="propose_improvement",
    description=(
        "Record a proposed improvement for review. "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="target",
            type="string",
            description="What to improve (agent name, workflow, tool)",
            required=True,
        ),
        ToolParameter(
            name="change_type",
            type="string",
            description="Type: prompt_update, new_tool, workflow_change, config_change",
            required=True,
        ),
        ToolParameter(
            name="description",
            type="string",
            description="Detailed description of the proposed change",
            required=True,
        ),
        ToolParameter(
            name="expected_impact",
            type="string",
            description="Expected improvement",
            required=True,
        ),
    ],
    _fn=propose_improvement,
)