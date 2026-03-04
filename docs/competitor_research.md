# Competitor Research: CrewAI vs LangGraph vs AutoGen vs Forge

## Comparison Table

### 1. State Serialization & Resume

| Capability | CrewAI | LangGraph | AutoGen | **Forge (Current)** | **Forge (Recommended)** |
|-----------|--------|-----------|---------|---------------------|------------------------|
| State persistence | `@persist` decorator → SQLite | Checkpointer → Postgres/Redis/SQLite/DynamoDB | `save_state()`/`load_state()` | ❌ None — agents forget on restart | ✅ Add `save_state()`/`load_state()` to Agent + Agency |
| Resume from checkpoint | Flow ID-based reload | Thread ID-based, any checkpoint | State dict reload | ❌ No checkpointing | ✅ Add checkpoint after each plan step |
| Time travel / rewind | Manual via checkpoints | ✅ First-class — rewind to any node | Via saved state history | ❌ Missing | 🟡 Phase 2 — add checkpoint history |
| Pluggable backends | SQLite default, custom supported | Postgres, Redis, SQLite, DynamoDB, MongoDB | App-managed (JSON/DB/vector) | SQLite memory only | ✅ Already have SQLiteMemoryBackend — extend to agent state |
| Long-term memory | External (Mem0, Aegis) | Vector stores (Chroma, Pinecone) | TeachableAgent + vector DB | SQLite keyword search only | 🔴 Need vector DB / RAG |

### 2. Agent-to-Agent Communication

| Capability | CrewAI | LangGraph | AutoGen | **Forge (Current)** | **Forge (Recommended)** |
|-----------|--------|-----------|---------|---------------------|------------------------|
| Communication pattern | Hierarchical role delegation | Directed graph / state passing | Conversational turns | Team lead delegation + router | ✅ Already good — add typed messages |
| Message format | Task objects + results | Typed state dicts via edges | Conversational message history | Raw strings | ✅ Add Pydantic message contracts |
| Delegation | Manager → specialist (top-down) | Explicit graph edges (deterministic) | Dynamic negotiation | Lead delegates via tools | ✅ Already have this |
| Parallel execution | Sequential by default | Parallel branches via graph | Sequential turns | ✅ Team parallel + Planner DAG | Already ahead |
| Protocols | Custom Python | Custom Python | Custom Python | Custom Python | 🟡 Phase 3 — add A2A/MCP support |

### 3. Guardrails & Safety

| Capability | CrewAI | LangGraph | AutoGen | **Forge (Current)** | **Forge (Recommended)** |
|-----------|--------|-----------|---------|---------------------|------------------------|
| Output validation | Task guardrails (function or LLM) | Node-level validators | Reviewer agents | ✅ QualityGate + reflection | Already ahead |
| Content filtering | PII/toxicity templates | Custom node logic | Dedicated moderator agents | ✅ ContentFilter (PII, patterns) | Already built |
| Action limiting | Task-level config | Graph structure enforces | Agent-level config | ✅ ActionLimiter (tools, tokens, cost) | Already built |
| Scope control | Role-based | Graph topology | Agent permissions | ✅ ScopeGuard (URLs, SQL tables) | Already built |
| Human-in-the-loop | Human reviewer task | Interrupt nodes | HumanProxyAgent | ✅ HumanApprovalGate + WebhookGate | Already built |
| Retry on failure | Configurable retries | Graph re-entry | Agent retry logic | ✅ Reflection loop (up to 5x) | Already built |

### 4. Streaming Responses

| Capability | CrewAI | LangGraph | AutoGen | **Forge (Current)** | **Forge (Recommended)** |
|-----------|--------|-----------|---------|---------------------|------------------------|
| Token streaming | `stream=True` on kickoff | Multi-mode (values, updates, messages, custom) | Token callbacks | ✅ `streaming.py` + `execute_stream()` | Already built |
| Async streaming | `akickoff()` | `astream()` | Async callbacks | ✅ AsyncIterator | Already built |
| SSE endpoint | Custom implementation | Custom implementation | Custom implementation | ✅ `/api/task/stream` SSE | Already built |
| Subgraph streaming | Crew-level | ✅ Subgraph + node-level | Turn-level | Per-agent only | 🟡 Add team-level streaming |
| Metadata in stream | Agent/task info per chunk | Full state per chunk | Message metadata | Tool call notifications | ✅ Already have tool status in stream |

---

## Gap Analysis: What Forge Needs

### 🔴 CRITICAL — Must Build

**1. Agent State Checkpointing** (`save_state` / `load_state`)
- Every competitor has this. Forge agents lose all state on restart.
- **Build:** Add `save_state() → dict` and `load_state(dict)` to Agent class.
- Serialize: conversation history, status, tool results, memory snapshot.
- Store via the existing SQLiteMemoryBackend.
- Add `checkpoint()` method to Planner that saves plan state after each step.

**2. Typed Agent Messages (Pydantic contracts)**
- Currently agents pass raw strings between each other.
- **Build:** Define `AgentMessage(BaseModel)` with: sender, receiver, content, message_type, structured_data, trace_id.
- Use in Router and Team delegation.

### 🟡 IMPORTANT — Build in Phase 2

**3. Vector Memory / RAG**
- Competitors integrate with Chroma/Pinecone for semantic search.
- Forge has keyword search only.
- **Build:** Add optional vector backend using `sqlite-vss` or simple TF-IDF.

**4. Team-Level Streaming**
- Currently only individual agents stream.
- **Build:** Team.execute_stream() that streams results from all agents.

**5. A2A / MCP Protocol Support**
- Emerging standard for agent interoperability.
- **Build:** Protocol adapter layer in Phase 3.

### ✅ ALREADY AHEAD OF COMPETITORS

Forge already has features most competitors DON'T:
- **Meta-agency generation** — nobody else generates entire agencies from descriptions
- **Triple critique loop** — no competitor has 3-layer quality review
- **Business ambition scoring** — unique to Forge
- **Universal revenue archetypes** — Growth Hacker, Revenue Optimizer etc.
- **Built-in real tool integrations** — HTTP, Email, SQL, File, Webhook
- **Strategic Planner with DAG execution** — better than CrewAI's sequential default
- **Guardrails engine** — more comprehensive than any competitor's built-in safety

---

## Recommendations for Forge

### Priority 1: Build state checkpointing (biggest gap)
```python
# Target API:
state = await agent.save_state()  # → serializable dict
await agent.load_state(state)     # restore from checkpoint
agency.checkpoint("my-checkpoint")  # save entire agency state
agency.restore("my-checkpoint")     # resume from checkpoint
```

### Priority 2: Typed messages between agents
```python
class AgentMessage(BaseModel):
    id: str
    sender: str
    receiver: str
    content: str
    message_type: str  # "task", "result", "delegation", "feedback"
    data: dict = {}
    trace_id: str = ""
```

### Priority 3: Don't copy competitors — leverage your uniqueness
Forge's moat is the META-AGENCY concept. Don't become another CrewAI clone.
Instead, make generated agencies so good that they rival hand-built CrewAI/LangGraph setups.
