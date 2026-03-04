"""Custom tool: trigger_outreach"""

from forge.runtime import Tool, ToolParameter


async def trigger_outreach(customer_id, reason, channel, message) -> str:
    """
    Send a proactive outreach message to a customer.

    Implementation notes: Send personalized message via specified channel, log interaction
    """
    # TODO: Implement this tool
    # This is a generated stub — replace with real logic
    result = {
        "tool": "trigger_outreach",
        "customer_id": customer_id,
        "reason": reason,
        "channel": channel,
        "message": message,
    }
    return str(result)


trigger_outreach_tool = Tool(
    name="trigger_outreach",
    description="Send a proactive outreach message to a customer.",
    parameters=[
        ToolParameter(
            name="customer_id",
            type="string",
            description="Customer identifier",
            required=True,
        ),
        ToolParameter(
            name="reason",
            type="string",
            description="Why we're reaching out",
            required=True,
        ),
        ToolParameter(
            name="channel",
            type="string",
            description="Channel: email, chat, call",
            required=True,
        ),
        ToolParameter(
            name="message",
            type="string",
            description="Outreach message",
            required=True,
        ),
    ],
    _fn=trigger_outreach,
)