"""Customer Success Agent — Customer Success & Retention Specialist"""

from forge.runtime import Agent, Tool, ToolParameter

async def get_customer_health(customer_id):
    """Get health score and risk assessment for a customer."""
    # TODO: Implement get_customer_health
    # Hint: Calculate health score from usage frequency, support tickets, sentiment, payment history
    return f"get_customer_health result"

get_customer_health_tool = Tool(
    name="get_customer_health",
    description="Get health score and risk assessment for a customer.",
    parameters=[
        ToolParameter(name="customer_id", type="string", description="Customer identifier", required=True),
    ],
    _fn=get_customer_health,
)
async def trigger_outreach(customer_id, reason, channel, message):
    """Send a proactive outreach message to a customer."""
    # TODO: Implement trigger_outreach
    # Hint: Send personalized message via specified channel, log interaction
    return f"trigger_outreach result"

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
async def flag_expansion_opportunity(customer_id, opportunity_type, estimated_value):
    """Flag a customer for upsell/expansion opportunity."""
    # TODO: Implement flag_expansion_opportunity
    # Hint: Log opportunity to CRM pipeline, notify sales/growth team
    return f"flag_expansion_opportunity result"

flag_expansion_opportunity_tool = Tool(
    name="flag_expansion_opportunity",
    description="Flag a customer for upsell/expansion opportunity.",
    parameters=[
        ToolParameter(name="customer_id", type="string", description="Customer identifier", required=True),
        ToolParameter(name="opportunity_type", type="string", description="Type: upsell, cross_sell, plan_upgrade, add_seats", required=True),
        ToolParameter(name="estimated_value", type="string", description="Estimated additional revenue", required=True),
    ],
    _fn=flag_expansion_opportunity,
)


def create_customer_success_agent_agent() -> Agent:
    """Create and return the Customer Success Agent agent."""
    return Agent(
        name="Customer Success Agent",
        role="support",
        system_prompt="""You are the Customer Success Agent — the agency's revenue protector. Your job is to make every customer so successful and satisfied that they never leave and keep paying more.

The math is simple: keeping a customer costs 5-7x less than acquiring a new one. Every customer you retain is pure profit. Every customer who upgrades is revenue growth without acquisition cost.

Your responsibilities:
1. PROACTIVELY reach out to customers before they have problems
2. MONITOR customer health scores — catch churn signals early
3. ONBOARD new customers to ensure they see value within the first week
4. IDENTIFY expansion opportunities — who needs more features/capacity?
5. RESOLVE issues before they become cancellation requests
6. COLLECT feedback and turn it into product improvements
7. BUILD relationships — make customers feel like VIPs

Customer Health Signals:
- Usage frequency declining → reach out immediately
- Support tickets increasing → escalate and fix root cause
- No login in 7 days → send re-engagement sequence
- Approaching contract renewal → start success review 30 days early
- Positive sentiment → ask for testimonial/referral

You are warm, proactive, and genuinely care about customer outcomes. Your KPIs: Net Revenue Retention > 120%, Churn Rate < 3%, NPS > 70.""",
        tools=[get_customer_health_tool, trigger_outreach_tool, flag_expansion_opportunity_tool, ],
        model="gpt-4",
        temperature=0.6,
        max_iterations=20,
    )