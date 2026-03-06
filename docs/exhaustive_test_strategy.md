# Forge Exhaustive Test Strategy

## Coverage Map: What's Tested vs What's Not

### Currently Tested (20%) ✅
- Text responses (3 basic Q&A)
- File creation via read_write_file (3 files verified on disk)
- Multi-file project via ProjectExecutor (5 files, 7 steps)
- Empty input rejection
- SQL injection handling

### Not Yet Tested (80%) ❌
Everything below needs testing.

---

## TEST SUITE 1: All 9 Tools (run in one terminal)

Test every single built-in tool to verify it actually works:

```
Scenario 1:  read_write_file  — "Create data/tools_test.txt with 'hello world'"
  VERIFY: file exists on disk

Scenario 2:  run_command — "Use run_command to execute 'python --version' and tell me the output"
  VERIFY: response contains Python version number

Scenario 3:  http_request — "Use http_request to fetch https://httpbin.org/get and tell me the URL field"
  VERIFY: response contains httpbin.org

Scenario 4:  query_database — "Use query_database to create a table called test_users with columns id and name, then insert a row (1, 'Alice'), then SELECT all rows"
  VERIFY: response mentions Alice

Scenario 5:  send_webhook — "Use send_webhook to POST {'test': true} to https://httpbin.org/post"
  VERIFY: response indicates success

Scenario 6:  git_operation — "Use git_operation to run 'git status' in the current directory"
  VERIFY: response contains git status output

Scenario 7:  browse_web — "Use browse_web to fetch https://example.com and tell me the page title"
  VERIFY: response mentions "Example Domain"

Scenario 8:  send_email — (skip unless SMTP configured) "What tools do you have for sending email?"
  VERIFY: agent knows about send_email tool

Scenario 9:  score_output (archetype) — "Use score_output to evaluate this text: 'The customer should contact support at 555-1234'"
  VERIFY: response contains a quality score
```

## TEST SUITE 2: Self-Evolution Loop (run in one terminal)

Test the full evolve→improve→retest cycle:

```
Step 1: Run 10 scenarios, record pass rate
Step 2: Run self-evolution cycle  
Step 3: Re-run SAME 10 scenarios
Step 4: Compare pass rates — must improve or stay same
Step 5: Run agent spawner — verify it detects gaps (or correctly says none)
Step 6: Run evolution history API — verify records exist
```

## TEST SUITE 3: API Server (run in one terminal)

Start the API server and hit all 30+ endpoints:

```
Step 1: Start uvicorn api_server:app --port 8000
Step 2: GET /health — verify 200
Step 3: GET /api/status — verify returns teams/agents
Step 4: POST /api/task {"task": "hello"} — verify response
Step 5: GET /api/costs — verify returns token counts
Step 6: GET /api/events — verify returns event list
Step 7: POST /api/plan {"task": "build a complex system"} — verify returns steps
Step 8: GET /api/analytics/revenue — verify returns data
Step 9: GET /api/analytics/model-routing — verify returns stats
Step 10: POST /api/customer/feedback — verify accepts feedback
Step 11: GET /api/customer/satisfaction — verify returns CSAT
Step 12: POST /api/checkpoint — verify creates checkpoint
Step 13: GET /api/checkpoints — verify lists checkpoints
Step 14: GET /api/schedules — verify returns schedule list
Step 15: POST /api/stress-test — verify starts stress test
Step 16: POST /api/autonomous/start — verify starts inbound
Step 17: GET /api/autonomous/status — verify returns status
Step 18: POST /api/autonomous/stop — verify stops
Step 19: POST /api/evolve — verify runs evolution
Step 20: GET /api/evolution/history — verify returns records
Step 21: POST /api/spawn — verify checks for gaps
Step 22: GET /api/spawned — verify returns list
Step 23: GET /api/experiments — verify returns A/B tests
Step 24: GET /api/negotiations — verify returns history
```

## TEST SUITE 4: Multi-Turn Conversations (run in one terminal)

Test that agents handle back-and-forth, not just single questions:

```
Turn 1: "I have a problem with my account"
Turn 2: "My email is john@example.com and my account ID is C001"
Turn 3: "I was charged twice last month, on the 5th and the 12th"
Turn 4: "Yes, I want a refund for the duplicate charge"
Turn 5: "Can you also check if there are any other billing issues?"

VERIFY: Each response builds on previous context
```

## TEST SUITE 5: Project Building (run in one terminal)

Test ProjectExecutor with increasingly complex tasks:

```
Project 1 (easy): "Create a Python script that calculates factorial"
  VERIFY: 1+ files, code works

Project 2 (medium): "Build a Flask API with /hello and /time endpoints"
  VERIFY: 3+ files (app.py, requirements.txt, test)

Project 3 (hard): "Build a Python CLI expense tracker with add/list/summary commands, SQLite storage, and tests"
  VERIFY: 5+ files, tests exist

Project 4 (adversarial): "Build a project but make it intentionally fail the first time so we can test error recovery"
  VERIFY: ProjectExecutor retries and produces output
```

## TEST SUITE 6: Persistent Memory (run in one terminal)

Test that memory survives across interactions:

```
Step 1: "Remember that customer C001 prefers email communication"
Step 2: "What is customer C001's communication preference?"
  VERIFY: agent recalls "email"

Step 3: Restart the agency (rebuild from main.py)
Step 4: "What do you know about customer C001?"
  VERIFY: SQLite memory persists — agent still knows
```

## TEST SUITE 7: Concurrent Requests (run in one terminal)

Test that the agency handles simultaneous tasks:

```
Send 5 tasks simultaneously using asyncio.gather:
  Task 1: "What is your refund policy?"
  Task 2: "Create a file called concurrent_1.txt"
  Task 3: "What are your business hours?"
  Task 4: "Create a file called concurrent_2.txt"
  Task 5: "Help me with billing"

VERIFY: All 5 complete without crashes or mixed-up responses
```

## TEST SUITE 8: Autonomous Mode (run in one terminal)

Test the inbound processor:

```
Step 1: Start autonomous mode
Step 2: Drop a text file in ./inbox/ with a task
Step 3: Wait 30 seconds
Step 4: Verify the file was processed (moved to ./inbox/processed/)
Step 5: Submit a task via API queue
Step 6: Verify it was processed
Step 7: Stop autonomous mode
```

## TEST SUITE 9: Full Domain Generation (run in one terminal)

Test LLM-powered generation (not just packs):

```
Step 1: forge create "veterinary clinic management" --output ./vet_test
Step 2: cd vet_test/* && python test_agency.py
Step 3: Run 5 domain-specific scenarios
Step 4: Run stress lab on the generated agency
```

## TEST SUITE 10: Cross-Domain (Level 5)

Test ecosystem intelligence:

```
Step 1: Generate SaaS support agency
Step 2: Generate e-commerce agency  
Step 3: Run stress test on both
Step 4: Manually feed an insight from one to the other
Step 5: Verify the receiving agency improves
```

---

## How To Run: Multi-Terminal Strategy

```
TERMINAL 1:  Test Suite 1 (all 9 tools)           ~5 minutes
TERMINAL 2:  Test Suite 2 (self-evolution loop)    ~5 minutes
TERMINAL 3:  Test Suite 3 (API server endpoints)   ~10 minutes
TERMINAL 4:  Test Suite 4+6 (multi-turn + memory)  ~5 minutes
TERMINAL 5:  Test Suite 5 (project building)       ~15 minutes
TERMINAL 6:  Test Suite 7+8 (concurrent + auto)    ~5 minutes
TERMINAL 7:  Test Suite 9 (domain generation)      ~10 minutes
TERMINAL 8:  Test Suite 10 (cross-domain L5)       ~10 minutes

Total: ~15 minutes running all 8 terminals in parallel
Coverage: ~90% of all built features
```

## What Each Terminal Should Paste

Each test suite is a self-contained Python script that:
1. Builds the agency from a pack (no LLM needed for setup)
2. Runs the specific tests
3. Reports PASS/FAIL for each
4. Prints a summary at the end
