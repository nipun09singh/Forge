"""Domain tool: propose_improvement

Record a proposed improvement for review.
"""

from forge.runtime.tools import Tool, ToolParameter


async def propose_improvement(target, change_type, description, expected_impact) -> str:
    """Record a proposed improvement for review."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Record a proposed improvement for review.\n"
        f"  target: {target}\n"
        f"  change_type: {change_type}\n"
        f"  description: {description}\n"
        f"  expected_impact: {expected_impact}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


propose_improvement_tool = Tool(
    name="propose_improvement",
    description="Record a proposed improvement for review.",
    parameters=[
        ToolParameter(name="target", type="string", description="What to improve (agent name, workflow, tool)", required=True),
        ToolParameter(name="change_type", type="string", description="Type: prompt_update, new_tool, workflow_change, config_change", required=True),
        ToolParameter(name="description", type="string", description="Detailed description of the proposed change", required=True),
        ToolParameter(name="expected_impact", type="string", description="Expected improvement", required=True),
    ],
    _fn=propose_improvement,
)
