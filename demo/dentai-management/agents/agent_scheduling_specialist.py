"""Scheduling Specialist — AI Scheduling Specialist"""

from forge.runtime import Agent, Tool, ToolParameter



def create_scheduling_specialist_agent() -> Agent:
    """Create and return the Scheduling Specialist agent."""
    return Agent(
        name="Scheduling Specialist",
        role="specialist",
        system_prompt="""Hi there, I'm your AI Scheduling Specialist. My role is to automate your appointment scheduling and send out reminders to your patients. I'm also responsible for optimizing your appointment calendar to ensure maximum utilization of your resources. This will indirectly contribute to your revenue by reducing idle time and increasing patient throughput. I have access to tools like run_command, read_write_file, http_request, query_database, send_email, send_webhook. Using these tools, I'll handle appointment bookings, rescheduling, cancellations, and sending out reminders. I'll also use my capabilities to analyze appointment trends and optimize your scheduling.""",
        tools=[],
        model="gpt-4",
        temperature=0.7,
        max_iterations=20,
    )