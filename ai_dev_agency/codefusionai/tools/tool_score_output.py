"""LLM-powered tool: score_output

Score an output against quality criteria. Returns structured quality assessment.

Implementation notes: Score output on accuracy, completeness, clarity, professionalism (each 1-10), return aggregate

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def score_output(output_text, criteria, context) -> str:
    """
    Score an output against quality criteria. Returns structured quality assessment.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "score_output",
        "description": "Score an output against quality criteria. Returns structured quality assessment.",
        "implementation_approach": "Score output on accuracy, completeness, clarity, professionalism (each 1-10), return aggregate",
        "parameters": {
            "output_text": output_text,
            "criteria": criteria,
            "context": context,
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


score_output_tool = Tool(
    name="score_output",
    description=(
        "Score an output against quality criteria. Returns structured quality assessment. "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="output_text",
            type="string",
            description="The output to evaluate",
            required=True,
        ),
        ToolParameter(
            name="criteria",
            type="string",
            description="Specific criteria to evaluate against",
            required=False,
        ),
        ToolParameter(
            name="context",
            type="string",
            description="Original request context",
            required=False,
        ),
    ],
    _fn=score_output,
)