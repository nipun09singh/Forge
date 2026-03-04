"""Domain tool: get_plan_status

Get the current status and progress of an active plan.
"""

from forge.runtime.tools import Tool, ToolParameter


async def get_plan_status(plan_id) -> str:
    """Get the current status and progress of an active plan."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Get the current status and progress of an active plan.\n"
        f"  plan_id: {plan_id}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


get_plan_status_tool = Tool(
    name="get_plan_status",
    description="Get the current status and progress of an active plan.",
    parameters=[
        ToolParameter(name="plan_id", type="string", description="Plan identifier", required=True),
    ],
    _fn=get_plan_status,
)
