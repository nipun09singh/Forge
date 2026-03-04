"""Domain tool: score_output

Score an output against quality criteria. Returns structured quality assessment.
"""

from forge.runtime.tools import Tool, ToolParameter


async def score_output(output_text, criteria, context) -> str:
    """Score an output against quality criteria. Returns structured quality assessment."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Score an output against quality criteria. Returns structured quality assessment.\n"
        f"  output_text: {output_text}\n"
        f"  criteria: {criteria}\n"
        f"  context: {context}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


score_output_tool = Tool(
    name="score_output",
    description="Score an output against quality criteria. Returns structured quality assessment.",
    parameters=[
        ToolParameter(name="output_text", type="string", description="The output to evaluate", required=True),
        ToolParameter(name="criteria", type="string", description="Specific criteria to evaluate against", required=False),
        ToolParameter(name="context", type="string", description="Original request context", required=False),
    ],
    _fn=score_output,
)
