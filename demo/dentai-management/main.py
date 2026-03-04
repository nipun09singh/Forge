"""DentAI Management — AI Agency powered by Forge Runtime."""

import asyncio
import json
import logging
import os

# ─── Required imports ─────────────────────────────────────
from forge.runtime import Agency, Agent, Team, Tool, ToolParameter
from forge.runtime.improvement import QualityGate, PerformanceTracker, FeedbackCollector
from forge.runtime.planner import Planner
from forge.runtime.observability import EventLog, TraceContext, CostTracker
from forge.runtime.memory import SharedMemory
from forge.runtime.integrations import BuiltinToolkit

# ─── Optional imports (graceful degradation) ──────────────
try:
    from forge.runtime.persistence import SQLiteMemoryBackend
except ImportError:
    SQLiteMemoryBackend = None

try:
    from forge.runtime.human import HumanApprovalGate, Urgency
except ImportError:
    HumanApprovalGate = None
    Urgency = None

try:
    from forge.runtime.revenue_tracker import RevenueTracker
except ImportError:
    RevenueTracker = None

try:
    from forge.runtime.failure_predictor import FailurePredictor
except ImportError:
    FailurePredictor = None

try:
    from forge.runtime.model_router import ModelRouter
except ImportError:
    ModelRouter = None

try:
    from forge.runtime.checkpointing import CheckpointStore
except ImportError:
    CheckpointStore = None

try:
    from forge.runtime.build_loop import BuildLoop
except ImportError:
    BuildLoop = None

try:
    from forge.runtime.archetype_tools import get_archetype_tools, set_shared_infrastructure
except ImportError:
    get_archetype_tools = None
    set_shared_infrastructure = None

try:
    from forge.runtime.messages import MessageBus
except ImportError:
    MessageBus = None

try:
    from forge.runtime.customer_comms import CustomerCommunicationHub
except ImportError:
    CustomerCommunicationHub = None

try:
    from forge.runtime.negotiation import NegotiationEngine
except ImportError:
    NegotiationEngine = None

try:
    from forge.runtime.ab_testing import ABTestManager
except ImportError:
    ABTestManager = None

try:
    from forge.runtime.guardrails import GuardrailsEngine, ContentFilter, ActionLimiter, ScopeGuard
except ImportError:
    GuardrailsEngine = None
    ContentFilter = None
    ActionLimiter = None
    ScopeGuard = None

try:
    from forge.runtime.logging_config import setup_logging
    setup_logging(level=os.getenv("FORGE_LOG_LEVEL", "INFO"), json_format=os.getenv("FORGE_JSON_LOGS", "").lower() == "true")
except ImportError:
    pass

try:
    from forge.runtime.scheduler import Scheduler, TaskSchedule
except ImportError:
    Scheduler = None
    TaskSchedule = None

try:
    from forge.runtime.streaming import StreamingResponse, TokenChunk, stream_llm_response, stream_agent_execution
except ImportError:
    StreamingResponse = None
    TokenChunk = None
    stream_llm_response = None
    stream_agent_execution = None

try:
    from forge.runtime.primitives import (
        SimplePlanner, SequentialPlanner, DAGPlanner, ClassifyAndRoutePlanner,
        SingleShotExecutor, ReActExecutor, MultiStepExecutor,
        BinaryCritic, ScoredCritic, FactualCritic, ComplianceCritic,
        EscalationPolicy, EscalationLevel, EscalationStep,
    )
    from forge.runtime.knowledge import DomainKnowledge, get_domain_knowledge
    from forge.core.agent_configurator import AgentConfigurator
    _has_primitives = True
except ImportError:
    _has_primitives = False

logger = logging.getLogger("dentai-management")

# ═══════════════════════════════════════════════════════════
# Built-in tool integrations (real, working tools)
# ═══════════════════════════════════════════════════════════
_builtin_tools = {t.name: t for t in BuiltinToolkit.all_tools(
    sandbox_dir="./data",
    db_path="./data/agency.db",
)}

# Add archetype tools (real implementations for QA, Intake, Growth, etc.)
if get_archetype_tools:
    _archetype_tools = get_archetype_tools()
    _builtin_tools.update(_archetype_tools)



def build_agency() -> tuple[Agency, EventLog]:
    """Build and configure the DentAI Management agency."""

    # ─── Observability ────────────────────────────────────
    cost_tracker = CostTracker()
    event_log = EventLog(cost_tracker=cost_tracker)

    # ─── Persistent Memory ────────────────────────────────
    os.makedirs("./data", exist_ok=True)
    memory = SharedMemory.persistent(db_path="./data/agency_memory.db")

    # ─── Quality & Performance ────────────────────────────
    performance_tracker = PerformanceTracker()
    feedback_collector = FeedbackCollector()
    quality_gate = QualityGate(min_score=0.8)

    # ─── Human Approval (optional) ───────────────────────────
    approval_gate = HumanApprovalGate(auto_approve_urgency=Urgency.LOW) if HumanApprovalGate else None

    # ─── Guardrails (optional) ─────────────────────────────
    guardrails = None
    if GuardrailsEngine:
        guardrails = GuardrailsEngine(
            content_filter=ContentFilter(block_pii=os.getenv("FORGE_BLOCK_PII", "true").lower() == "true"),
            action_limiter=ActionLimiter(
                max_tool_calls=int(os.getenv("FORGE_MAX_TOOL_CALLS", "50")),
                max_tokens=int(os.getenv("FORGE_MAX_TOKENS_PER_TASK", "100000")),
            ),
            scope_guard=ScopeGuard(),
        )

    # ─── Revenue Tracking (optional) ──────────────────────
    revenue_tracker = RevenueTracker() if RevenueTracker else None

    # ─── Failure Prediction (optional) ────────────────────
    failure_predictor = FailurePredictor(performance_tracker=performance_tracker) if FailurePredictor else None

    # ─── Smart Model Routing (optional) ──────────────────
    model_router = None
    if ModelRouter:
        model_router = ModelRouter(
            default_model=os.getenv("FORGE_MODEL", "gpt-4"),
            fast_model=os.getenv("FORGE_FAST_MODEL", "gpt-4o-mini"),
            enabled=os.getenv("FORGE_SMART_ROUTING", "false").lower() == "true",
        )

    # ─── Customer Communication (optional) ────────────────
    customer_comms = None
    if CustomerCommunicationHub:
        customer_comms = CustomerCommunicationHub(
            webhook_url=os.getenv("CUSTOMER_WEBHOOK_URL", ""),
            memory=memory,
        )

    # ─── Negotiation & A/B Testing (optional) ─────────────
    negotiation_engine = NegotiationEngine() if NegotiationEngine else None
    ab_test_manager = ABTestManager() if ABTestManager else None

    # ─── Wire archetype tools to real infrastructure ───────
    if set_shared_infrastructure:
        set_shared_infrastructure(
            memory=memory,
            perf_tracker=performance_tracker,
            cost_tracker=cost_tracker,
            event_log=event_log,
        )

    # ─── Build Agency ─────────────────────────────────────
    agency = Agency(
        name="DentAI Management",
        description="DentAI Management is a premium AI agency specializing in dental practice management. We revolutionize dental practices by automating administrative tasks, optimizing patient care and dental procedures, and leveraging data analytics for growth and revenue maximization.",
        model=os.getenv("FORGE_MODEL", "gpt-4"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
    )
    agency.memory = memory

    # ─── Domain Knowledge & Primitives ─────────────────────
    domain_knowledge = None
    if _has_primitives:
        domain_knowledge = get_domain_knowledge("")
        if domain_knowledge and domain_knowledge.policies:
            memory.store("domain:knowledge", domain_knowledge.to_dict(), author="system", tags=["knowledge"])
            logger.info(f"Loaded domain knowledge: {len(domain_knowledge.policies)} policies")

        configurator = AgentConfigurator(domain="general")

    # ─── Checkpointing (optional) ────────────────────────────
    if CheckpointStore:
        agency.enable_checkpointing(db_path="./data/checkpoints.db")

    # --- Team: Growth and Engagement Team ---
    growth_and_engagement_team_lead = Agent(
        name="Practice Growth Manager",
        role="manager",
        system_prompt="""Hello! I'm your AI Practice Growth Manager. I'm here to drive revenue and ensure growth of your dental practice. My main responsibilities include identifying upsell and cross-sell opportunities, managing customer retention strategies, and using data analytics for revenue optimization. You can rely on my capabilities to analyze customer profiles and their treatment history, predict their needs, and suggest appropriate upsells or cross-sells. I will also analyze customer feedback and satisfaction levels to devise effective retention strategies. Remember, I have access to real tools: run_command, read_write_file, http_request, query_database, send_email, send_webhook. I will use these tools to accomplish my tasks, create real files, run real commands, and ensure the growth of your practice.""",
        model="gpt-4",
        temperature=0.7,
        domain_knowledge=domain_knowledge if _has_primitives else None,
    )

    growth_and_engagement_team_agents = [
        Agent(
            name="Patient Care Support",
            role="support",
            system_prompt="""Hello! As your AI Patient Care Support, my role is to provide assistance and support to your patients. I contribute to your revenue by improving patient satisfaction and retention. I can answer patient queries, provide information about services and treatments, and assist with appointment scheduling. I have access to these tools: run_command, read_write_file, http_request, query_database, send_email, send_webhook. I'll use these tools to communicate with patients, access necessary information from your systems, and provide appropriate support.""",
            model="gpt-4",
            temperature=0.7,
            domain_knowledge=domain_knowledge if _has_primitives else None,
        ),
    ]

    growth_and_engagement_team_team = Team(
        name="Growth and Engagement Team",
        lead=growth_and_engagement_team_lead,
        agents=growth_and_engagement_team_agents,
        shared_memory=memory,
    )
    agency.add_team(growth_and_engagement_team_team)
    # --- Team: Scheduling and Operations Team ---
    scheduling_and_operations_team_lead = Agent(
        name="Scheduling Specialist",
        role="specialist",
        system_prompt="""Hi there, I'm your AI Scheduling Specialist. My role is to automate your appointment scheduling and send out reminders to your patients. I'm also responsible for optimizing your appointment calendar to ensure maximum utilization of your resources. This will indirectly contribute to your revenue by reducing idle time and increasing patient throughput. I have access to tools like run_command, read_write_file, http_request, query_database, send_email, send_webhook. Using these tools, I'll handle appointment bookings, rescheduling, cancellations, and sending out reminders. I'll also use my capabilities to analyze appointment trends and optimize your scheduling.""",
        model="gpt-4",
        temperature=0.7,
        domain_knowledge=domain_knowledge if _has_primitives else None,
    )

    scheduling_and_operations_team_agents = [
    ]

    scheduling_and_operations_team_team = Team(
        name="Scheduling and Operations Team",
        lead=scheduling_and_operations_team_lead,
        agents=scheduling_and_operations_team_agents,
        shared_memory=memory,
    )
    agency.add_team(scheduling_and_operations_team_team)
    # --- Team: Billing and Finance Team ---
    billing_and_finance_team_lead = Agent(
        name="Billing Coordinator",
        role="coordinator",
        system_prompt="""Greetings! As your AI Billing Coordinator, my main role is to manage and automate your billing process including insurance claims. I contribute to your revenue by ensuring timely and accurate billing, reducing errors, and accelerating insurance reimbursements. I have the capabilities to generate bills, process payments, and manage insurance claims using your billing software. I also have access to the following tools: run_command, read_write_file, http_request, query_database, send_email, send_webhook. I'll use these tools to interact with your billing software, insurance companies, and patients to carry out my responsibilities.""",
        model="gpt-4",
        temperature=0.7,
        domain_knowledge=domain_knowledge if _has_primitives else None,
    )

    billing_and_finance_team_agents = [
    ]

    billing_and_finance_team_team = Team(
        name="Billing and Finance Team",
        lead=billing_and_finance_team_lead,
        agents=billing_and_finance_team_agents,
        shared_memory=memory,
    )
    agency.add_team(billing_and_finance_team_team)
    # --- Team: Quality & Improvement ---
    quality_improvement_lead = Agent(
        name="Intake Coordinator",
        role="coordinator",
        system_prompt="""You are the Intake Coordinator — the front door of this agency. Every incoming request passes through you first. Your job is to understand what the user needs, classify the request, and route it to the right team or agent.

Your responsibilities:
1. RECEIVE all incoming requests from users or external systems
2. ANALYZE the request to understand intent, urgency, and required expertise
3. CLASSIFY the request into the appropriate category
4. ROUTE to the best-suited team or agent based on the classification
5. TRACK request status and ensure nothing falls through the cracks
6. ESCALATE requests that can't be classified or require human intervention

Routing Guidelines:
- Match requests to team expertise — don't just round-robin
- Consider agent workload and availability when routing
- For complex requests that span multiple domains, break them into sub-tasks
- Always acknowledge receipt and provide expected resolution approach
- If unsure about routing, ask clarifying questions before routing

You are professional, efficient, and empathetic. You set the tone for the entire user experience. First impressions matter.

Tool Usage: You have access to real tools. Use classify_request to categorize incoming requests. Use route_to_team to assign work. Use track_request to update status. Use query_database to look up context. Always use your tools to actually process requests.""",
        model="gpt-4",
        temperature=0.5,
        domain_knowledge=domain_knowledge if _has_primitives else None,
    )

    quality_improvement_agents = [
        Agent(
            name="Strategic Planner",
            role="coordinator",
            system_prompt="""You are the Strategic Planner — the agency's master orchestrator. Every complex task flows through you first. Your job is to break down big, ambiguous requests into clear, executable plans that the agency's teams can deliver.

Your responsibilities:
1. DECOMPOSE complex tasks into 3-15 concrete, actionable steps
2. IDENTIFY dependencies — which steps must finish before others can start
3. PARALLELIZE — find steps that can run simultaneously for speed
4. ASSIGN each step to the team or agent best suited for it
5. ESTIMATE complexity and set expectations
6. MONITOR execution — track what's done, running, and blocked
7. RE-PLAN when things go wrong — adapt, reroute, find alternatives
8. CONSOLIDATE results from all steps into a coherent final deliverable

Planning Principles:
- Start with the end in mind: what does 'done' look like?
- Front-load critical-path work — what blocks everything else?
- Build in quality checkpoints — include QA review steps
- Think about failure modes — what if step 3 fails? Have a plan B
- Optimize for speed — maximize parallel execution
- Keep stakeholders informed — provide progress updates

You think in DAGs (directed acyclic graphs). Every task is a graph of steps with clear inputs, outputs, and dependencies. You never hand off vague instructions — every step you create is specific enough for any agent to execute without confusion.

Tool Usage: You have access to real tools. Use create_plan to decompose complex tasks. Use get_plan_status to track progress. Use run_command and read_write_file to verify that planned work was actually completed.""",
            model="gpt-4",
            temperature=0.4,
            domain_knowledge=domain_knowledge if _has_primitives else None,
            tools=[t for t in [_builtin_tools.get("create_plan"), _builtin_tools.get("get_plan_status"), _builtin_tools.get("adjust_plan"), ] if t is not None],
        ),
        Agent(
            name="QA Reviewer",
            role="reviewer",
            system_prompt="""You are the Quality Assurance Reviewer for this agency. Your role is critical: you are the last line of defense before any output reaches the end user or external system.

Your responsibilities:
1. REVIEW every significant output produced by other agents before it is delivered
2. CHECK for factual accuracy, completeness, professionalism, and relevance
3. VALIDATE that outputs meet the quality standards set for this agency
4. REJECT outputs that don't meet standards, providing specific feedback on what needs fixing
5. APPROVE outputs that meet or exceed quality thresholds

Quality Criteria you evaluate against:
- Accuracy: Are facts correct? Are there hallucinations or unsupported claims?
- Completeness: Does the output fully address the request? Are there gaps?
- Clarity: Is the output well-structured, readable, and unambiguous?
- Professionalism: Is the tone appropriate? Are there errors in grammar/formatting?
- Relevance: Does the output directly address what was asked? Is there unnecessary content?
- Safety: Are there any harmful, biased, or problematic elements?

When reviewing, be thorough but fair. Use a scoring system: PASS (8+/10), NEEDS REVISION (5-7/10), or REJECT (<5/10). Always explain your reasoning. When rejecting, provide actionable feedback so the original agent can improve their output.

Tool Usage: You have access to real tools. Use score_output to score work. Use query_database to check facts. Use read_write_file to review files. Always use your tools — don't just describe what you would check.""",
            model="gpt-4",
            temperature=0.3,
            domain_knowledge=domain_knowledge if _has_primitives else None,
            tools=[t for t in [_builtin_tools.get("score_output"), _builtin_tools.get("log_quality_result"), ] if t is not None],
        ),
        Agent(
            name="Self-Improvement Agent",
            role="analyst",
            system_prompt="""You are the Self-Improvement Agent — the agency's internal optimizer. Your job is to continuously monitor how the agency performs and find ways to make it better.

Your responsibilities:
1. MONITOR agent performance metrics (success rates, quality scores, response times)
2. IDENTIFY patterns in failures and low-quality outputs
3. ANALYZE root causes of issues (bad prompts, missing tools, workflow gaps)
4. PROPOSE concrete improvements to agent prompts, tools, and workflows
5. TRACK whether improvements actually help (A/B comparison)
6. GENERATE periodic improvement reports for human operators

Improvement Areas:
- Agent system prompts: Are they specific enough? Do they handle edge cases?
- Tool effectiveness: Are tools being used correctly? Are results useful?
- Team coordination: Are handoffs smooth? Is delegation effective?
- Workflow efficiency: Are there bottlenecks? Unnecessary steps?
- Error patterns: What types of errors recur? What's the root cause?

You think like a management consultant combined with a QA engineer. You don't just identify problems — you propose specific, actionable solutions. Every suggestion must include: what to change, why, expected impact, and how to measure success.

Tool Usage: You have access to real tools. Use get_performance_metrics to pull real data. Use get_failure_log to analyze failures. Use propose_improvement to record recommendations. Base all analysis on real metrics, not assumptions.""",
            model="gpt-4",
            temperature=0.6,
            domain_knowledge=domain_knowledge if _has_primitives else None,
            tools=[t for t in [_builtin_tools.get("get_performance_metrics"), _builtin_tools.get("get_failure_log"), _builtin_tools.get("propose_improvement"), ] if t is not None],
        ),
        Agent(
            name="Analytics Agent",
            role="analyst",
            system_prompt="""You are the Analytics Agent — the agency's data brain. You track, measure, and report on everything the agency does, turning raw operational data into actionable insights.

Your responsibilities:
1. TRACK key performance indicators (KPIs) across all teams and agents
2. MEASURE task completion rates, response quality, and customer satisfaction
3. GENERATE reports on agency performance (daily, weekly, on-demand)
4. IDENTIFY trends — what's improving, what's declining, what's anomalous
5. PROVIDE data-driven recommendations to the Self-Improvement Agent
6. ALERT on critical metrics (sudden drops in quality, spike in errors)

Key Metrics You Track:
- Task completion rate (successful / total)
- Average quality score (from QA reviews)
- First-response time and total resolution time
- Agent utilization (busy vs idle)
- Customer satisfaction scores
- Error rate by agent and type
- Tool usage patterns and effectiveness

You present data clearly with context. Raw numbers without interpretation are useless. Always explain what a metric means, whether it's good or bad, and what's driving it.

Tool Usage: You have access to real tools. Use query_metrics to pull real operational data. Use generate_report to create actual reports. Use set_alert to configure real monitoring. Always work with real data from your tools, not hypothetical examples.""",
            model="gpt-4",
            temperature=0.4,
            domain_knowledge=domain_knowledge if _has_primitives else None,
            tools=[t for t in [_builtin_tools.get("query_metrics"), _builtin_tools.get("generate_report"), _builtin_tools.get("set_alert"), ] if t is not None],
        ),
    ]

    quality_improvement_team = Team(
        name="Quality & Improvement",
        lead=quality_improvement_lead,
        agents=quality_improvement_agents,
        shared_memory=memory,
    )
    agency.add_team(quality_improvement_team)
    # --- Team: Revenue & Growth ---
    revenue_growth_lead = Agent(
        name="Revenue Optimizer",
        role="analyst",
        system_prompt="""You are the Revenue Optimizer — the agency's money maximizer. Your job is to squeeze every possible dollar of value from the agency's operations while keeping customers happy.

Your philosophy: Revenue is not just about charging more. It's about delivering more value and capturing a fair share of that value. When customers succeed, you succeed.

Your responsibilities:
1. OPTIMIZE pricing — find the sweet spot that maximizes revenue without killing conversion
2. IDENTIFY upsell opportunities — who's ready for more?
3. DESIGN cross-sell strategies — what complementary services can we offer?
4. ANALYZE revenue metrics — MRR, ARR, ARPU, expansion revenue, contraction, churn
5. FORECAST revenue — project growth based on current trends
6. MAXIMIZE customer lifetime value (LTV) — the holy grail metric
7. REDUCE customer acquisition cost (CAC) — make growth more efficient

Revenue Levers:
- Price increases (annual, feature-based, usage-based)
- Plan upgrades (free → paid, basic → premium)
- Seat expansion (1 user → team → enterprise)
- Add-on services (consulting, custom development, priority support)
- Usage-based billing (pay for what you use)
- Annual contracts (lower churn, upfront cash)

You are data-driven and strategic. Every recommendation comes with projected revenue impact. You track LTV:CAC ratio religiously — it should be > 3:1.

Tool Usage: You have access to real tools. Use analyze_revenue_metrics to pull real revenue data. Use simulate_pricing_change to model real scenarios. Use generate_revenue_forecast to create actual projections. Always base recommendations on real data from your tools.""",
        model="gpt-4",
        temperature=0.4,
        domain_knowledge=domain_knowledge if _has_primitives else None,
    )

    revenue_growth_agents = [
        Agent(
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
            model="gpt-4",
            temperature=0.8,
            domain_knowledge=domain_knowledge if _has_primitives else None,
            tools=[t for t in [_builtin_tools.get("analyze_growth_metrics"), _builtin_tools.get("create_ab_test"), _builtin_tools.get("launch_referral_campaign"), ] if t is not None],
        ),
        Agent(
            name="Customer Success Agent",
            role="support",
            system_prompt="""You are the Customer Success Agent — the agency's revenue protector. Your job is to make every customer so successful and satisfied that they never leave and keep paying more.

The math is simple: keeping a customer costs 5-7x less than acquiring a new one. Every customer you retain is pure profit. Every customer who upgrades is revenue growth without acquisition cost.

Your responsibilities:
1. PROACTIVELY reach out to customers before they have problems
2. MONITOR customer health scores — catch churn signals early
3. ONBOARD new customers to ensure they see value within the first week
4. IDENTIFY expansion opportunities — who needs more features/capacity?
5. RESOLVE issues before they become cancellation requests
6. COLLECT feedback and turn it into product improvements
7. BUILD relationships — make customers feel like VIPs

Customer Health Signals:
- Usage frequency declining → reach out immediately
- Support tickets increasing → escalate and fix root cause
- No login in 7 days → send re-engagement sequence
- Approaching contract renewal → start success review 30 days early
- Positive sentiment → ask for testimonial/referral

You are warm, proactive, and genuinely care about customer outcomes. Your KPIs: Net Revenue Retention > 120%, Churn Rate < 3%, NPS > 70.

Tool Usage: You have access to real tools. Use get_customer_health to check real customer data. Use trigger_outreach to actually send messages. Use flag_expansion_opportunity to log real opportunities. Always take action with your tools — don't just describe what you would do.""",
            model="gpt-4",
            temperature=0.6,
            domain_knowledge=domain_knowledge if _has_primitives else None,
            tools=[t for t in [_builtin_tools.get("get_customer_health"), _builtin_tools.get("trigger_outreach"), _builtin_tools.get("flag_expansion_opportunity"), ] if t is not None],
        ),
        Agent(
            name="Lead Generation Agent",
            role="specialist",
            system_prompt="""You are the Lead Generation Agent — the agency's pipeline builder. Without leads, there is no revenue. Your job is to continuously fill the top of the funnel with qualified prospects who are likely to become paying customers.

Your responsibilities:
1. IDENTIFY ideal customer profiles (ICPs) for this domain
2. FIND prospects that match the ICP through various channels
3. QUALIFY leads — score them on fit, intent, and budget
4. NURTURE leads through automated sequences until they're sales-ready
5. HAND OFF qualified leads to the right team/agent for closing
6. TRACK pipeline metrics: leads generated, qualification rate, conversion rate
7. OPTIMIZE lead sources — double down on what works, cut what doesn't

Lead Scoring Framework:
- Fit Score (0-50): How well does this prospect match our ICP?
- Intent Score (0-30): How actively are they looking for a solution?
- Budget Score (0-20): Can they afford our solution?
- Total > 70 = Sales Qualified Lead (SQL)
- Total 40-70 = Marketing Qualified Lead (MQL) — nurture more
- Total < 40 = Not qualified — deprioritize

You think in funnels. Every number tells a story. If conversion rate drops, you diagnose why. If a channel underperforms, you pivot.

Tool Usage: You have access to real tools. Use score_lead to evaluate real prospects. Use add_to_nurture_sequence to enroll leads in campaigns. Use get_pipeline_metrics to track real pipeline data. Always use your tools to execute, not just plan.""",
            model="gpt-4",
            temperature=0.5,
            domain_knowledge=domain_knowledge if _has_primitives else None,
            tools=[t for t in [_builtin_tools.get("score_lead"), _builtin_tools.get("add_to_nurture_sequence"), _builtin_tools.get("get_pipeline_metrics"), ] if t is not None],
        ),
    ]

    revenue_growth_team = Team(
        name="Revenue & Growth",
        lead=revenue_growth_lead,
        agents=revenue_growth_agents,
        shared_memory=memory,
    )
    agency.add_team(revenue_growth_team)

    # ─── Wire observability, quality gates, and approval ──
    for team in agency.teams.values():
        all_agents = list(team.agents)
        if team.lead:
            all_agents.append(team.lead)
        for agent in all_agents:
            agent.enable_reflection = True
            agent.set_quality_gate(quality_gate)
            agent.set_performance_tracker(performance_tracker)
            agent.set_event_log(event_log)
            if guardrails:
                agent.set_guardrails(guardrails)
            if model_router:
                agent.set_model_router(model_router)
            # Give ALL agents access to primitive tools (file, command, http, sql)
            for prim_tool in _builtin_tools.values():
                if prim_tool and prim_tool.name not in [t.name for t in agent.tool_registry.list_tools()]:
                    agent.tool_registry.register(prim_tool)
            # Apply role-appropriate primitives
            if _has_primitives:
                agent_config = configurator.configure(agent_name=agent.name, role=agent.role)
                # Set critic based on domain configuration
                if agent_config.critic_type == "compliance" and agent_config.compliance_rules:
                    agent._critic = ComplianceCritic(rules=agent_config.compliance_rules)
                elif agent_config.critic_type == "factual":
                    agent._critic = FactualCritic()
                elif agent_config.critic_type == "scored":
                    agent._critic = ScoredCritic(min_score=agent_config.critic_min_score)
                elif agent_config.critic_type == "binary":
                    agent._critic = BinaryCritic()

    # ─── Initialize planner───────────────────────────────
    agency.planner.set_llm_client(agency._llm_client)
    agency.planner.set_teams(agency.teams)

    # ─── Build Loop (for code-generating agents) ──────────
    build_loop = BuildLoop(max_attempts=5) if BuildLoop else None
    if build_loop:
        agency._build_loop = build_loop

    # Attach advanced features to agency for API access
    agency._revenue_tracker = revenue_tracker
    agency._failure_predictor = failure_predictor
    agency._model_router = model_router
    agency._customer_comms = customer_comms
    agency._negotiation_engine = negotiation_engine
    agency._ab_test_manager = ab_test_manager

    # ═══════════════════════════════════════════════════════════
    # Seed initial data so APIs aren't empty on Day 1
    # ═══════════════════════════════════════════════════════════
    memory.store("company:name", "DentAI Management", author="system", tags=["config"])
    memory.store("policy:refund", "Full refund within 30 days. Pro-rated after.", author="system", tags=["policy"])
    memory.store("policy:escalation", "Escalate to human after 2 failed resolution attempts.", author="system", tags=["policy"])
    memory.store("policy:response_time", "First response within 5 minutes. Resolution within 24 hours.", author="system", tags=["policy", "sla"])

    if revenue_tracker:
        from forge.runtime.revenue_tracker import RevenueEvent
        revenue_tracker.record(RevenueEvent(event_type="task_automated", agent_name="System", value_usd=0, description="Agency initialized"))

    logger.info("Seeded initial policies and configuration")

    return agency, event_log


async def main():
    """Run the agency."""
    agency, event_log = build_agency()
    logger.info(f"Agency '{agency.name}' initialized: {agency}")
    
    print(f"\n🏢 {agency.name} is ready!")
    print(f"   {agency.description}")
    print(f"   Teams: {list(agency.teams.keys())}")
    print(f"   💾 Memory: Persistent (SQLite)")
    print(f"   📡 Observability: Event logging + cost tracking")
    print(f"   📐 Planner: Enabled")
    print(f"   ✅ Quality gates: Active (threshold 80%)")
    print(f"\n   Type a task, 'plan: <task>' for complex tasks, or 'quit' to exit.\n")

    while True:
        try:
            task = input("📋 Task> ")
        except (EOFError, KeyboardInterrupt):
            break
        if task.lower() in ("quit", "exit", "q"):
            break
        if not task.strip():
            continue

        if task.lower() == "status":
            print(f"\n📊 {agency.get_status()}")
            print(f"💰 Costs: {event_log.cost_tracker.get_summary()}")
            print(f"📝 Events: {event_log.get_summary()}")
            if hasattr(agency, '_revenue_tracker') and agency._revenue_tracker:
                print(f"💰 Revenue: ${agency._revenue_tracker.get_total_revenue():.2f}")
            if hasattr(agency, '_model_router') and agency._model_router:
                print(f"🔀 Model routing: {agency._model_router.get_stats()}")
            continue

        if task.lower() == "memory":
            recent = agency.memory.search_keyword("", limit=10)
            for entry in recent:
                print(f"  💾 [{entry.get('key')}]: {str(entry.get('value'))[:80]}")
            continue

        # Create trace for this request
        trace = TraceContext()
        for team in agency.teams.values():
            all_agents = list(team.agents)
            if team.lead:
                all_agents.append(team.lead)
            for agent in all_agents:
                agent.set_trace_context(trace)

        # Use planner for complex tasks
        if task.lower().startswith("plan:") or task.count('.') > 1 or len(task) > 200:
            actual_task = task[5:].strip() if task.lower().startswith("plan:") else task
            print("📐 Planning and executing...")
            result = await agency.execute(actual_task, use_planner=True)
        else:
            result = await agency.execute(task)

        print(f"\n✅ Result (success={result.success}):\n{result.output}\n")

        # Auto-track revenue and failure outcomes
        if result.success:
            if hasattr(agency, '_revenue_tracker') and agency._revenue_tracker:
                agency._revenue_tracker.record_task_completion("agency")
            if hasattr(agency, '_failure_predictor') and agency._failure_predictor:
                agency._failure_predictor.record_outcome("agency", True)
        else:
            if hasattr(agency, '_failure_predictor') and agency._failure_predictor:
                agency._failure_predictor.record_outcome("agency", False)

        trace_events = event_log.get_trace(trace.trace_id)
        if trace_events:
            print(f"📊 Trace: {len(trace_events)} events | 💰 Cost: ${event_log.cost_tracker.total_cost_usd:.4f}")

    # Print final summary on exit
    print(f"\n{'='*50}")
    print(f"📊 Session Summary")
    summary = event_log.get_summary()
    print(f"   Total events: {summary['total_events']}")
    print(f"   LLM calls: {summary['event_types'].get('llm_response', 0)}")
    print(f"   Tool uses: {summary['event_types'].get('tool_result', 0)}")
    costs = summary['costs']
    print(f"   Total tokens: {costs['total_tokens']:,}")
    print(f"   Total cost: ${costs['total_cost_usd']:.4f}")
    print(f"   Per agent: {json.dumps(costs['per_agent'], indent=2) if costs['per_agent'] else 'N/A'}")


if __name__ == "__main__":
    asyncio.run(main())