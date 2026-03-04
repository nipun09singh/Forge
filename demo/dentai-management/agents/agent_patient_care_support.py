"""Patient Care Support — AI Patient Care Support"""

from forge.runtime import Agent, Tool, ToolParameter



def create_patient_care_support_agent() -> Agent:
    """Create and return the Patient Care Support agent."""
    return Agent(
        name="Patient Care Support",
        role="support",
        system_prompt="""Hello! As your AI Patient Care Support, my role is to provide assistance and support to your patients. I contribute to your revenue by improving patient satisfaction and retention. I can answer patient queries, provide information about services and treatments, and assist with appointment scheduling. I have access to these tools: run_command, read_write_file, http_request, query_database, send_email, send_webhook. I'll use these tools to communicate with patients, access necessary information from your systems, and provide appropriate support.""",
        tools=[],
        model="gpt-4",
        temperature=0.7,
        max_iterations=20,
    )