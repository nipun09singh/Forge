"""Domain tool: trigger_outreach

Send a proactive outreach message to a customer.
"""

from forge.runtime.tools import Tool, ToolParameter


async def trigger_outreach(customer_id, reason, channel, message) -> str:
    """Send a proactive outreach message to a customer."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Send a proactive outreach message to a customer.\n"
        f"  customer_id: {customer_id}\n"
        f"  reason: {reason}\n"
        f"  channel: {channel}\n"
        f"  message: {message}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


trigger_outreach_tool = Tool(
    name="trigger_outreach",
    description="Send a proactive outreach message to a customer.",
    parameters=[
        ToolParameter(name="customer_id", type="string", description="Customer identifier", required=True),
        ToolParameter(name="reason", type="string", description="Why we're reaching out", required=True),
        ToolParameter(name="channel", type="string", description="Channel: email, chat, call", required=True),
        ToolParameter(name="message", type="string", description="Outreach message", required=True),
    ],
    _fn=trigger_outreach,
)
