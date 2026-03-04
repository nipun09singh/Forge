# The 5 Features That Make Forge Worth $5K/Month

> **Status: Round 1 features BUILT (see below). Round 2 features identified.**

## Round 1 — COMPLETED ✅

These 5 features were identified and built:
1. ✅ Generated agencies actually run (fixed template, name sanitization, tool matching)
2. ✅ Real archetype tools (15 implementations in `runtime/archetype_tools.py`)
3. ✅ Async-safe human approval (replaced blocking `input()` with `run_in_executor`)
4. ✅ Cost controls (`max_cost_usd`, `max_concurrent_tasks`, config vars)
5. ✅ Post-generation validation (`generators/validator.py`, `forge validate` CLI)

## Round 2 — Current Assessment (Post Round-1 Build)

Fresh audit of all 65 Python files reveals the NEXT 5 highest-impact gaps:

The meta-agency concept is genuinely unique. The blueprint generation, triple critique, universal archetypes, planner, observability — all architecturally sound. But a customer who runs `forge create "dental practice management"` gets a project that **crashes on first run** because:

1. Every custom tool is a stub (`# TODO: Implement`)
2. Universal archetype tools (Growth Hacker, QA Reviewer) are no-ops
3. The generated `main.py` template has broken tool injection logic
4. Human approval blocks the async event loop with `input()`
5. No rate limiting, no connection pooling, no proper error recovery

**The gap: integration, not architecture.**

---

## The 5 Features (in priority order)

### Feature 1: Make Generated Agencies Actually Run
**Impact: This is literally the difference between "demo" and "product"**

The generated `main.py` from `agency_main.py.j2` has broken tool injection. Fix it and verify the full cycle: `forge create --pack saas_support` → `cd generated/saas-support-pro` → `python main.py` → agent handles a real task.

**Files to modify:**
| File | Change |
|------|--------|
| `forge/templates/agency_main.py.j2` | Fix tool injection logic. Remove the broken `_builtin_tools.get(t.name, t)` comprehension. Make tools load cleanly from both built-in integrations and generated stubs. Add `import json` at the top (it's referenced but not imported until the end). |
| `forge/core/engine.py` → `_package_runtime()` | Verify that the copied runtime includes `integrations/` directory AND that generated tool files import correctly. Add a post-generation validation step that tries `importlib.import_module()` on key generated files. |
| `forge/generators/orchestration_gen.py` | Pass team/agent names through a `make_python_identifier()` filter (names with `&`, spaces, etc. break Python). |
| `forge/generators/tool_generator.py` | Fix fuzzy matching — `send_message` should NOT match to email_tool. Make pattern matching stricter (exact prefix match, not substring). |

**Acceptance test:** `forge create --pack saas_support --output ./test && cd test/saas-support-pro && python -c "from main import build_agency; a, e = build_agency(); print(a)"` must succeed.

**Why $5K customers care:** If the product they're paying for doesn't start, they cancel immediately.

---

### Feature 2: Make Archetype Tools Actually Work
**Impact: Turns 9 fake agents into 9 real agents**

Every universal archetype (QA Reviewer, Growth Hacker, Customer Success, etc.) has tools defined but those tools are stubs. The archetype tools need to use the EXISTING runtime infrastructure instead of returning placeholder strings.

**Files to modify:**
| File | Change |
|------|--------|
| `forge/core/archetypes.py` | Rewrite each archetype's tool `implementation_hint` to reference the actual runtime module. BUT MORE IMPORTANTLY: create actual runtime implementations. |
| NEW: `forge/runtime/archetype_tools.py` | Create REAL implementations for the 15+ archetype tools. Each should delegate to existing infrastructure: |

**Concrete tool implementations needed:**

| Archetype Tool | Real Implementation |
|---|---|
| `score_output` (QA Reviewer) | Use the existing `QualityGate._llm_evaluate()` — it already does LLM-based scoring |
| `log_quality_result` (QA Reviewer) | Write to `PerformanceTracker` (already exists) |
| `classify_request` (Intake) | LLM call with structured output — use existing `LLMClient.complete_structured()` |
| `route_to_team` (Intake) | Use existing `Router.route_to_team()` |
| `track_request` (Intake) | Store in `SharedMemory` (already exists) |
| `get_performance_metrics` (Self-Improvement) | Read from `PerformanceTracker.get_agency_stats()` (already exists) |
| `get_failure_log` (Self-Improvement) | Read from `PerformanceTracker.get_failure_patterns()` (already exists) |
| `propose_improvement` (Self-Improvement) | Store in `SharedMemory` with tag "improvement_proposal" |
| `query_metrics` (Analytics) | Read from `PerformanceTracker` + `CostTracker` (both exist) |
| `generate_report` (Analytics) | LLM call to summarize metrics — use `LLMClient.complete()` |
| `analyze_growth_metrics` (Growth) | Read from `PerformanceTracker` + format as growth report |
| `get_customer_health` (Customer Success) | Query `SharedMemory` for customer data |
| `trigger_outreach` (Customer Success) | Use existing `send_email` integration |
| `score_lead` (Lead Gen) | LLM call with structured output |
| `analyze_revenue_metrics` (Revenue) | Read from `CostTracker` + `PerformanceTracker` |

**The key insight:** Most of these tools can be built by WRAPPING EXISTING INFRASTRUCTURE. The runtime already has PerformanceTracker, CostTracker, SharedMemory, QualityGate, Router, LLMClient. The archetype tools just need to call them.

**Why $5K customers care:** They're paying for an agency with 9 built-in agents. If those agents can't do anything, the customer sees through it instantly.

---

### Feature 3: Async-Safe Human Approval (Don't Block the Event Loop)
**Impact: Prevents production crashes**

The current `HumanApprovalGate` uses `input()` in async code. This blocks the entire event loop. With even 2 concurrent tasks, the system deadlocks.

**Files to modify:**
| File | Change |
|------|--------|
| `forge/runtime/human.py` | Replace `input()` with `asyncio.get_event_loop().run_in_executor(None, input, prompt)` for console mode. Better: make the default mode auto-approve with logging, and make console/webhook modes opt-in. |
| `forge/runtime/agent.py` | Add a `max_approval_wait` timeout to the approval check in `_execute_tools`. If approval times out, reject (don't hang forever). |

**Why $5K customers care:** Production systems that hang are worse than systems with bugs. A hanging system looks broken; a system that auto-approves low-risk and rejects timeouts looks smart.

---

### Feature 4: Rate Limiting and Cost Controls
**Impact: Prevents $10,000 surprise bills**

There are ZERO cost controls. An agency with 20 agents, each doing 20 iterations with reflection, can burn through hundreds of dollars in minutes. A $5K/month customer expects cost caps.

**Files to modify:**
| File | Change |
|------|--------|
| `forge/runtime/agent.py` | Add `max_cost_usd` parameter. Before each `_call_llm()`, check `CostTracker`. If over budget, stop and return partial result. |
| `forge/runtime/agency.py` | Add `max_concurrent_tasks` (use `asyncio.Semaphore`). Add `max_cost_per_task` that propagates to all agents. |
| `forge/runtime/observability.py` → `CostTracker` | Add `check_budget(limit)` method that raises `BudgetExceededError` when limit is hit. Add cost alerts at 50%, 80%, 100% of budget. |
| `forge/config.py` | Add `FORGE_MAX_COST_PER_TASK`, `FORGE_MAX_CONCURRENT_TASKS`, `FORGE_COST_ALERT_THRESHOLD` config vars. |
| `forge/templates/agency_main.py.j2` | Wire cost controls from config into agency initialization. |

**Why $5K customers care:** An uncontrolled AI system is a liability. The #1 question enterprises ask is "what's the maximum this can cost?"

---

### Feature 5: Post-Generation Validation (Prove It Works)
**Impact: Confidence that generated agencies are correct**

Currently `forge create` generates files and says "done." It doesn't verify the generated code can import, the tools load, or the agents initialize. Add a validation step.

**Files to modify:**
| File | Change |
|------|--------|
| NEW: `forge/generators/validator.py` | Create `AgencyValidator` that: (1) Checks all generated .py files for syntax errors (`py_compile`) (2) Checks imports resolve (3) Tries to instantiate Agency from generated main.py (4) Verifies all expected files exist (5) Returns a validation report with pass/fail and specific errors. |
| `forge/core/engine.py` | After `_package_runtime()`, call `AgencyValidator.validate(output_path)`. If validation fails, print warnings (don't block generation). |
| `forge/cli.py` | After generation, print validation results. Add `forge validate <path>` command for manual validation. |

**Why $5K customers care:** Confidence. "Forge guaranteed this agency is correct before it shipped" is worth the money. Nobody else does post-generation validation.

---

## The Math: Why These 5 Features = $5K/Month

| Feature | What It Unlocks | Revenue Impact |
|---------|----------------|----------------|
| Agencies that actually run | Customers can USE the product | Prerequisite for any revenue |
| Working archetype tools | 9 agents that DO things, not just talk | "This replaces 3 human employees" |
| Async-safe approvals | Production deployment possible | Enterprise contracts require this |
| Cost controls | CFO approves the purchase | Removes #1 enterprise blocker |
| Post-gen validation | Customer trusts the output | Reduces support tickets 80% |

**Without these 5:** Forge is a $0/month demo.
**With these 5:** Forge generates agencies that start, agents that work, costs that are controlled, and output that's validated. That's worth $5K/month to any business replacing $15K+/month in human salaries.

---

## Build Order

```
Feature 1 (Generated agencies run)     ← Do FIRST. Nothing else matters if this is broken.
    │
    ├── Feature 2 (Archetype tools work)    ← High-leverage: 9 agents become real
    │
    ├── Feature 3 (Async approvals)         ← Quick fix, prevents production crashes
    │
    ├── Feature 4 (Cost controls)           ← Enterprise requirement
    │
    └── Feature 5 (Post-gen validation)     ← Quality seal, reduces support burden
```

Features 2-5 are independent of each other. Build 1 first, then 2-5 in parallel.
