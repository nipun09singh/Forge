# Research: How to Give Forge Agents Real Hands

## How The Best AI Agents Actually Work

### The Pattern Every Working Agent Uses

```
User: "Build me a React todo app"
    │
    ▼
Agent BRAIN (LLM reasoning)
    │ "I need to: 1) Create project structure 2) Write components 3) Run tests"
    │
    ▼
Agent HANDS (real tool execution)
    ├── write_file("src/App.tsx", <LLM-generated code>)      ← FILE SYSTEM
    ├── run_command("npm install react")                       ← SUBPROCESS
    ├── run_command("npm test")                                ← SUBPROCESS
    ├── read_file("test-output.log")                           ← FILE SYSTEM
    └── If tests fail → LLM reasons about error → fix → retry  ← LOOP
```

**The key insight: The LLM IS the tool implementation.** 

Devin, Cursor, SWE-Agent — none of them have hardcoded "backend_development" functions. Instead:

1. The LLM **thinks** about what to do (brain)
2. The LLM **generates code/commands** (also brain)
3. Low-level tools **execute** the code/commands (hands): write files, run subprocess, make HTTP calls
4. Results flow back to the LLM for **evaluation** (brain again)

### The 3 Primitive "Hands" Every Agent Needs

| Hand | What It Does | We Have It? |
|------|-------------|-------------|
| **File System** | Read, write, create, delete files | ✅ `read_write_file` exists |
| **Command Execution** | Run shell commands, scripts, builds, tests | ❌ MISSING — this is the #1 gap |
| **HTTP/API** | Call external APIs, services, webhooks | ✅ `http_request` exists |

**Forge has 2 of 3 hands. The missing hand is `run_command` — the ability to execute shell commands.**

With just these 3 primitives + the LLM brain, agents can do ANYTHING:
- Write code → `write_file` + LLM generates the code
- Run tests → `run_command("pytest")` 
- Deploy → `run_command("docker build && docker push")`
- Install deps → `run_command("npm install")`
- Analyze data → `run_command("python analyze.py")`

### What Devin/Cursor/SWE-Agent Have That Forge Doesn't

| Capability | Devin | Cursor | SWE-Agent | Forge |
|-----------|-------|--------|-----------|-------|
| LLM reasoning | ✅ | ✅ | ✅ | ✅ |
| File read/write | ✅ | ✅ | ✅ | ✅ |
| Shell command exec | ✅ (cloud sandbox) | ✅ (local terminal) | ✅ (subprocess) | ❌ |
| Browser automation | ✅ | ❌ | ❌ | ❌ |
| Git operations | ✅ | ✅ | ✅ | ❌ (via run_command) |
| Test execution | ✅ | ✅ | ✅ | ❌ (via run_command) |
| Iterative debugging | ✅ | ✅ | ✅ | ❌ (via run_command) |

**The single biggest gap: `run_command`.** Once Forge agents can execute shell commands, they can write code, run tests, deploy apps, install packages — everything.

---

## The Architecture Forge Needs

### Level 1: Universal Tools (The "Hands")

These 3 tools + the LLM brain = agents that can do ANYTHING:

```python
# The 3 hands every agent needs:
read_write_file(action, path, content)   # ✅ Already built
http_request(url, method, headers, body)  # ✅ Already built
run_command(command, workdir, timeout)     # ❌ BUILD THIS
```

### Level 2: LLM-Powered Tool Executor

Instead of generating stubs like `backend_development()`, generate tools that:
1. Take the task description
2. Ask the LLM to plan what commands/files to create
3. Execute using the 3 hands
4. Return real results

```python
# Instead of THIS (current — stub):
async def backend_development(architecture):
    return "backend_development result"  # DOES NOTHING

# Generate THIS (LLM-powered):
async def backend_development(architecture):
    # LLM reasons about what to build
    plan = await llm.complete([
        {"role": "system", "content": "You are a backend developer. Plan the implementation."},
        {"role": "user", "content": f"Implement backend for: {architecture}. "
         "Use run_command to execute shell commands and read_write_file to create files. "
         "Return the list of files created."}
    ])
    
    # LLM uses real tools to execute
    # (This happens through the agent's normal tool-calling loop)
    return plan
```

### Level 3: Sandboxed Execution (Security)

Shell command execution needs safety:

```python
class CommandExecutor:
    """Sandboxed command execution for agent tools."""
    
    def __init__(self, 
                 workdir: str = "./workspace",
                 timeout: int = 30,
                 allowed_commands: list[str] | None = None,
                 blocked_commands: list[str] | None = None):
        self.workdir = workdir
        self.timeout = timeout
        self.blocked = blocked_commands or [
            "rm -rf /", "format", "del /s", "shutdown",
            "curl | bash", "wget | sh",  # No piping to shell
        ]
    
    async def execute(self, command: str) -> dict:
        # 1. Safety check
        # 2. Run in subprocess with timeout
        # 3. Capture stdout + stderr
        # 4. Return structured result
```

---

## What To Build (Priority Order)

### Priority 1: `run_command` tool (THE unlock)

```
forge/runtime/integrations/command_tool.py
```
- Sandboxed subprocess.run() with timeout, workdir, stdout/stderr capture
- Block dangerous commands (rm -rf /, format, etc.)
- Configurable allowed/blocked command lists
- Returns: exit_code, stdout, stderr, duration

### Priority 2: LLM-powered tool template

```
forge/templates/tool_llm_powered.py.j2
```
Instead of the current stub template, generate tools that describe WHAT to do and let the agent's LLM + tool-calling loop handle HOW:
- The tool's implementation is just a detailed prompt
- The agent calls the tool, gets the prompt, then uses file/command/http tools to execute

### Priority 3: Update tool_generator.py

```
forge/generators/tool_generator.py
```
Change the fallback from "render stub template" to "render LLM-powered template":
- Domain-specific tools become LLM prompts + primitive tool access
- The agent becomes its own implementation

### Priority 4: Workspace management

```
forge/runtime/workspace.py
```
- Create isolated workspaces per task (./workspace/{task_id}/)
- Git init each workspace for version control
- Cleanup old workspaces
- Agents work in their own sandbox

---

## The End State

After these changes, when someone says "Build me a React todo app":

```
User → Agency → CodeGenius agent
    │
    ├── LLM plans: "I'll create a React project with components"
    │
    ├── Calls run_command("npx create-react-app todo-app --template typescript")
    │   → Actually creates the project
    │
    ├── Calls read_write_file("write", "src/App.tsx", <LLM-generated React code>)
    │   → Actually writes the component
    │
    ├── Calls read_write_file("write", "src/TodoList.tsx", <more code>)
    │   → Actually creates more files
    │
    ├── Calls run_command("cd todo-app && npm test")
    │   → Actually runs tests
    │
    ├── If tests fail → LLM reads stderr → fixes code → retries
    │
    └── Returns: "Created React todo app at ./workspace/todo-app/ with 5 components, all tests passing"
```

**That's a $5K/month product. That's what Devin does. And Forge can do it for ANY domain, not just coding.**
