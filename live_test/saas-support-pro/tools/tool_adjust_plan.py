"""Custom tool: adjust_plan"""

from forge.runtime import Tool, ToolParameter


async def adjust_plan(plan_id, adjustment) -> str:
    """
    Modify an active plan — add, remove, or reassign steps.

    Implementation notes: Modify the TaskPlan DAG — add/remove steps, change assignments
    """
    # TODO: Implement this tool
    # This is a generated stub — replace with real logic
    result = {
        "tool": "adjust_plan",
        "plan_id": plan_id,
        "adjustment": adjustment,
    }
    return str(result)


adjust_plan_tool = Tool(
    name="adjust_plan",
    description="Modify an active plan — add, remove, or reassign steps.",
    parameters=[
        ToolParameter(
            name="plan_id",
            type="string",
            description="Plan identifier",
            required=True,
        ),
        ToolParameter(
            name="adjustment",
            type="string",
            description="Description of what to change",
            required=True,
        ),
    ],
    _fn=adjust_plan,
)