"""Domain tool: add_to_nurture_sequence

Add a lead to an automated nurture sequence.
"""

from forge.runtime.tools import Tool, ToolParameter


async def add_to_nurture_sequence(lead_id, sequence_name) -> str:
    """Add a lead to an automated nurture sequence."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Add a lead to an automated nurture sequence.\n"
        f"  lead_id: {lead_id}\n"
        f"  sequence_name: {sequence_name}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


add_to_nurture_sequence_tool = Tool(
    name="add_to_nurture_sequence",
    description="Add a lead to an automated nurture sequence.",
    parameters=[
        ToolParameter(name="lead_id", type="string", description="Lead identifier", required=True),
        ToolParameter(name="sequence_name", type="string", description="Which nurture sequence to use", required=True),
    ],
    _fn=add_to_nurture_sequence,
)
