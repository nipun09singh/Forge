"""SaaS Customer Support domain pack."""

from forge.core.blueprint import (
    AgencyBlueprint, AgentBlueprint, AgentRole, TeamBlueprint,
    ToolBlueprint, WorkflowBlueprint, WorkflowStep, APIEndpoint,
)


def create_saas_support_blueprint() -> AgencyBlueprint:
    """Create a pre-built SaaS customer support agency blueprint."""

    # ─── Agents ───
    support_lead = AgentBlueprint(
        name="Support Lead",
        role=AgentRole.MANAGER,
        title="Customer Support Team Lead",
        system_prompt=(
            "You are the Support Team Lead for a SaaS company. You triage incoming support "
            "tickets, delegate to specialists, monitor SLA compliance, and ensure customer "
            "satisfaction. Prioritize by urgency: critical > high > medium > low. "
            "Escalate unresolved issues after 2 hours. Track first-response time and resolution time."
        ),
        capabilities=["Ticket triage", "Team delegation", "SLA monitoring", "Escalation management"],
        can_spawn_sub_agents=True,
        temperature=0.4,
    )

    tech_support = AgentBlueprint(
        name="Technical Support",
        role=AgentRole.SPECIALIST,
        title="Technical Support Engineer",
        system_prompt=(
            "You are a Technical Support Engineer. You handle bug reports, integration issues, "
            "API errors, and platform outages. You can query databases, check system status, "
            "and read log files. Always provide step-by-step solutions with screenshots/code when possible. "
            "If you can't resolve in 3 interactions, escalate to engineering."
        ),
        capabilities=["Bug diagnosis", "API troubleshooting", "Integration support", "Log analysis"],
        tools=[
            ToolBlueprint(name="query_database", description="Query the support database for ticket/customer data", parameters=[
                {"name": "query", "type": "string", "description": "SQL query", "required": True}
            ]),
            ToolBlueprint(name="http_request", description="Check system status and API endpoints", parameters=[
                {"name": "url", "type": "string", "description": "URL to check", "required": True},
                {"name": "method", "type": "string", "description": "HTTP method", "required": False},
            ]),
        ],
        temperature=0.3,
    )

    billing_support = AgentBlueprint(
        name="Billing Support",
        role=AgentRole.SPECIALIST,
        title="Billing & Account Specialist",
        system_prompt=(
            "You handle billing inquiries, plan changes, refund requests, and payment issues. "
            "Refund policy: full refund within 30 days, pro-rated after. "
            "You can look up customer accounts, process plan changes, and issue credits. "
            "Always verify customer identity before making account changes."
        ),
        capabilities=["Billing inquiries", "Refund processing", "Plan changes", "Payment troubleshooting"],
        tools=[
            ToolBlueprint(name="query_database", description="Look up billing and account data", parameters=[
                {"name": "query", "type": "string", "description": "SQL query", "required": True}
            ]),
        ],
        temperature=0.3,
    )

    onboarding_agent = AgentBlueprint(
        name="Onboarding Guide",
        role=AgentRole.SUPPORT,
        title="Customer Onboarding Specialist",
        system_prompt=(
            "You guide new customers through product setup and first-value experience. "
            "Your goal: get every customer to their 'aha moment' within the first 7 days. "
            "Walk them through: account setup, key features, first workflow, team invitation. "
            "Proactively check in at Day 1, Day 3, and Day 7."
        ),
        capabilities=["Guided onboarding", "Feature walkthroughs", "Proactive check-ins", "Best practices"],
        tools=[
            ToolBlueprint(name="send_email", description="Send onboarding emails to customers", parameters=[
                {"name": "to", "type": "string", "description": "Email address", "required": True},
                {"name": "subject", "type": "string", "description": "Subject", "required": True},
                {"name": "body", "type": "string", "description": "Body", "required": True},
            ]),
        ],
        temperature=0.6,
    )

    return AgencyBlueprint(
        name="SaaS Support Pro",
        slug="saas-support-pro",
        description="AI-powered customer support, onboarding, and retention agency for SaaS products",
        domain="SaaS customer support with technical troubleshooting, billing, and onboarding",
        teams=[
            TeamBlueprint(
                name="Support Team",
                description="Front-line customer support handling tickets and inquiries",
                lead=support_lead,
                agents=[tech_support, billing_support, onboarding_agent],
                allow_dynamic_scaling=True,
            ),
        ],
        workflows=[
            WorkflowBlueprint(
                name="Ticket Resolution",
                description="End-to-end support ticket handling",
                trigger="incoming_ticket",
                steps=[
                    WorkflowStep(id="triage", description="Classify ticket by type and urgency"),
                    WorkflowStep(id="assign", description="Route to appropriate specialist", depends_on=["triage"]),
                    WorkflowStep(id="resolve", description="Specialist resolves the issue", depends_on=["assign"]),
                    WorkflowStep(id="qa", description="QA review of resolution quality", depends_on=["resolve"]),
                    WorkflowStep(id="close", description="Close ticket and send satisfaction survey", depends_on=["qa"]),
                ],
            ),
            WorkflowBlueprint(
                name="New Customer Onboarding",
                description="7-day guided onboarding for new customers",
                trigger="new_signup",
                steps=[
                    WorkflowStep(id="welcome", description="Send welcome email and setup guide"),
                    WorkflowStep(id="day1", description="Day 1 check-in: account setup complete?", depends_on=["welcome"]),
                    WorkflowStep(id="day3", description="Day 3 check-in: first workflow created?", depends_on=["day1"]),
                    WorkflowStep(id="day7", description="Day 7 review: activation metrics check", depends_on=["day3"]),
                ],
            ),
        ],
        api_endpoints=[
            APIEndpoint(path="/api/task", method="POST", description="Submit a support task"),
            APIEndpoint(path="/api/tickets", method="POST", description="Create a support ticket", handler_team="Support Team"),
            APIEndpoint(path="/api/onboard", method="POST", description="Start customer onboarding", handler_team="Support Team"),
        ],
        model="gpt-4",
    )
