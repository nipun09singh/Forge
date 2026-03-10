# 🔨 Forge

**One sentence in. A complete AI agency out.**

```
$ forge create "customer support agency for a SaaS product"

✓ Analyzed domain (6 phases)
✓ Designed 13 agents across 3 teams
✓ Passed quality critique (score: 91/100)
✓ Generated 40+ files
✓ Self-test: 8/8 PASS ✅

→ generated/saas-support-pro/
  Run:  python main.py
  API:  uvicorn api_server:app  (29 endpoints)
  Ship: docker compose up
```

<!-- Badges -->
![Tests](https://img.shields.io/badge/tests-1%2C009_passing-brightgreen)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Why Forge?

You describe a business function. Forge delivers a **running AI operations team** — agents, tools, API, deployment, observability — in seconds.

No boilerplate. No wiring agents together. No prompt engineering.

| | **Forge** | CrewAI | LangGraph | Devin |
|---|---|---|---|---|
| Generates complete agencies from a sentence | ✅ | ❌ | ❌ | ❌ |
| Works instantly without API key (domain packs) | ✅ | ❌ | ❌ | ❌ |
| 29-endpoint REST API, auto-generated | ✅ | ❌ | ❌ | ❌ |
| Composable primitives (4 planners × 3 executors × 4 critics) | ✅ | ❌ | ⚠️ | ❌ |
| Triple quality critique (structural + technical + business) | ✅ | ❌ | ❌ | ❌ |
| Docker-ready deployment | ✅ | ❌ | ❌ | ✅ |
| Built-in security guardrails | ✅ | ❌ | ❌ | ⚠️ |

## Get Started (30 seconds)

```bash
git clone https://github.com/nipun09singh/Forge.git
cd Forge && pip install -e .

# Instant — no API key needed
forge create --pack saas_support
cd generated/saas-support-pro && python main.py

# Or describe anything
export OPENAI_API_KEY=sk-...
forge create "dental practice management agency"
```

## What Gets Generated

Every agency is a **complete, deployable project**:

```
generated/your-agency/
├── main.py                 # Interactive CLI
├── api_server.py           # FastAPI (29 endpoints, auth, SSE streaming)
├── agents/                 # 10-20 specialized agents
├── tools/                  # Domain-specific tools
├── blueprint.json          # Full agency specification
├── test_agency.py          # Self-verification suite
├── Dockerfile              # Container image
├── docker-compose.yml      # One-command deployment
├── requirements.txt        # Pinned dependencies
└── README.md               # Auto-generated docs
```

### The Agent Primitive System

Every agent is a **composition of pluggable primitives**, not a monolith:

```
Agent = Planner + Executor + Critic + Escalation + Domain Knowledge

Planners:     Simple │ Sequential │ DAG │ ClassifyAndRoute
Executors:    SingleShot │ ReAct (think→act→observe) │ MultiStep
Critics:      Binary │ Scored │ Factual │ Compliance
Escalation:   Retry(3) → Different Model(2) → Human(1)
```

The engine picks the right combination per agent role. A triage agent gets `ClassifyAndRoute + SingleShot + Binary`. A research agent gets `DAG + ReAct + Scored`.

## How the Engine Works

```
forge create "your domain"
    │
    ├─ Domain Analysis        6 LLM-powered phases extract agents, tools,
    │                         teams, workflows, and API design
    │
    ├─ Archetype Injection    9 universal agents added (QA, Planning,
    │                         Analytics, Growth, Revenue, Intake...)
    │
    ├─ Quality Critique       Up to 10 iterations across 15 dimensions
    │  Loop                   Auto-refines until score ≥ 85%
    │
    ├─ Code Generation        40+ files with real runtime, not templates
    │
    └─ Validation             Syntax check, import check, self-test
```

## Built-in Security

Not an afterthought — baked into every generated agency:

- **PII Detection** — Credit cards (Luhn-validated), SSN, emails, API keys auto-redacted
- **SSRF Protection** — Blocks private IPs, cloud metadata endpoints, non-HTTP schemes
- **SQL Injection Defense** — Multi-statement blocking, tautology detection, function blacklist
- **Command Whitelist** — Only pre-approved shell commands execute
- **Role-Based Tool Access** — Support agents can't write files, analysts can't run commands
- **Rate Limiting** — Per-tool limits (20 emails/hr, $500/hr Stripe cap)
- **Webhook HMAC Verification** — Cryptographic signature validation on inbound webhooks
- **Human Approval Gates** — Configurable for high-stakes actions

## Real Tools, Not Stubs

9 tools that make real calls out of the box:

| Tool | What It Does |
|---|---|
| `http_request` | Real HTTP calls with SSRF protection |
| `read_write_file` | Sandboxed file I/O with path validation |
| `run_command` | Whitelisted shell execution |
| `query_database` | SQLite with SQL injection defense |
| `send_email` | SMTP integration |
| `send_webhook` | Outbound webhooks with signature support |
| `git_operation` | Full git workflow |
| `browse_web` | Web page fetching and parsing |
| `web_search` | DuckDuckGo search (no API key needed) |

Plus `stripe_payment` and `send_sms` when credentials are configured.

**Domain-specific tools** (like `process_refund`) use mock backends by default so agencies self-test without external dependencies. Wire real implementations in one line:

```python
executor = ToolExecutor()
executor.register("process_refund", myapp.refunds.process_refund)
# Or load from config: executor.load_backends_from_config("tool_backends.json")
```

## Domain Packs

Generate instantly, no API key required:

```bash
forge create --pack saas_support    # 13 agents, 3 teams
forge create --pack ecommerce       # 13 agents, 3 teams
forge create --pack real_estate     # 12 agents, 3 teams
forge packs                         # List all available
```

## CLI

```bash
forge create "description"           # Generate from natural language
forge create --pack <name>           # Generate from domain pack
forge validate generated/my-agency   # Verify agency code
forge run generated/my-agency        # Start API server
forge inspect generated/my-agency    # View blueprint details
forge doctor                         # System health check
forge list                           # List generated agencies
forge packs                          # List domain packs
forge dashboard                      # Web dashboard
```

## API Endpoints

Every generated agency ships with **29 REST endpoints**:

```
Core
  POST /api/task                   Execute a task
  POST /api/task/stream            Stream execution (SSE)
  POST /api/plan                   Plan a complex task
  POST /api/plan/{id}/execute      Execute a plan

Observability
  GET  /api/status                 Agency status + metrics
  GET  /api/events                 Event stream
  GET  /api/costs                  Per-agent cost tracking
  GET  /api/analytics/model-routing  Model selection stats

State
  POST /api/checkpoint             Save agency state
  GET  /api/checkpoints            List checkpoints
  POST /api/restore/{id}           Restore from checkpoint
  POST /api/memory/store           Store to memory
  POST /api/memory/search          Search memory

Automation
  POST /api/schedules              Create recurring task
  GET  /api/schedules              List schedules
  POST /api/autonomous/start       Start autonomous mode
  POST /api/inbound/submit         Submit to task queue
  POST /api/evolve                 Trigger self-improvement

Operations
  POST /api/spawn                  Spawn sub-agents
  POST /api/orchestrate            Multi-agent orchestration
  POST /api/stress-test            Run stress tests
  GET  /health                     Health check
```

## Configuration

```bash
# Required for LLM-powered generation (not needed for domain packs)
export OPENAI_API_KEY=sk-...

# Optional
export FORGE_MODEL=gpt-4o                # Default model
export FORGE_SMART_ROUTING=true          # Auto-pick cheapest model per task
export AGENCY_API_KEY=your-secret        # API authentication
export FORGE_BLOCK_PII=true              # PII detection
export FORGE_MAX_COST_PER_TASK=1.0       # Cost limit per task ($)
```

Copy `.env.example` for the full template.

## Project Structure

```
forge/                          81 modules
├── core/                       Meta-agency engine
│   ├── engine.py               6-phase generation pipeline
│   ├── domain_analyzer.py      LLM-powered domain analysis
│   ├── critic.py               Triple quality critique
│   ├── quality.py              15-dimension evaluation
│   └── archetypes.py           9 universal agents
├── runtime/                    Ships with every generated agency
│   ├── agent.py                Composable agent primitives
│   ├── agency.py               Multi-team orchestration
│   ├── planner.py              DAG task decomposition
│   ├── primitives/             Pluggable planners/executors/critics
│   ├── integrations/           11 tool implementations
│   ├── observability.py        Event logging + cost tracking
│   ├── guardrails.py           PII, SSRF, SQL injection defense
│   ├── self_evolution.py       Autonomous improvement
│   └── knowledge.py            Domain knowledge injection
├── generators/                 Code generation pipeline
├── packs/                      Pre-built domain packs
└── templates/                  Jinja2 code templates

tests/                          1,009 tests (43 files)
```

## Contributing

```bash
git clone https://github.com/nipun09singh/Forge.git
cd Forge && pip install -e .
python -m pytest tests/ -v          # Run unit tests
python -m pytest -m integration     # Run integration tests (needs API key)
```

## License

MIT
