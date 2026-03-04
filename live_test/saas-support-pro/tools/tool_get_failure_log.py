"""Custom tool: get_failure_log"""

from forge.runtime import Tool, ToolParameter


async def get_failure_log(agent_name, limit) -> str:
    """
    Retrieve recent failures and their details.

    Implementation notes: Query failure/error log for recent issues with stack traces and context
    """
    # TODO: Implement this tool
    # This is a generated stub — replace with real logic
    result = {
        "tool": "get_failure_log",
        "agent_name": agent_name,
        "limit": limit,
    }
    return str(result)


get_failure_log_tool = Tool(
    name="get_failure_log",
    description="Retrieve recent failures and their details.",
    parameters=[
        ToolParameter(
            name="agent_name",
            type="string",
            description="Agent name (or 'all')",
            required=False,
        ),
        ToolParameter(
            name="limit",
            type="integer",
            description="Max failures to return",
            required=False,
        ),
    ],
    _fn=get_failure_log,
)