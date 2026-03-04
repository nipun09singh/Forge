"""Domain tool: adjust_plan

Modify an active plan — add, remove, or reassign steps.
"""

from forge.runtime.tools import Tool, ToolParameter


async def adjust_plan(plan_id, adjustment) -> str:
    """Modify an active plan — add, remove, or reassign steps."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Modify an active plan — add, remove, or reassign steps.\n"
        f"  plan_id: {plan_id}\n"
        f"  adjustment: {adjustment}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


adjust_plan_tool = Tool(
    name="adjust_plan",
    description="Modify an active plan — add, remove, or reassign steps.",
    parameters=[
        ToolParameter(name="plan_id", type="string", description="Plan identifier", required=True),
        ToolParameter(name="adjustment", type="string", description="Description of what to change", required=True),
    ],
    _fn=adjust_plan,
)
