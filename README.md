# 🔨 Forge

**The AI Agency Factory — generate complete, deployable AI agent teams from a single sentence.**

```bash
pip install -e .
forge create "customer support agency for a SaaS product"
# → 6 teams, 13 agents, 36 tools, 24 API endpoints, Docker-ready
# → Self-test passes ✅ (1008 tests), API server starts, tools use mock backends by default
# → Wire real backends via tool_backends.json — see "Configuring Real Tool Backends"
```

---

## What Is Forge?

Forge is a **meta-agency** — a system that generates complete AI agencies. Describe what you need in plain English, and Forge:

1. **Analyzes** your domain (6 AI-powered phases)
2. **Designs** agents with specialized roles, tools, and team structure
3. **Critiques** the design against 15 quality dimensions (business + technical)
4. **Iterates** until quality score ≥ 85% (up to 10 refinement rounds)
5. **Generates** a complete, deployable project with 40+ files
6. **Validates** the output (syntax, imports, structure)

Every generated agency includes: FastAPI server (24 endpoints), Docker deployment, tool integrations (mock by default, configurable with real backends), observability, cost tracking, guardrails, and human approval gates.

## Quick Start

```bash
# Install
git clone https://github.com/yourusername/forge.git
cd forge
pip install -e .

# Generate instantly (no API key needed)
forge create --pack saas_support

# Or use AI-powered generation (needs OpenAI key)
export OPENAI_API_KEY=sk-...
forge create "dental practice management agency"

# Verify it works
cd generated/saas-support-pro
python test_agency.py  # → 8/8 PASS ✅

# Run it
python main.py           # Interactive CLI
uvicorn api_server:app   # REST API (24 endpoints)
docker compose up        # Container deployment
```

## What You Get

Every generated agency includes:

| Component | What It Does |
|-----------|-------------|
| **Multi-agent teams** | 10-20 specialized agents organized into functional teams |
| **Real tools** | File I/O, shell commands, HTTP, SQL, email, webhooks — mock backends by default, wire real ones via `ToolExecutor` |
| **Strategic planner** | Decomposes complex tasks into DAGs with parallel execution |
| **Quality gates** | Self-critique loop ensures output quality before delivery |
| **Observability** | Event logging, distributed tracing, per-agent cost tracking |
| **Guardrails** | PII detection, action limits, URL/SQL scope guards |
| **Human approval** | Configurable gates for high-stakes decisions |
| **Revenue tracking** | ROI dashboard showing value generated per agent |
| **API server** | 24 REST endpoints with auth, streaming (SSE), scheduling |
| **Docker deployment** | Dockerfile + docker-compose, production-ready |
| **Self-test** | Automated verification that everything works |

## How It's Different

| Feature | Forge | CrewAI | LangGraph | Devin |
|---------|-------|--------|-----------|-------|
| Generates complete agencies from description | ✅ | ❌ | ❌ | ❌ |
| Composable agent primitives (4 planners, 3 executors, 4 critics) | ✅ | ❌ | ⚠️ | ❌ |
| Domain knowledge injection (policies, rules, vocabulary) | ✅ | ❌ | ❌ | ⚠️ |
| Triple quality critique (structural + technical + business) | ✅ | ❌ | ❌ | ❌ |
| Revenue tracking + ROI dashboard | ✅ | ❌ | ❌ | ❌ |
| Real tool execution (files, commands, HTTP, SQL) | ✅ | ⚠️ | ⚠️ | ✅ |
| Configurable mock → real tool backends | ✅ | ❌ | ❌ | ❌ |
| Pre-built domain packs (instant, no API key) | ✅ | ❌ | ❌ | ❌ |
| 24-endpoint REST API generated automatically | ✅ | ❌ | ❌ | ❌ |

## Architecture

```
forge create "your domain"
    │
    ├─→ Domain Analyzer (6 LLM phases)
    │     → agents, tools, teams, workflows, API design
    │
    ├─→ Archetype Injection (9 universal agents)
    │     → QA Reviewer, Strategic Planner, Growth Hacker, 
    │       Revenue Optimizer, Customer Success, Lead Gen,
    │       Analytics, Intake Coordinator, Self-Improvement
    │
    ├─→ Quality Critique Loop (up to 10 iterations)
    │     → Structural (15 dimensions) + Technical + Business
    │     → Auto-refines until score ≥ 85%
    │
    ├─→ Code Generation (40+ files)
    │     → agents/, tools/, main.py, api_server.py, Docker
    │
    └─→ Validation + Runtime Packaging
          → Syntax check, import check, self-test
```

### Agent Primitive System

Every agent is a composition of primitives, configured per domain:

```
Agent = Planner + Executor + Critic + Escalation + Domain Knowledge

Planners:     Simple | Sequential | DAG | ClassifyAndRoute
Executors:    SingleShot | ReAct (think-act-observe) | MultiStep
Critics:      Binary | Scored | Factual | Compliance
Escalation:   Retry(3) → Different Model(2) → Human(1)
```

## CLI Reference

```bash
forge create "description"        # Generate agency (LLM-powered)
forge create --pack saas_support  # Generate from pre-built pack
forge create --pack ecommerce     # E-commerce agency
forge create --pack real_estate   # Real estate agency
forge packs                       # List available packs
forge inspect generated/my-agency # View agency blueprint
forge validate generated/my-agency # Verify agency code
forge run generated/my-agency     # Start API server
forge doctor                      # Check system health
forge list                        # List generated agencies
```

## API Endpoints (Generated)

Every agency comes with 24 REST endpoints:

```
POST /api/task              Execute a task
POST /api/task/stream       Stream execution (SSE)
POST /api/plan              Plan a complex task
GET  /api/status            Agency status + metrics
GET  /api/events            Observable events
GET  /api/costs             Cost tracking
GET  /api/analytics/revenue Revenue dashboard
GET  /api/analytics/model-routing  Model routing stats
POST /api/customer/feedback Customer satisfaction
POST /api/schedules         Create recurring tasks
POST /api/checkpoint        Save agency state
GET  /health                Health check
... and 12 more
```

## Domain Packs

Generate instantly without an API key:

| Pack | Command | Agents | Teams |
|------|---------|--------|-------|
| SaaS Support | `--pack saas_support` | 13 | 3 |
| E-Commerce | `--pack ecommerce` | 13 | 3 |
| Real Estate | `--pack real_estate` | 12 | 3 |

## Configuration

```bash
# Required for LLM-powered generation (not needed for pre-built packs)
export OPENAI_API_KEY=sk-...          # For LLM-powered generation

# Optional
export FORGE_MODEL=gpt-4              # Default model
export FORGE_SMART_ROUTING=true       # Auto-pick cheapest model per task
export AGENCY_API_KEY=your-secret     # Enable API authentication
export FORGE_BLOCK_PII=true           # Enable PII detection
export FORGE_MAX_COST_PER_TASK=1.0    # Cost limit per task ($)
```

See `.env.example` for a complete template including SMTP, database, and LLM configuration.

## Configuring Real Tool Backends

Generated tools use **mock backends by default** so agencies can self-test and demo without external dependencies. To wire real implementations:

**Option 1: `tool_backends.json` config file**

```json
{
    "process_refund": "myapp.refunds.process_refund",
    "check_inventory": "myapp.inventory.check_stock"
}
```

```python
executor = ToolExecutor()
executor.load_backends_from_config("tool_backends.json")
```

**Option 2: `backend_ref` on ToolBlueprint**

```python
ToolBlueprint(
    name="process_refund",
    description="Process a customer refund",
    parameters=[...],
    backend_ref="myapp.refunds.process_refund",  # dotted import path
    is_async=True,
)
```

**Option 3: Register backends programmatically**

```python
executor = ToolExecutor()
executor.register("process_refund", myapp.refunds.process_refund)
```

See `examples/tool_backends.json` for a working example.

## Current Status

Forge is a **powerful prototype with real engineering** — here's what to know:

| Area | Status |
|------|--------|
| Core generation pipeline | ✅ Fully functional (6-phase analysis, critique loop, code generation) |
| Pre-built domain packs | ✅ Work instantly, no API key needed |
| Security guardrails (PII, scope guards) | ✅ Comprehensive (91 tests) |
| Observability & cost tracking | ✅ Event logging, distributed tracing, cost per agent |
| Streaming (SSE) | ✅ Multi-provider support (OpenAI, Anthropic) |
| Persistence | ✅ SQLite + in-memory backends |
| Agent primitives system | ✅ 4 planners, 3 executors, 4 critics, escalation policies |
| Domain-specific tools | ⚠️ Mock backends by default — configurable via `ToolExecutor` |
| Agent execution on real tasks | ⚠️ Requires `OPENAI_API_KEY` (or compatible LLM API key) |
| Integration tests | ⚠️ Require `OPENAI_API_KEY` environment variable |
| Unit test suite | ✅ 1008 tests pass without API key |

## Project Structure

```
forge/
├── core/                    # Meta-agency engine
│   ├── engine.py            # 5-phase generation pipeline
│   ├── domain_analyzer.py   # AI-powered domain analysis
│   ├── critic.py            # Triple quality critique
│   ├── quality.py           # 15-dimension evaluation
│   └── archetypes.py        # 9 universal agents
├── runtime/                 # Ships with every agency
│   ├── agent.py             # Composable agent (primitives)
│   ├── agency.py            # Multi-team orchestration
│   ├── planner.py           # DAG task decomposition
│   ├── primitives/          # Pluggable planners/executors/critics
│   ├── integrations/        # 7 real tools (file, cmd, http, sql, email, webhook)
│   ├── observability.py     # Event log + cost tracking
│   ├── guardrails.py        # Safety filters
│   └── knowledge.py         # Domain knowledge injection
├── generators/              # Code generation
├── packs/                   # Pre-built domain packs
└── templates/               # Jinja2 code templates
```

## Contributing

1. Fork the repo
2. Create a feature branch
3. Make your changes
4. Run tests: `python -m pytest tests/ -v`
5. Submit a PR

## License

MIT
