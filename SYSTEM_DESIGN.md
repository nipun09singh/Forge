# Forge System Design

## 1. Vision

Forge is an **AI Agency Meta-Factory** — a system that takes a natural language domain description and generates a **complete, deployable AI agency** composed of unlimited AI agents organized into teams, equipped with custom tools, operating through defined workflows, exposed via REST APIs, and packaged for Docker deployment.

Every generated agency is designed to **maximize revenue** — not just automate tasks. The system pushes for the most ambitious interpretation of any domain.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     USER / CLI                              │
│  forge create "e-commerce support"                          │
│  forge create --file domain.txt                             │
│  forge inspect / forge list / forge run                     │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   FORGE ENGINE                              │
│  (ForgeEngine — the meta-agency orchestrator)               │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │   Domain      │  │  Archetype   │  │   Critique &     │  │
│  │   Analyzer    │  │  Injector    │  │   Refinement     │  │
│  │  (6 phases)   │→ │  (8 agents)  │→ │   Loop           │  │
│  │              │  │              │  │  (up to 10x)     │  │
│  └──────────────┘  └──────────────┘  └──────┬───────────┘  │
│                                              │              │
│  ┌───────────────────────────────────────────▼───────────┐  │
│  │              CODE GENERATORS                          │  │
│  │  AgentGen │ ToolGen │ OrchGen │ DeployGen            │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              GENERATED AGENCY (output)                      │
│                                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │
│  │ Planner  │ │  Teams   │ │  Router  │ │  Quality     │  │
│  │ (DAG     │ │ (agents  │ │ (message │ │  Gates &     │  │
│  │  exec)   │ │  + lead) │ │  routing)│ │  Reflection) │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────────────┘  │
│       │            │            │                           │
│  ┌────▼────────────▼────────────▼──────────────────────┐   │
│  │              SHARED MEMORY                          │   │
│  │        (cross-agent context store)                  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              API SERVER (FastAPI)                    │   │
│  │  POST /api/task │ GET /api/status │ GET /health     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              DOCKER DEPLOYMENT                      │   │
│  │  Dockerfile │ docker-compose.yml                    │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Core Components

### 3.1 CLI (`forge/cli.py`)

| Command | Description |
|---------|-------------|
| `forge create <domain>` | Generate agency from description |
| `forge create --file <path>` | Generate from file |
| `forge list` | List generated agencies |
| `forge inspect <path>` | View agency blueprint details |
| `forge run <path>` | Start agency API server |

### 3.2 ForgeEngine (`forge/core/engine.py`)

The master orchestrator. Executes a **5-phase pipeline**:

```
Phase 1: Domain Analysis ──→ AgencyBlueprint (draft)
Phase 2: Archetype Injection ──→ AgencyBlueprint (with 8 universal agents)
Phase 3: Critique & Refinement ──→ AgencyBlueprint (quality-verified)
Phase 4: Code Generation ──→ Project files on disk
Phase 5: Runtime Packaging ──→ Self-contained deployable project
```

### 3.3 Domain Analyzer (`forge/core/domain_analyzer.py`)

6-phase AI-driven analysis that transforms a text domain into a structured blueprint:

```
Domain Text
    │
    ├─→ Phase 1: _analyze_domain()
    │     Extracts: name, functions, stakeholders, integrations,
    │     revenue streams, market size, growth levers, monetization
    │
    ├─→ Phase 2: _design_agents()
    │     Creates: AgentBlueprints with detailed system prompts,
    │     capabilities, roles (revenue-focused)
    │
    ├─→ Phase 3: _design_tools()
    │     Creates: ToolBlueprints assigned to specific agents or shared
    │     Returns: (agents_with_tools, shared_tools)
    │
    ├─→ Phase 4: _organize_teams()
    │     Groups agents into teams with leads
    │     Catches unassigned agents in "General" team
    │
    ├─→ Phase 5: _design_workflows()
    │     Defines operational workflows with step dependencies
    │
    └─→ Phase 6: _design_api()
          Designs REST API endpoints mapped to teams
```

Each phase uses **structured LLM output** (JSON mode + Pydantic validation).

### 3.4 Blueprint Data Model (`forge/core/blueprint.py`)

```
AgencyBlueprint
├── name, slug, description, domain
├── model (default LLM)
├── teams: list[TeamBlueprint]
│   ├── name, description
│   ├── lead: AgentBlueprint | None
│   ├── agents: list[AgentBlueprint]
│   │   ├── name, role (AgentRole enum), title
│   │   ├── system_prompt (detailed persona)
│   │   ├── capabilities: list[str]
│   │   ├── tools: list[ToolBlueprint]
│   │   │   ├── name, description, parameters
│   │   │   └── implementation_hint
│   │   ├── model, temperature, max_iterations
│   │   └── can_spawn_sub_agents: bool
│   ├── allow_dynamic_scaling: bool
│   └── max_concurrent_tasks: int
├── workflows: list[WorkflowBlueprint]
│   ├── name, description, trigger
│   └── steps: list[WorkflowStep]
│       ├── id, description, assigned_team
│       ├── depends_on: list[str]
│       └── parallel: bool
├── api_endpoints: list[APIEndpoint]
│   ├── path, method, description
│   └── handler_team
├── shared_tools: list[ToolBlueprint]
└── environment_variables: dict
```

---

## 4. Quality Assurance System

### 4.1 Triple Critique Architecture

Every blueprint must pass **three independent critics** before code generation:

```
                    AgencyBlueprint
                         │
           ┌─────────────┼─────────────┐
           ▼             ▼             ▼
    ┌──────────┐  ┌──────────┐  ┌──────────────┐
    │Structural│  │Technical │  │Business      │
    │Evaluator │  │LLM       │  │Ambition      │
    │          │  │Critic    │  │VC Critic     │
    │15 dimens.│  │10 criteria│  │7 criteria    │
    │(25%)     │  │(35%)     │  │(40%)         │
    └────┬─────┘  └────┬─────┘  └──────┬───────┘
         │             │               │
         └──────┬──────┘───────────────┘
                │
         Combined Score
         (must be ≥ 80%)
                │
         ┌──────┴──────┐
         │   PASSED?   │
         │  Yes → Gen  │
         │  No → Refine│──→ LLM auto-fixes blueprint
         └─────────────┘      then loops back (up to 10x)
```

### 4.2 Quality Dimensions (15 total)

**Technical (10):**
role_coverage (1.5x), agent_depth (1.2x), tooling (1.3x), team_architecture (1.0x), workflow_completeness (1.0x), scalability (0.8x), resilience (0.9x), api_design (0.7x), self_improvement (1.1x), universals (1.4x)

**Business Impact (5) — intentionally heavier:**
revenue_potential (1.8x), customer_acquisition (1.6x), competitive_advantage (1.5x), monetization (1.4x), growth_engine (1.7x)

### 4.3 Refinement Loop

```python
for iteration in range(max_iterations):  # default: 10
    structural = evaluator.evaluate(blueprint)       # 25%
    technical = critic.critique(blueprint)            # 35%
    business = business_critic.critique(blueprint)    # 40%

    combined = structural*0.25 + technical*0.35 + business*0.40

    if combined >= 0.80 and no_critical_issues:
        return blueprint  # PASS

    blueprint = auto_refine(blueprint, all_feedback)  # LLM-powered fix
```

---

## 5. Universal Agent Archetypes

Every generated agency receives **8 mandatory agents** in 2 teams:

### Quality & Improvement Team
| Agent | Role | Purpose |
|-------|------|---------|
| QA Reviewer | reviewer | Validates all outputs, scores quality 1-10, rejects bad work |
| Intake Coordinator | coordinator | Front door — classifies, routes, and tracks all requests |
| Self-Improvement Agent | analyst | Monitors performance, identifies failure patterns, proposes fixes |
| Analytics Agent | analyst | Tracks KPIs, generates reports, identifies trends |

### Revenue & Growth Team
| Agent | Role | Purpose |
|-------|------|---------|
| Growth Hacker | specialist | Viral loops, referral programs, A/B testing, conversion optimization |
| Customer Success Agent | support | Retention, churn prevention, NPS, proactive outreach |
| Lead Generation Agent | specialist | Prospect identification, qualification, pipeline nurturing |
| Revenue Optimizer | analyst | Pricing optimization, upselling, cross-selling, LTV maximization |

### Universal Workflows
- **Quality Assurance Review** — produce → QA review → approve/revise loop → deliver
- **Continuous Improvement Cycle** — collect metrics → analyze patterns → propose changes → QA review → apply
- **Revenue Growth Cycle** — generate leads → nurture → monitor health → expansion → optimize → experiments

---

## 6. Runtime Architecture (Generated Agencies)

### 6.1 Agent Execution Model

```
Task arrives
    │
    ▼
Agent.execute(task)
    │
    ├─→ Build conversation: [system_prompt, user_task]
    │
    ├─→ REASONING LOOP (up to max_iterations):
    │     │
    │     ├─→ Call LLM with conversation + tools
    │     │
    │     ├─→ If tool_calls → execute tools → append results → continue
    │     │
    │     └─→ If no tool_calls → agent is done
    │
    ├─→ REFLECTION LOOP (if enable_reflection=True):
    │     │
    │     ├─→ QualityGate.check(output, task)
    │     │
    │     ├─→ If PASSED → return output
    │     │
    │     └─→ If FAILED → re-execute with feedback → loop (up to max_reflections)
    │
    └─→ Record metrics via PerformanceTracker
```

### 6.2 Team Execution Model

```
Team.execute(task)
    │
    ├─→ If team has LEAD agent:
    │     Lead receives task + team roster
    │     Lead gets delegate_to_agent() and delegate_parallel() tools
    │     Lead decides who does what
    │     Lead provides consolidated result
    │
    └─→ If no lead:
          All agents work on task in parallel
          Results combined
```

### 6.3 Strategic Planner

Every agency includes a **Planner** that decomposes complex tasks:

```
Complex Task: "Launch a marketing campaign for our new product"
    │
    ▼
Planner.plan(task)
    │
    ▼
TaskPlan (DAG):
    ┌──────────────────────────────────────────────┐
    │ Step 1: Market Research        [Analyst]      │
    │ Step 2: Competitor Analysis    [Analyst]      │──→ parallel
    │ Step 3: Define Target Audience [Lead Gen]     │
    │ Step 4: Create Messaging       [Writer]       │──→ depends on 1,2,3
    │ Step 5: Design Campaign        [Growth]       │──→ depends on 4
    │ Step 6: Launch & Monitor       [Growth]       │──→ depends on 5
    │ Step 7: Analyze Results        [Analytics]    │──→ depends on 6
    │ Step 8: QA Review              [QA Reviewer]  │──→ depends on 7
    └──────────────────────────────────────────────┘
    │
    ▼
Planner.execute_plan()
    │
    ├─→ Parallel execution of independent steps
    ├─→ Respects dependency ordering
    ├─→ Re-plans on step failure
    └─→ Tracks progress in real-time
```

### 6.4 Message Router

Routes tasks between agents based on:
- **Direct routing** — specific agent by ID
- **Team routing** — best available agent in a team (prefers idle)
- **Broadcast** — all agents work in parallel

### 6.5 Shared Memory

Key-value store with:
- Sync/async operations (thread-safe via asyncio.Lock)
- Author tracking (who wrote what)
- Tag-based search
- History with timestamps
- Context summaries for agent injection

### 6.6 Quality Gates & Self-Improvement

```
Agent Output
    │
    ▼
QualityGate.check(output, task)
    │
    ├─→ LLM evaluation (accuracy, completeness, clarity, usefulness)
    │   Score 0.0-1.0
    │
    ├─→ If score ≥ 0.8 → PASS → deliver
    │
    └─→ If score < 0.8 → REVISE
          │
          └─→ Feed feedback to agent → re-execute → re-check
               (loop up to max_reflections times)
```

Performance tracking feeds into:
- Self-Improvement Agent (identifies patterns)
- Analytics Agent (generates reports)
- Growth Hacker (optimizes conversion)

---

## 7. Code Generation Pipeline

### 7.1 Generators

| Generator | Input | Output |
|-----------|-------|--------|
| AgentGenerator | AgentBlueprint | `agents/agent_{name}.py` |
| ToolGenerator | ToolBlueprint | `tools/tool_{name}.py` |
| OrchestrationGenerator | AgencyBlueprint | `main.py`, `api_server.py` |
| DeploymentGenerator | AgencyBlueprint | Dockerfile, docker-compose, requirements, README |
| AgencyGenerator | AgencyBlueprint | All of the above (master orchestrator) |

### 7.2 Template System (Jinja2)

8 templates in `forge/templates/`:

| Template | Generates |
|----------|-----------|
| `agency_main.py.j2` | Main entry point with agency builder |
| `agent_module.py.j2` | Individual agent with tools |
| `tool_module.py.j2` | Custom tool function |
| `api_server.py.j2` | FastAPI server |
| `dockerfile.j2` | Docker image |
| `docker_compose.yml.j2` | Service orchestration |
| `requirements.txt.j2` | Python dependencies |
| `readme.md.j2` | Project documentation |

### 7.3 Generated Project Structure

```
generated/{slug}/
├── main.py                 # Agency initialization + interactive CLI
├── api_server.py           # FastAPI REST API
├── blueprint.json          # Blueprint snapshot (reference)
├── agents/
│   ├── __init__.py
│   └── agent_*.py          # One file per agent
├── tools/
│   ├── __init__.py
│   └── tool_*.py           # One file per tool
├── forge/
│   └── runtime/            # Bundled runtime framework
│       ├── agent.py
│       ├── agency.py
│       ├── team.py
│       ├── planner.py
│       ├── tools.py
│       ├── memory.py
│       ├── router.py
│       └── improvement.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## 8. Data Flow

### 8.1 Generation Flow (Forge → Generated Agency)

```
User Input (domain text)
    │
    ▼
CLI (Click) ─── parse args ───→ ForgeEngine.create_agency()
    │
    ├─→ DomainAnalyzer.analyze()
    │     6 LLM calls → AgencyBlueprint
    │
    ├─→ inject_archetypes(blueprint)
    │     Add 8 universal agents + 3 workflows
    │
    ├─→ RefinementLoop.refine()
    │     Up to 10 iterations:
    │       BlueprintEvaluator.evaluate()      [structural, 15 dims]
    │       BlueprintCritic.critique()          [semantic, LLM]
    │       BusinessAmbitionCritic.critique()   [business, LLM]
    │       If < 80% → auto_refine() via LLM
    │
    ├─→ AgencyGenerator.generate()
    │     ToolGenerator → agent tools + shared tools
    │     AgentGenerator → agent modules
    │     OrchestrationGenerator → main.py + api_server.py
    │     DeploymentGenerator → Docker + requirements + README
    │
    └─→ _package_runtime()
          Copy forge/runtime/ into generated project
```

### 8.2 Runtime Flow (Generated Agency handling a request)

```
HTTP POST /api/task { "task": "..." }
    │
    ▼
FastAPI handler
    │
    ▼
Agency.execute(task)
    │
    ▼
Planner.plan(task)
    ├─→ LLM decomposes task into sub-task DAG
    ├─→ Assigns each step to best agent/team
    └─→ Returns TaskPlan
    │
    ▼
Planner.execute_plan()
    │
    ├─→ For each ready step (no pending dependencies):
    │     Route to assigned agent/team via Router
    │     Agent.execute(step_task)
    │       ├─→ Reasoning loop (LLM + tools)
    │       ├─→ Reflection loop (quality gate)
    │       └─→ Record metrics
    │     Mark step complete
    │
    ├─→ Parallel execution of independent steps
    │
    ├─→ If step fails → Planner.replan()
    │
    └─→ Consolidate results → return TaskResult
```

---

## 9. Extension Points

| Extension | How |
|-----------|-----|
| Custom LLM provider | Set `OPENAI_BASE_URL` to any OpenAI-compatible API |
| Custom tools | Add ToolBlueprint or use @tool decorator |
| Custom agents | Add AgentBlueprint with role and system prompt |
| Custom archetypes | Add to UNIVERSAL_ARCHETYPES list |
| Custom quality dimensions | Add to QualityDimension enum + evaluator |
| Custom critic | Subclass BlueprintCritic with domain-specific criteria |
| Custom templates | Add .j2 files to forge/templates/ |
| Post-generation hooks | Modify AgencyGenerator.generate() |

---

## 10. Deployment Model

### Generated Agency Deployment

```bash
# Option 1: Direct Python
cd generated/my-agency
pip install -r requirements.txt
export OPENAI_API_KEY="..."
python main.py                      # Interactive CLI
uvicorn api_server:app --port 8000  # REST API

# Option 2: Docker
cd generated/my-agency
docker compose up --build

# Option 3: Forge CLI
forge run generated/my-agency --port 8000
```

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `OPENAI_API_KEY` | LLM authentication | Required |
| `OPENAI_BASE_URL` | Custom API endpoint | OpenAI default |
| `FORGE_MODEL` | LLM model | gpt-4 |

---

## 11. Security Considerations

- **API keys** are passed via environment variables, never hardcoded
- **Generated code** uses async patterns to prevent blocking
- **Quality gates** prevent hallucinated/harmful outputs from reaching users
- **Tool sandboxing** — generated tool stubs require implementation before production use
- **Docker isolation** — generated agencies run in containers

---

## 12. Performance Characteristics

| Operation | Typical Duration | LLM Calls |
|-----------|-----------------|-----------|
| Domain analysis | 30-60s | 6 |
| Archetype injection | <1s | 0 |
| Single critique iteration | 15-30s | 3 (structural + technical + business) |
| Full refinement (3 iterations) | 60-120s | 9 |
| Code generation | 2-5s | 0 |
| Runtime packaging | <1s | 0 |
| **Total agency generation** | **2-5 minutes** | **15-25** |

---

## 13. Design Decisions

| Decision | Rationale |
|----------|-----------|
| Business ambition weighted 40% | Revenue potential matters more than technical elegance |
| 8 universal archetypes | Every business needs QA, intake, analytics, growth, retention, leads, revenue |
| Iterative refinement (up to 10x) | Quality over speed — never deploy a mediocre agency |
| Runtime bundled with generated agency | Generated agencies are self-contained, no external dependencies on Forge |
| Planner as first-class citizen | Complex tasks need decomposition, not just routing |
| Jinja2 templates | Separates code generation logic from output format |
| Pydantic for all models | Validation, serialization, and LLM structured output in one |
| AsyncOpenAI | Non-blocking I/O for concurrent agent execution |
