"""LLM-powered tool: trigger_outreach

Send a proactive outreach message to a customer.

Implementation notes: Send personalized message via specified channel, log interaction

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def trigger_outreach(customer_id, reason, channel, message) -> str:
    """
    Send a proactive outreach message to a customer.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "trigger_outreach",
        "description": "Send a proactive outreach message to a customer.",
        "implementation_approach": "Send personalized message via specified channel, log interaction",
        "parameters": {
            "customer_id": customer_id,
            "reason": reason,
            "channel": channel,
            "message": message,
        },
        "instructions": (
            "Execute this task using the available tools: "
            "run_command (to execute shell commands), "
            "read_write_file (to create/read files), "
            "http_request (to call APIs). "
            "Be specific and actually perform the actions, don't just describe them. "
            "Create real files, run real commands, produce real output."
        ),
    }
    return json.dumps(task, indent=2, default=str)


trigger_outreach_tool = Tool(
    name="trigger_outreach",
    description=(
        "Send a proactive outreach message to a customer. "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
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