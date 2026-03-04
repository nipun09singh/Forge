"""Custom tool: add_to_nurture_sequence"""

from forge.runtime import Tool, ToolParameter


async def add_to_nurture_sequence(lead_id, sequence_name) -> str:
    """
    Add a lead to an automated nurture sequence.

    Implementation notes: Enroll lead in drip campaign, schedule follow-ups
    """
    # TODO: Implement this tool
    # This is a generated stub — replace with real logic
    result = {
        "tool": "add_to_nurture_sequence",
        "lead_id": lead_id,
        "sequence_name": sequence_name,
    }
    return str(result)


add_to_nurture_sequence_tool = Tool(
    name="add_to_nurture_sequence",
    description="Add a lead to an automated nurture sequence.",
    parameters=[
        ToolParameter(
            name="lead_id",
            type="string",
            description="Lead identifier",
            required=True,
        ),
        ToolParameter(
            name="sequence_name",
            type="string",
            description="Which nurture sequence to use",
            required=True,
        ),
    ],
    _fn=add_to_nurture_sequence,
)