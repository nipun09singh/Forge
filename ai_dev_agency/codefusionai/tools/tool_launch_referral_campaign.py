"""LLM-powered tool: launch_referral_campaign

Launch a referral campaign to drive viral growth.

Implementation notes: Create referral tracking links, set up incentive rules, deploy via channel

This tool uses the agent's LLM reasoning to figure out HOW to accomplish the task,
then uses real tools (run_command, read_write_file, http_request) to execute.
"""

import json
from forge.runtime.tools import Tool, ToolParameter


async def launch_referral_campaign(incentive, target_audience, channel) -> str:
    """
    Launch a referral campaign to drive viral growth.

    This is an LLM-powered tool. Instead of hardcoded logic, it returns a detailed
    action plan that the agent will execute using real tools (run_command, read_write_file, http_request).
    """
    # Build a structured task description for the agent to execute
    task = {
        "tool": "launch_referral_campaign",
        "description": "Launch a referral campaign to drive viral growth.",
        "implementation_approach": "Create referral tracking links, set up incentive rules, deploy via channel",
        "parameters": {
            "incentive": incentive,
            "target_audience": target_audience,
            "channel": channel,
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


launch_referral_campaign_tool = Tool(
    name="launch_referral_campaign",
    description=(
        "Launch a referral campaign to drive viral growth. "
        "This tool returns an action plan. Use run_command, read_write_file, and http_request "
        "to execute the plan and produce real results."
    ),
    parameters=[
        ToolParameter(
            name="incentive",
            type="string",
            description="What referrers get",
            required=True,
        ),
        ToolParameter(
            name="target_audience",
            type="string",
            description="Who to target",
            required=True,
        ),
        ToolParameter(
            name="channel",
            type="string",
            description="Distribution channel: email, social, in-app",
            required=True,
        ),
    ],
    _fn=launch_referral_campaign,
)