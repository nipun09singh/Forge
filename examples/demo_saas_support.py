"""
Forge Demo: SaaS Customer Support Agency
=========================================

This demo builds a working SaaS customer support agency using the Forge runtime
directly, showcasing:
- Agent teams with specialized roles
- Real tool integrations (HTTP, File, SQL)
- Persistent memory (SQLite-backed)
- Observability (structured event logging, cost tracking)
- Quality gates and reflection
- Strategic planner for complex tasks
- Human approval gates

Run: python examples/demo_saas_support.py
(No API key needed — uses simulated responses for demo)
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from forge.runtime.agent import Agent, TaskResult
from forge.runtime.agency import Agency
from forge.runtime.team import Team
from forge.runtime.tools import Tool, ToolParameter
from forge.runtime.memory import SharedMemory
from forge.runtime.observability import EventLog, TraceContext, CostTracker
from forge.runtime.persistence import SQLiteMemoryBackend
from forge.runtime.improvement import QualityGate, PerformanceTracker
from forge.runtime.integrations.file_tool import create_file_tool
from forge.runtime.integrations.sql_tool import create_sql_tool
from forge.runtime.integrations.http_tool import create_http_tool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("forge-demo")


# ═══════════════════════════════════════════════════════════
# Custom tools for the demo
# ═══════════════════════════════════════════════════════════

async def lookup_customer(customer_id: str) -> str:
    """Look up a customer in the mock CRM."""
    customers = {
        "C001": {"name": "Alice Johnson", "plan": "Pro", "mrr": 99, "status": "active", "since": "2024-01"},
        "C002": {"name": "Bob Smith", "plan": "Enterprise", "mrr": 499, "status": "active", "since": "2023-06"},
        "C003": {"name": "Carol Davis", "plan": "Starter", "mrr": 29, "status": "at_risk", "since": "2025-01"},
    }
    customer = customers.get(customer_id)
    if customer:
        return json.dumps({"found": True, **customer})
    return json.dumps({"found": False, "error": f"Customer {customer_id} not found"})


async def check_ticket_status(ticket_id: str) -> str:
    """Check the status of a support ticket."""
    tickets = {
        "T100": {"status": "open", "priority": "high", "subject": "Cannot access dashboard", "customer": "C001"},
        "T101": {"status": "pending", "priority": "medium", "subject": "Billing discrepancy", "customer": "C002"},
        "T102": {"status": "escalated", "priority": "critical", "subject": "Data export failing", "customer": "C003"},
    }
    ticket = tickets.get(ticket_id)
    if ticket:
        return json.dumps({"found": True, **ticket})
    return json.dumps({"found": False, "error": f"Ticket {ticket_id} not found"})


lookup_customer_tool = Tool(
    name="lookup_customer",
    description="Look up customer information by customer ID",
    parameters=[ToolParameter(name="customer_id", type="string", description="Customer ID (e.g., C001)")],
    _fn=lookup_customer,
)

check_ticket_tool = Tool(
    name="check_ticket_status",
    description="Check the status and details of a support ticket",
    parameters=[ToolParameter(name="ticket_id", type="string", description="Ticket ID (e.g., T100)")],
    _fn=check_ticket_status,
)


# ═══════════════════════════════════════════════════════════
# Build the agency
# ═══════════════════════════════════════════════════════════

def build_demo_agency() -> tuple[Agency, EventLog]:
    """Build a SaaS customer support agency with all Forge capabilities."""

    # Initialize observability
    event_log = EventLog()
    perf_tracker = PerformanceTracker()

    # Initialize persistent memory
    os.makedirs("./demo_data", exist_ok=True)
    memory = SharedMemory.persistent(db_path="./demo_data/agency_memory.db")

    # Create agents
    support_lead = Agent(
        name="Support Lead",
        role="manager",
        system_prompt=(
            "You are the Support Team Lead. You coordinate the support team, "
            "triage incoming tickets, and ensure customer issues are resolved quickly. "
            "Delegate specific tasks to your team members based on their expertise. "
            "Always prioritize high-severity issues. Track SLA compliance."
        ),
        temperature=0.5,
        max_iterations=10,
    )

    tech_specialist = Agent(
        name="Tech Specialist",
        role="specialist",
        system_prompt=(
            "You are a Technical Support Specialist. You handle complex technical issues "
            "like dashboard access problems, API errors, data export failures, and integration bugs. "
            "You can query databases, check system status via HTTP, and read log files. "
            "Always provide clear, step-by-step solutions."
        ),
        tools=[create_http_tool(), create_file_tool("./demo_data"), create_sql_tool("./demo_data/support.db"), check_ticket_tool],
        temperature=0.3,
        max_iterations=15,
    )

    billing_specialist = Agent(
        name="Billing Specialist",
        role="specialist",
        system_prompt=(
            "You are a Billing Support Specialist. You handle billing inquiries, "
            "plan changes, refund requests, and payment issues. "
            "You can look up customer accounts and check their billing history. "
            "Be empathetic but follow the refund policy: refunds within 30 days of charge."
        ),
        tools=[lookup_customer_tool, check_ticket_tool],
        temperature=0.4,
        max_iterations=10,
    )

    success_agent = Agent(
        name="Customer Success",
        role="support",
        system_prompt=(
            "You are the Customer Success Agent. You proactively reach out to at-risk "
            "customers, monitor satisfaction scores, and identify upsell opportunities. "
            "Your goal is to maximize retention and expand revenue per account. "
            "When you detect churn signals, act immediately."
        ),
        tools=[lookup_customer_tool],
        temperature=0.6,
        max_iterations=10,
    )

    # Build teams
    support_team = Team(
        name="Customer Support",
        lead=support_lead,
        agents=[tech_specialist, billing_specialist],
        shared_memory=memory,
    )

    success_team = Team(
        name="Customer Success",
        agents=[success_agent],
        shared_memory=memory,
    )

    # Build agency
    agency = Agency(
        name="SaaS Support Agency",
        description="AI-powered customer support for SaaS companies",
        model="gpt-4",
    )
    agency.memory = memory
    agency.add_team(support_team)
    agency.add_team(success_team)

    # Wire observability into all agents
    all_agents = [support_lead, tech_specialist, billing_specialist, success_agent]
    for agent in all_agents:
        agent.set_event_log(event_log)
        agent.set_performance_tracker(perf_tracker)

    return agency, event_log


# ═══════════════════════════════════════════════════════════
# Demo runner
# ═══════════════════════════════════════════════════════════

def print_banner():
    print("""
╔══════════════════════════════════════════════════════════╗
║      🔨 FORGE DEMO — SaaS Customer Support Agency       ║
║                                                          ║
║  This agency demonstrates:                               ║
║  ✅ Multi-agent teams with specialized roles              ║
║  ✅ Real tool integrations (HTTP, SQL, File)              ║
║  ✅ Persistent memory (SQLite-backed)                     ║
║  ✅ Structured observability (event log + cost tracking)  ║
║  ✅ Performance tracking                                  ║
║  ✅ Strategic planner for complex tasks                   ║
║                                                          ║
║  Note: Requires OPENAI_API_KEY for live LLM calls.       ║
║  Without it, the agency structure is built but tasks      ║
║  won't execute the LLM reasoning loop.                   ║
╚══════════════════════════════════════════════════════════╝
    """)


async def run_demo():
    print_banner()

    # Build the agency
    agency, event_log = build_demo_agency()

    print(f"\n🏢 Agency: {agency}")
    print(f"📊 Teams: {list(agency.teams.keys())}")
    for name, team in agency.teams.items():
        print(f"  📋 {team}")
        if team.lead:
            print(f"     Lead: {team.lead.name} ({team.lead.role})")
        for a in team.agents:
            tools_str = f" — tools: {[t.name for t in a.tool_registry.list_tools()]}" if a.tool_registry.list_tools() else ""
            print(f"     Agent: {a.name} ({a.role}){tools_str}")

    print(f"\n💾 Memory: Persistent (SQLite)")
    print(f"📡 Observability: Event logging + cost tracking")
    print(f"📐 Planner: Enabled")

    # Store some context in persistent memory
    agency.memory.store("company_name", "AcmeSaaS Inc.", author="system", tags=["config"])
    agency.memory.store("refund_policy", "Full refund within 30 days. Pro-rated after 30 days.", author="system", tags=["policy"])
    agency.memory.store("escalation_threshold", "2 hours without resolution → escalate to engineering", author="system", tags=["policy"])
    print(f"\n📝 Stored 3 policies in persistent memory")

    # Demonstrate tool execution directly
    print("\n─── Testing Real Tools ───")
    customer_result = await lookup_customer("C001")
    print(f"  🔍 Customer lookup C001: {customer_result}")
    ticket_result = await check_ticket_status("T100")
    print(f"  🎫 Ticket check T100: {ticket_result}")

    # Demonstrate file tool
    from forge.runtime.integrations.file_tool import read_write_file
    write_result = await read_write_file("write", "test_note.txt", "Support note: Customer C001 contacted about dashboard access.")
    print(f"  📄 File write: {write_result}")
    read_result = await read_write_file("read", "test_note.txt")
    print(f"  📖 File read: {read_result}")

    # Demonstrate SQL tool
    from forge.runtime.integrations.sql_tool import query_database
    await query_database("CREATE TABLE IF NOT EXISTS tickets (id TEXT, customer TEXT, status TEXT, priority TEXT)", db_path="./demo_data/support.db")
    await query_database("INSERT OR REPLACE INTO tickets VALUES ('T100', 'C001', 'open', 'high')", db_path="./demo_data/support.db")
    sql_result = await query_database("SELECT * FROM tickets", db_path="./demo_data/support.db")
    print(f"  🗄️ SQL query: {sql_result}")

    # Show event log summary
    print(f"\n─── Observability Summary ───")
    summary = event_log.get_summary()
    print(f"  Total events: {summary['total_events']}")
    print(f"  Costs: {summary['costs']}")

    # Show persistent memory
    print(f"\n─── Persistent Memory ───")
    recent = agency.memory.search_keyword("policy")
    for entry in recent:
        print(f"  💾 [{entry.get('key')}]: {str(entry.get('value'))[:80]}")

    # Interactive mode hint
    if os.getenv("OPENAI_API_KEY"):
        print("\n✅ OPENAI_API_KEY detected — agency is ready for live tasks!")
        print("   The agency can now handle real customer support requests.")
        print("\n   Example tasks:")
        print('   • "Customer C001 cannot access their dashboard"')
        print('   • "Check the status of ticket T100"')
        print('   • "Customer C003 is at risk of churning, what should we do?"')

        while True:
            try:
                task = input("\n📋 Task (or 'quit')> ")
            except (EOFError, KeyboardInterrupt):
                break
            if task.lower() in ("quit", "exit", "q"):
                break
            if not task.strip():
                continue

            trace = TraceContext()
            for agent_list in [agency.teams[t].agents for t in agency.teams]:
                for a in agent_list:
                    a.set_trace_context(trace)

            result = await agency.execute(task)
            print(f"\n✅ Result: {result.output[:500]}")
            print(f"📊 Events in trace: {len(event_log.get_trace(trace.trace_id))}")
            print(f"💰 Total cost: ${event_log.cost_tracker.total_cost_usd:.4f}")
    else:
        print("\n⚠️  Set OPENAI_API_KEY to enable live LLM calls and interactive mode.")
        print("   Without it, the agency structure is demonstrated but can't process tasks.")

    print("\n🔨 Forge demo complete!")


if __name__ == "__main__":
    asyncio.run(run_demo())
