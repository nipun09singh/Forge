"""Custom tool: get_plan_status"""

from forge.runtime import Tool, ToolParameter


async def get_plan_status(plan_id) -> str:
    """
    Get the current status and progress of an active plan.

    Implementation notes: Query the Planner for plan status, step completion, and blockers
    """
    # TODO: Implement this tool
    # This is a generated stub — replace with real logic
    result = {
        "tool": "get_plan_status",
        "plan_id": plan_id,
    }
    return str(result)


get_plan_status_tool = Tool(
    name="get_plan_status",
    description="Get the current status and progress of an active plan.",
    parameters=[
        ToolParameter(
            name="plan_id",
            type="string",
            description="Plan identifier",
            required=True,
        ),
    ],
    _fn=get_plan_status,
)