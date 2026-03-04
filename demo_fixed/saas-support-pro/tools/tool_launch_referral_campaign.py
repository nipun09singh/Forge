"""Domain tool: launch_referral_campaign

Launch a referral campaign to drive viral growth.
"""

from forge.runtime.tools import Tool, ToolParameter


async def launch_referral_campaign(incentive, target_audience, channel) -> str:
    """Launch a referral campaign to drive viral growth."""
    # This tool provides context to the agent.
    # The agent will use primitive tools (run_command, read_write_file, http_request)
    # to actually execute the task described here.
    task_context = (
        "Task: Launch a referral campaign to drive viral growth.\n"
        f"  incentive: {incentive}\n"
        f"  target_audience: {target_audience}\n"
        f"  channel: {channel}\n"
        "\nUse your available tools (run_command, read_write_file, http_request, "\n        "query_database) to accomplish this task. Create real files and run real commands."
    )
    return task_context


launch_referral_campaign_tool = Tool(
    name="launch_referral_campaign",
    description="Launch a referral campaign to drive viral growth.",
    parameters=[
        ToolParameter(name="incentive", type="string", description="What referrers get", required=True),
        ToolParameter(name="target_audience", type="string", description="Who to target", required=True),
        ToolParameter(name="channel", type="string", description="Distribution channel: email, social, in-app", required=True),
    ],
    _fn=launch_referral_campaign,
)
