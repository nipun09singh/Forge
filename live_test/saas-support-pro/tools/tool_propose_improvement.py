"""Custom tool: propose_improvement"""

from forge.runtime import Tool, ToolParameter


async def propose_improvement(target, change_type, description, expected_impact) -> str:
    """
    Record a proposed improvement for review.

    Implementation notes: Log proposal to improvement backlog for human review or auto-apply
    """
    # TODO: Implement this tool
    # This is a generated stub — replace with real logic
    result = {
        "tool": "propose_improvement",
        "target": target,
        "change_type": change_type,
        "description": description,
        "expected_impact": expected_impact,
    }
    return str(result)


propose_improvement_tool = Tool(
    name="propose_improvement",
    description="Record a proposed improvement for review.",
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