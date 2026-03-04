"""Custom tool: flag_expansion_opportunity"""

from forge.runtime import Tool, ToolParameter


async def flag_expansion_opportunity(customer_id, opportunity_type, estimated_value) -> str:
    """
    Flag a customer for upsell/expansion opportunity.

    Implementation notes: Log opportunity to CRM pipeline, notify sales/growth team
    """
    # TODO: Implement this tool
    # This is a generated stub — replace with real logic
    result = {
        "tool": "flag_expansion_opportunity",
        "customer_id": customer_id,
        "opportunity_type": opportunity_type,
        "estimated_value": estimated_value,
    }
    return str(result)


flag_expansion_opportunity_tool = Tool(
    name="flag_expansion_opportunity",
    description="Flag a customer for upsell/expansion opportunity.",
    parameters=[
        ToolParameter(
            name="customer_id",
            type="string",
            description="Customer identifier",
            required=True,
        ),
        ToolParameter(
            name="opportunity_type",
            type="string",
            description="Type: upsell, cross_sell, plan_upgrade, add_seats",
            required=True,
        ),
        ToolParameter(
            name="estimated_value",
            type="string",
            description="Estimated additional revenue",
            required=True,
        ),
    ],
    _fn=flag_expansion_opportunity,
)