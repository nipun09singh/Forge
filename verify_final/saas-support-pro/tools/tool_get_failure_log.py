"""Domain tool: get_failure_log

Retrieve recent failures and their details.
"""

from forge.runtime.tools import Tool, ToolParameter


async def get_failure_log(agent_name, limit) -> str:
    """Retrieve recent failures and their details."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Retrieve recent failures and their details.\n"
        f"  agent_name: {agent_name}\n"
        f"  limit: {limit}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


get_failure_log_tool = Tool(
    name="get_failure_log",
    description="Retrieve recent failures and their details.",
    parameters=[
        ToolParameter(name="agent_name", type="string", description="Agent name (or 'all')", required=False),
        ToolParameter(name="limit", type="integer", description="Max failures to return", required=False),
    ],
    _fn=get_failure_log,
)
