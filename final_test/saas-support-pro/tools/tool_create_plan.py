"""Domain tool: create_plan

Create an execution plan by decomposing a task into steps.
"""

from forge.runtime.tools import Tool, ToolParameter


async def create_plan(task, context) -> str:
    """Create an execution plan by decomposing a task into steps."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Create an execution plan by decomposing a task into steps.\n"
        f"  task: {task}\n"
        f"  context: {context}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


create_plan_tool = Tool(
    name="create_plan",
    description="Create an execution plan by decomposing a task into steps.",
    parameters=[
        ToolParameter(name="task", type="string", description="The complex task to plan", required=True),
        ToolParameter(name="context", type="string", description="Additional context (JSON)", required=False),
    ],
    _fn=create_plan,
)
