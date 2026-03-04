"""Real Estate Agency domain pack."""

from forge.core.blueprint import (
    AgencyBlueprint, AgentBlueprint, AgentRole, TeamBlueprint,
    ToolBlueprint, WorkflowBlueprint, WorkflowStep, APIEndpoint,
)


def create_real_estate_blueprint() -> AgencyBlueprint:
    """Create a pre-built real estate agency blueprint."""

    lead_gen = AgentBlueprint(
        name="Lead Generator",
        role=AgentRole.SPECIALIST,
        title="Real Estate Lead Generation Specialist",
        system_prompt=(
            "You find and qualify real estate leads. Source leads from inquiries, website visits, "
            "referrals, and social media. Score leads on: budget, timeline, location preference, "
            "and engagement level. Qualify leads before passing to agents."
        ),
        capabilities=["Lead sourcing", "Lead scoring", "Pipeline management", "Outreach"],
        tools=[
            ToolBlueprint(name="query_database", description="Search leads database", parameters=[
                {"name": "query", "type": "string", "description": "SQL query", "required": True}
            ]),
            ToolBlueprint(name="send_email", description="Send outreach emails", parameters=[
                {"name": "to", "type": "string", "description": "Email", "required": True},
                {"name": "subject", "type": "string", "description": "Subject", "required": True},
                {"name": "body", "type": "string", "description": "Body", "required": True},
            ]),
        ],
        temperature=0.5,
    )

    property_matcher = AgentBlueprint(
        name="Property Matcher",
        role=AgentRole.SPECIALIST,
        title="Property Matching Specialist",
        system_prompt=(
            "You match buyers with properties based on their criteria: budget, location, size, "
            "amenities, school district, commute. Search the MLS database, compare options, "
            "create shortlists, and schedule viewings. Know the local market intimately."
        ),
        capabilities=["Property search", "Market analysis", "Comparative analysis", "Shortlist creation"],
        tools=[
            ToolBlueprint(name="query_database", description="Search property listings", parameters=[
                {"name": "query", "type": "string", "description": "SQL query", "required": True}
            ]),
            ToolBlueprint(name="http_request", description="Query MLS and property APIs", parameters=[
                {"name": "url", "type": "string", "description": "API URL", "required": True},
                {"name": "method", "type": "string", "description": "Method", "required": False},
            ]),
        ],
        temperature=0.4,
    )

    broker_lead = AgentBlueprint(
        name="Broker Lead",
        role=AgentRole.MANAGER,
        title="Managing Broker",
        system_prompt=(
            "You oversee all real estate operations. Coordinate lead generation, property matching, "
            "and client management. Monitor: leads generated, conversion rate, average days to close, "
            "commission revenue. Ensure compliance with real estate regulations."
        ),
        capabilities=["Team management", "Deal oversight", "Compliance", "Revenue tracking"],
        can_spawn_sub_agents=True,
        temperature=0.4,
    )

    return AgencyBlueprint(
        name="RealEstate AI",
        slug="realestate-ai",
        description="AI-powered real estate agency: lead generation, property matching, and client management",
        domain="Residential real estate with lead generation, property search, and transaction management",
        teams=[
            TeamBlueprint(
                name="Brokerage",
                description="Core real estate operations",
                lead=broker_lead,
                agents=[lead_gen, property_matcher],
                allow_dynamic_scaling=True,
            ),
        ],
        workflows=[
            WorkflowBlueprint(name="Lead to Close", description="Full pipeline from lead to closed deal", trigger="new_lead", steps=[
                WorkflowStep(id="qualify", description="Score and qualify the lead"),
                WorkflowStep(id="match", description="Match with suitable properties", depends_on=["qualify"]),
                WorkflowStep(id="schedule", description="Schedule property viewings", depends_on=["match"]),
                WorkflowStep(id="negotiate", description="Handle offers and negotiations", depends_on=["schedule"]),
                WorkflowStep(id="close", description="Process closing documents", depends_on=["negotiate"]),
            ]),
        ],
        api_endpoints=[
            APIEndpoint(path="/api/task", method="POST", description="Submit a task"),
            APIEndpoint(path="/api/leads", method="POST", description="Submit a new lead", handler_team="Brokerage"),
            APIEndpoint(path="/api/properties/search", method="POST", description="Search properties", handler_team="Brokerage"),
        ],
        model="gpt-4",
    )
