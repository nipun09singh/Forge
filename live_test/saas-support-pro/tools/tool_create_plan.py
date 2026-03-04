"""Custom tool: create_plan"""

from forge.runtime import Tool, ToolParameter


async def create_plan(task, context) -> str:
    """
    Create an execution plan by decomposing a task into steps.

    Implementation notes: Use the Planner module to decompose task into a DAG of PlanSteps
    """
    # TODO: Implement this tool
    # This is a generated stub — replace with real logic
    result = {
        "tool": "create_plan",
        "task": task,
        "context": context,
    }
    return str(result)


create_plan_tool = Tool(
    name="create_plan",
    description="Create an execution plan by decomposing a task into steps.",
    parameters=[
        ToolParameter(
            name="task",
            type="string",
            description="The complex task to plan",
            required=True,
        ),
        ToolParameter(
            name="context",
            type="string",
            description="Additional context (JSON)",
            required=False,
        ),
    ],
    _fn=create_plan,
)