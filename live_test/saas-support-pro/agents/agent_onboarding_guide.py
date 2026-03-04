"""Onboarding Guide — Customer Onboarding Specialist"""

from forge.runtime import Agent, Tool, ToolParameter

async def send_email(to, subject, body):
    """Send onboarding emails to customers"""
    # TODO: Implement send_email
    # Hint: 
    return f"send_email result"

send_email_tool = Tool(
    name="send_email",
    description="Send onboarding emails to customers",
    parameters=[
        ToolParameter(name="to", type="string", description="Email address", required=True),
        ToolParameter(name="subject", type="string", description="Subject", required=True),
        ToolParameter(name="body", type="string", description="Body", required=True),
    ],
    _fn=send_email,
)


def create_onboarding_guide_agent() -> Agent:
    """Create and return the Onboarding Guide agent."""
    return Agent(
        name="Onboarding Guide",
        role="support",
        system_prompt="""You guide new customers through product setup and first-value experience. Your goal: get every customer to their 'aha moment' within the first 7 days. Walk them through: account setup, key features, first workflow, team invitation. Proactively check in at Day 1, Day 3, and Day 7.""",
        tools=[send_email_tool, ],
        model="gpt-4",
        temperature=0.6,
        max_iterations=20,
    )