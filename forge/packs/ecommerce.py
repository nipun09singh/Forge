"""E-Commerce Operations domain pack."""

from forge.core.blueprint import (
    AgencyBlueprint, AgentBlueprint, AgentRole, TeamBlueprint,
    ToolBlueprint, WorkflowBlueprint, WorkflowStep, APIEndpoint,
)


def create_ecommerce_blueprint() -> AgencyBlueprint:
    """Create a pre-built e-commerce operations agency blueprint."""

    order_agent = AgentBlueprint(
        name="Order Manager",
        role=AgentRole.SPECIALIST,
        title="Order Management Specialist",
        system_prompt=(
            "You manage customer orders: tracking, modifications, cancellations, and returns. "
            "You can query the order database, check shipping status via API, and process refunds. "
            "Always confirm order details before making changes. "
            "Return policy: 30 days for unused items, 14 days for electronics."
        ),
        capabilities=["Order tracking", "Order modifications", "Return processing", "Shipping status"],
        tools=[
            ToolBlueprint(name="query_database", description="Query order database", parameters=[
                {"name": "query", "type": "string", "description": "SQL query", "required": True}
            ]),
            ToolBlueprint(name="http_request", description="Check shipping/payment APIs", parameters=[
                {"name": "url", "type": "string", "description": "API URL", "required": True},
                {"name": "method", "type": "string", "description": "HTTP method", "required": False},
            ]),
        ],
        temperature=0.3,
    )

    product_agent = AgentBlueprint(
        name="Product Advisor",
        role=AgentRole.SPECIALIST,
        title="Product Recommendation Specialist",
        system_prompt=(
            "You help customers find the right products. You understand the catalog, "
            "can compare products, suggest alternatives, and make personalized recommendations "
            "based on purchase history. Cross-sell and upsell naturally — suggest complementary products."
        ),
        capabilities=["Product search", "Recommendations", "Comparisons", "Cross-selling"],
        tools=[
            ToolBlueprint(name="query_database", description="Search product catalog", parameters=[
                {"name": "query", "type": "string", "description": "SQL query", "required": True}
            ]),
        ],
        temperature=0.6,
    )

    marketing_agent = AgentBlueprint(
        name="Marketing Specialist",
        role=AgentRole.SPECIALIST,
        title="E-Commerce Marketing Specialist",
        system_prompt=(
            "You create and manage marketing campaigns: email promotions, abandoned cart recovery, "
            "loyalty programs, and seasonal sales. Track conversion rates and ROI. "
            "Segment customers by behavior and personalize messaging."
        ),
        capabilities=["Campaign creation", "Abandoned cart recovery", "Customer segmentation", "A/B testing"],
        tools=[
            ToolBlueprint(name="send_email", description="Send marketing emails", parameters=[
                {"name": "to", "type": "string", "description": "Email", "required": True},
                {"name": "subject", "type": "string", "description": "Subject", "required": True},
                {"name": "body", "type": "string", "description": "Body", "required": True},
            ]),
            ToolBlueprint(name="send_webhook", description="Trigger marketing automation", parameters=[
                {"name": "url", "type": "string", "description": "Webhook URL", "required": True},
                {"name": "payload", "type": "string", "description": "JSON payload", "required": True},
            ]),
        ],
        temperature=0.7,
    )

    ops_lead = AgentBlueprint(
        name="Operations Lead",
        role=AgentRole.MANAGER,
        title="E-Commerce Operations Manager",
        system_prompt=(
            "You oversee all e-commerce operations. Coordinate between order management, "
            "product recommendations, and marketing. Monitor KPIs: conversion rate, AOV, "
            "return rate, customer satisfaction. Identify bottlenecks and optimize."
        ),
        capabilities=["Operations management", "KPI monitoring", "Team coordination", "Process optimization"],
        can_spawn_sub_agents=True,
        temperature=0.4,
    )

    return AgencyBlueprint(
        name="E-Commerce Pro",
        slug="ecommerce-pro",
        description="AI-powered e-commerce operations: orders, products, marketing, and customer service",
        domain="Online retail with order management, product recommendations, and marketing automation",
        teams=[
            TeamBlueprint(
                name="Operations",
                description="Core e-commerce operations and customer service",
                lead=ops_lead,
                agents=[order_agent, product_agent, marketing_agent],
                allow_dynamic_scaling=True,
            ),
        ],
        workflows=[
            WorkflowBlueprint(name="Order Fulfillment", description="End-to-end order processing", trigger="new_order", steps=[
                WorkflowStep(id="validate", description="Validate order and payment"),
                WorkflowStep(id="fulfill", description="Process fulfillment", depends_on=["validate"]),
                WorkflowStep(id="ship", description="Ship and send tracking", depends_on=["fulfill"]),
                WorkflowStep(id="followup", description="Post-delivery follow-up", depends_on=["ship"]),
            ]),
        ],
        api_endpoints=[
            APIEndpoint(path="/api/task", method="POST", description="Submit a task"),
            APIEndpoint(path="/api/orders", method="POST", description="Order operations", handler_team="Operations"),
            APIEndpoint(path="/api/recommend", method="POST", description="Get product recommendations", handler_team="Operations"),
        ],
        model="gpt-4",
    )
