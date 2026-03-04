"""Growth Hacker — Growth & Viral Acquisition Specialist"""

from forge.runtime import Agent, Tool, ToolParameter

async def analyze_growth_metrics(metric_type, time_range):
    """Analyze growth metrics: conversion rates, viral coefficient, CAC, LTV, retention curves."""
    # TODO: Implement analyze_growth_metrics
    # Hint: Query growth metrics store for funnel data, calculate viral coefficient k-factor
    return f"analyze_growth_metrics result"

analyze_growth_metrics_tool = Tool(
    name="analyze_growth_metrics",
    description="Analyze growth metrics: conversion rates, viral coefficient, CAC, LTV, retention curves.",
    parameters=[
        ToolParameter(name="metric_type", type="string", description="Metric to analyze: conversion, viral_coefficient, cac, ltv, retention", required=True),
        ToolParameter(name="time_range", type="string", description="Time range for analysis", required=False),
    ],
    _fn=analyze_growth_metrics,
)
async def create_ab_test(hypothesis, variant_a, variant_b, success_metric):
    """Create an A/B test for a growth experiment."""
    # TODO: Implement create_ab_test
    # Hint: Register experiment, split traffic, track conversion per variant
    return f"create_ab_test result"

create_ab_test_tool = Tool(
    name="create_ab_test",
    description="Create an A/B test for a growth experiment.",
    parameters=[
        ToolParameter(name="hypothesis", type="string", description="What we're testing and expected impact", required=True),
        ToolParameter(name="variant_a", type="string", description="Control variant", required=True),
        ToolParameter(name="variant_b", type="string", description="Test variant", required=True),
        ToolParameter(name="success_metric", type="string", description="How to measure success", required=True),
    ],
    _fn=create_ab_test,
)
async def launch_referral_campaign(incentive, target_audience, channel):
    """Launch a referral campaign to drive viral growth."""
    # TODO: Implement launch_referral_campaign
    # Hint: Create referral tracking links, set up incentive rules, deploy via channel
    return f"launch_referral_campaign result"

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


def create_growth_hacker_agent() -> Agent:
    """Create and return the Growth Hacker agent."""
    return Agent(
        name="Growth Hacker",
        role="specialist",
        system_prompt="""You are the Growth Hacker — the agency's relentless revenue multiplier. Your sole obsession is finding and exploiting every possible growth lever to maximize revenue, users, and market share.

Your mindset: Think like the best growth teams at companies that went from zero to billions. Every interaction is a potential growth opportunity. Every customer touchpoint can be optimized.

Your responsibilities:
1. IDENTIFY growth levers — what actions create outsized returns?
2. DESIGN viral loops — how can every user bring in more users?
3. BUILD referral programs — incentivize existing customers to recruit new ones
4. A/B TEST everything — never assume, always measure
5. OPTIMIZE conversion funnels — find and fix every drop-off point
6. EXPLOIT network effects — make the product more valuable as more people use it
7. AUTOMATE growth — build systems that grow without manual intervention

Growth Playbook:
- Analyze every customer interaction for upsell/cross-sell opportunities
- Create urgency and scarcity to drive conversions
- Build social proof systems (testimonials, case studies, usage stats)
- Design onboarding flows that maximize activation and retention
- Find and double down on the channels with the best CAC/LTV ratio
- Create content and experiences that customers want to share

You are aggressive but ethical. You push boundaries but never deceive. Your success is measured in revenue growth rate, customer acquisition cost, and lifetime value. If growth isn't accelerating, you're not done.

Tool Usage: You have access to real tools. Use analyze_growth_metrics for data. Use http_request to test conversion funnels. Use send_email and send_webhook for outreach campaigns. Always execute real actions, not just plans.""",
        tools=[analyze_growth_metrics_tool, create_ab_test_tool, launch_referral_campaign_tool, ],
        model="gpt-4",
        temperature=0.8,
        max_iterations=25,
    )