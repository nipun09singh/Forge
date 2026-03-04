"""
Forge End-to-End Verification
==============================

Proves the entire Forge pipeline works without needing an LLM API key.
Creates a mock blueprint programmatically, runs it through archetypes,
quality evaluation, and code generation, then verifies the output.

Run: python examples/verify_forge.py
"""

import json
import shutil
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    print("=" * 60)
    print("🔨 FORGE END-TO-END VERIFICATION")
    print("=" * 60)

    results = []

    def check(name: str, condition: bool, detail: str = ""):
        status = "✅ PASS" if condition else "❌ FAIL"
        results.append((name, condition))
        print(f"  {status}  {name}")
        if detail and not condition:
            print(f"         → {detail}")

    # ─── Step 1: Import all modules ───────────────────────
    print("\n📦 Step 1: Import Verification")
    try:
        from forge.core.blueprint import (
            AgencyBlueprint, AgentBlueprint, AgentRole, TeamBlueprint,
            ToolBlueprint, WorkflowBlueprint, WorkflowStep, APIEndpoint,
        )
        check("Core blueprint models", True)
    except Exception as e:
        check("Core blueprint models", False, str(e))
        print("FATAL: Cannot proceed without blueprint models")
        return

    try:
        from forge.core.quality import BlueprintEvaluator, QualityRubric, format_quality_report
        check("Quality evaluation", True)
    except Exception as e:
        check("Quality evaluation", False, str(e))

    try:
        from forge.core.archetypes import inject_archetypes, UNIVERSAL_ARCHETYPES
        check("Universal archetypes", True)
    except Exception as e:
        check("Universal archetypes", False, str(e))

    try:
        from forge.core.critic import BlueprintCritic, RefinementLoop, BusinessAmbitionCritic
        check("Critic system", True)
    except Exception as e:
        check("Critic system", False, str(e))

    try:
        from forge.generators.agency_generator import AgencyGenerator
        check("Agency generator", True)
    except Exception as e:
        check("Agency generator", False, str(e))

    try:
        from forge.runtime import Agent, Agency, Team, Tool, ToolParameter, SharedMemory, Router
        check("Runtime core", True)
    except Exception as e:
        check("Runtime core", False, str(e))

    try:
        from forge.runtime.planner import Planner, TaskPlan, PlanStep
        check("Strategic planner", True)
    except Exception as e:
        check("Strategic planner", False, str(e))

    try:
        from forge.runtime.observability import EventLog, TraceContext, CostTracker
        check("Observability", True)
    except Exception as e:
        check("Observability", False, str(e))

    try:
        from forge.runtime.persistence import SQLiteMemoryBackend, InMemoryBackend
        check("Persistent memory", True)
    except Exception as e:
        check("Persistent memory", False, str(e))

    try:
        from forge.runtime.improvement import QualityGate, PerformanceTracker, ReflectionEngine
        check("Self-improvement", True)
    except Exception as e:
        check("Self-improvement", False, str(e))

    try:
        from forge.runtime.human import HumanApprovalGate, ApprovalRequest, ApprovalDecision
        check("Human approval", True)
    except Exception as e:
        check("Human approval", False, str(e))

    try:
        from forge.runtime.integrations import BuiltinToolkit
        check("Built-in integrations", True)
    except Exception as e:
        check("Built-in integrations", False, str(e))

    # ─── Step 2: Create mock blueprint ────────────────────
    print("\n📋 Step 2: Blueprint Creation")

    support_agent = AgentBlueprint(
        name="Support Specialist",
        role=AgentRole.SPECIALIST,
        title="Customer Support Specialist",
        system_prompt="You are a helpful customer support specialist. You resolve customer issues quickly and professionally.",
        capabilities=["Answer questions", "Troubleshoot issues", "Process refunds"],
        tools=[
            ToolBlueprint(name="http_request", description="Make HTTP API calls", parameters=[
                {"name": "url", "type": "string", "description": "URL to call", "required": True}
            ]),
            ToolBlueprint(name="query_database", description="Query the customer database", parameters=[
                {"name": "query", "type": "string", "description": "SQL query", "required": True}
            ]),
        ],
        temperature=0.4,
    )

    sales_agent = AgentBlueprint(
        name="Sales Agent",
        role=AgentRole.SPECIALIST,
        title="Sales & Upsell Specialist",
        system_prompt="You identify upsell opportunities during support interactions. You are persuasive but not pushy.",
        capabilities=["Identify upsell opportunities", "Present upgrade options", "Track conversion"],
        temperature=0.7,
    )

    team_lead = AgentBlueprint(
        name="Team Lead",
        role=AgentRole.MANAGER,
        title="Support Team Lead",
        system_prompt="You coordinate the support team. Triage tickets, delegate to specialists, ensure SLA compliance.",
        capabilities=["Triage tickets", "Delegate tasks", "Monitor SLAs"],
        temperature=0.5,
        can_spawn_sub_agents=True,
    )

    blueprint = AgencyBlueprint(
        name="Demo Support Agency",
        slug="demo-support-agency",
        description="AI-powered customer support for a SaaS product",
        domain="SaaS customer support with upselling and retention capabilities",
        teams=[
            TeamBlueprint(
                name="Support Team",
                description="Handles customer support tickets and inquiries",
                lead=team_lead,
                agents=[support_agent, sales_agent],
                allow_dynamic_scaling=True,
            ),
        ],
        workflows=[
            WorkflowBlueprint(
                name="Ticket Resolution",
                description="End-to-end ticket handling",
                trigger="incoming_ticket",
                steps=[
                    WorkflowStep(id="triage", description="Classify and prioritize ticket"),
                    WorkflowStep(id="assign", description="Assign to specialist", depends_on=["triage"]),
                    WorkflowStep(id="resolve", description="Resolve the issue", depends_on=["assign"]),
                    WorkflowStep(id="review", description="QA review of resolution", depends_on=["resolve"]),
                ],
            ),
        ],
        api_endpoints=[
            APIEndpoint(path="/api/task", method="POST", description="Submit a task"),
            APIEndpoint(path="/api/tickets", method="POST", description="Create a support ticket", handler_team="Support Team"),
        ],
        shared_tools=[
            ToolBlueprint(name="send_webhook", description="Send notifications", parameters=[
                {"name": "url", "type": "string", "description": "Webhook URL", "required": True},
                {"name": "payload", "type": "string", "description": "JSON payload", "required": True},
            ]),
        ],
        model="gpt-4",
    )

    check("Blueprint created", blueprint.name == "Demo Support Agency")
    check("Has teams", len(blueprint.teams) == 1)
    check("Has agents", len(blueprint.all_agents) == 3)
    check("Has tools", len(blueprint.all_tools) == 3)
    check("Has workflows", len(blueprint.workflows) == 1)
    check("Has API endpoints", len(blueprint.api_endpoints) == 2)

    # ─── Step 3: Inject archetypes ────────────────────────
    print("\n🧬 Step 3: Archetype Injection")

    original_agents = len(blueprint.all_agents)
    original_teams = len(blueprint.teams)
    blueprint = inject_archetypes(blueprint)

    check("Archetypes injected", len(blueprint.all_agents) > original_agents,
          f"Before: {original_agents}, After: {len(blueprint.all_agents)}")
    check("New teams added", len(blueprint.teams) > original_teams,
          f"Before: {original_teams}, After: {len(blueprint.teams)}")
    check(f"Total agents: {len(blueprint.all_agents)}", len(blueprint.all_agents) >= 10)
    check(f"Total teams: {len(blueprint.teams)}", len(blueprint.teams) >= 3)

    # Check universal agents are present
    agent_names = [a.name.lower() for a in blueprint.all_agents]
    check("Has QA Reviewer", any("qa" in n for n in agent_names))
    check("Has Strategic Planner", any("planner" in n or "strategic" in n for n in agent_names))
    check("Has Growth Hacker", any("growth" in n for n in agent_names))
    check("Has Revenue Optimizer", any("revenue" in n for n in agent_names))

    # ─── Step 4: Quality evaluation ───────────────────────
    print("\n📊 Step 4: Quality Evaluation (15 dimensions)")

    evaluator = BlueprintEvaluator()
    score = evaluator.evaluate(blueprint)

    check(f"Overall score: {score.overall_score:.0%}", score.overall_score > 0)
    check(f"Dimensions scored: {len(score.dimension_scores)}", len(score.dimension_scores) >= 10)

    for ds in score.dimension_scores:
        icon = "✅" if ds.score >= 0.8 else "⚠️" if ds.score >= 0.5 else "❌"
        print(f"     {icon} {ds.dimension.value}: {ds.score:.0%} (weight: {ds.weight}x)")

    if score.critical_issues:
        print(f"  🚨 Critical issues: {len(score.critical_issues)}")
        for issue in score.critical_issues[:3]:
            print(f"     • {issue}")

    # ─── Step 5: Code generation ──────────────────────────
    print("\n⚙️ Step 5: Code Generation")

    output_dir = Path("./verification_output")
    if output_dir.exists():
        shutil.rmtree(output_dir)

    generator = AgencyGenerator(output_base=output_dir)
    generated_path = generator.generate(blueprint)

    check("Output directory created", generated_path.exists())
    check("main.py generated", (generated_path / "main.py").exists())
    check("api_server.py generated", (generated_path / "api_server.py").exists())
    check("blueprint.json generated", (generated_path / "blueprint.json").exists())
    check("Dockerfile generated", (generated_path / "Dockerfile").exists())
    check("docker-compose.yml generated", (generated_path / "docker-compose.yml").exists())
    check("requirements.txt generated", (generated_path / "requirements.txt").exists())
    check("README.md generated", (generated_path / "README.md").exists())
    check("agents/ directory exists", (generated_path / "agents").is_dir())
    check("tools/ directory exists", (generated_path / "tools").is_dir())

    # Count generated agent/tool files
    agent_files = list((generated_path / "agents").glob("agent_*.py"))
    tool_files = list((generated_path / "tools").glob("tool_*.py"))
    check(f"Agent modules generated: {len(agent_files)}", len(agent_files) >= 3)
    check(f"Tool modules generated: {len(tool_files)}", len(tool_files) >= 1)

    # Check main.py has observability imports
    main_content = (generated_path / "main.py").read_text(encoding="utf-8")
    check("main.py imports EventLog", "EventLog" in main_content)
    check("main.py imports SharedMemory", "SharedMemory" in main_content)
    check("main.py imports BuiltinToolkit", "BuiltinToolkit" in main_content)
    check("main.py imports Planner", "Planner" in main_content)

    # Check requirements don't reference forge-agency pip package
    req_content = (generated_path / "requirements.txt").read_text(encoding="utf-8")
    check("requirements.txt clean (no forge-agency ref)", "forge-agency" not in req_content)

    # Check tool files use built-in integrations where possible
    for tf in tool_files:
        content = tf.read_text(encoding="utf-8")
        tool_name = tf.stem.replace("tool_", "")
        if tool_name in ("http_request", "query_database", "send_webhook"):
            check(f"Tool {tool_name} uses built-in integration", "forge.runtime.integrations" in content)

    # ─── Step 6: Runtime components ───────────────────────
    print("\n🔧 Step 6: Runtime Component Verification")

    # Test EventLog
    event_log = EventLog()
    event_log.emit_llm_call("TestAgent", "gpt-4", 3, 2, trace_id="test-trace")
    event_log.emit_llm_response("TestAgent", "gpt-4", 100, 50, False, 500.0, trace_id="test-trace")
    check("EventLog records events", len(event_log.events) == 2)
    check("CostTracker tracks costs", event_log.cost_tracker.total_cost_usd > 0)
    check("Trace filtering works", len(event_log.get_trace("test-trace")) == 2)

    # Test TraceContext
    trace = TraceContext()
    check("TraceContext generates trace_id", trace.trace_id.startswith("trace-"))
    span = trace.new_span()
    check("TraceContext generates spans", span.startswith("span-"))

    # Test persistent memory
    import tempfile, os
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "test.db")
        mem = SharedMemory.persistent(db_path)
        mem.store("test_key", "test_value", author="verifier", tags=["test"])
        check("Persistent memory stores", mem.recall("test_key") is not None)
        results_list = mem.search_keyword("test")
        check("Persistent memory searches", len(results_list) > 0)
        mem._backend.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # Test built-in tools
    import asyncio
    file_tool = BuiltinToolkit.all_tools(sandbox_dir="./verification_output/data")[0]
    check("BuiltinToolkit returns tools", file_tool is not None)
    check("Tools are Tool instances", hasattr(file_tool, 'name'))

    # Test TaskPlan
    plan = TaskPlan(task="Test task", steps=[
        PlanStep(id="s1", description="Step 1"),
        PlanStep(id="s2", description="Step 2", depends_on=["s1"]),
    ])
    ready = plan.get_ready_steps()
    check("Planner DAG resolves dependencies", len(ready) == 1)
    check("Planner identifies ready steps", ready[0].id == "s1")

    # Test QualityGate
    gate = QualityGate(min_score=0.8)
    check("QualityGate instantiates", gate.min_score == 0.8)

    # ─── Cleanup ──────────────────────────────────────────
    if output_dir.exists():
        shutil.rmtree(output_dir)

    # ─── Summary ──────────────────────────────────────────
    print("\n" + "=" * 60)
    passed = sum(1 for _, ok in results if ok)
    failed = sum(1 for _, ok in results if not ok)
    total = len(results)

    if failed == 0:
        print(f"🎉 ALL {total} CHECKS PASSED")
    else:
        print(f"📊 {passed}/{total} passed, {failed} failed")

    print(f"\n🔨 Forge Verification Complete")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
