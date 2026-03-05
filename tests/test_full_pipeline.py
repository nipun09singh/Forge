"""Full pipeline integration tests — proves Forge works end-to-end without API key."""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from forge.core.blueprint import AgencyBlueprint
from forge.core.archetypes import inject_archetypes, UNIVERSAL_ARCHETYPES
from forge.core.quality import BlueprintEvaluator, format_quality_report
from forge.generators.agency_generator import AgencyGenerator
from forge.runtime.integrations import BuiltinToolkit
from forge.runtime.planner import Planner, TaskPlan, PlanStep, StepStatus
from forge.runtime.guardrails import ContentFilter, ActionLimiter, ScopeGuard, GuardrailsEngine
from forge.runtime.observability import EventLog, TraceContext, CostTracker
from forge.runtime.checkpointing import CheckpointStore
from forge.runtime.messages import AgentMessage, MessageType, MessageBus
from forge.packs.saas_support import create_saas_support_blueprint
from forge.packs.ecommerce import create_ecommerce_blueprint
from forge.packs.real_estate import create_real_estate_blueprint


class TestFullPipeline:
    """Tests the complete Forge pipeline: pack → archetypes → evaluate → generate → verify."""

    @pytest.fixture
    def output_dir(self):
        d = tempfile.mkdtemp()
        yield Path(d)
        shutil.rmtree(d, ignore_errors=True)

    @pytest.mark.parametrize("pack_fn,expected_slug", [
        (create_saas_support_blueprint, "saas-support-pro"),
        (create_ecommerce_blueprint, "ecommerce-pro"),
        (create_real_estate_blueprint, "realestate-ai"),
    ])
    def test_pack_to_generation(self, pack_fn, expected_slug, output_dir):
        """Complete pipeline for each domain pack."""
        # 1. Create blueprint from pack
        bp = pack_fn()
        assert isinstance(bp, AgencyBlueprint)
        assert bp.slug == expected_slug
        assert len(bp.teams) >= 1
        assert len(bp.all_agents) >= 2

        # 2. Inject archetypes
        enhanced = inject_archetypes(bp)
        assert len(enhanced.all_agents) > len(bp.all_agents)
        assert len(enhanced.teams) > len(bp.teams)

        # 3. Evaluate quality
        evaluator = BlueprintEvaluator()
        score = evaluator.evaluate(enhanced)
        assert score.overall_score > 0
        assert len(score.dimension_scores) >= 10

        # 4. Generate agency
        gen = AgencyGenerator(output_base=output_dir)
        path = gen.generate(enhanced)
        assert path.exists()

        # 5. Verify all expected files
        assert (path / "main.py").exists()
        assert (path / "api_server.py").exists()
        assert (path / "blueprint.json").exists()
        assert (path / "Dockerfile").exists()
        assert (path / "requirements.txt").exists()
        assert (path / "README.md").exists()
        assert (path / "agents").is_dir()
        assert (path / "tools").is_dir()

        # 6. Verify blueprint.json round-trips
        bp_json = json.loads((path / "blueprint.json").read_text())
        assert bp_json["name"] == enhanced.name

        # 7. Verify requirements don't reference forge-agency pip package
        reqs = (path / "requirements.txt").read_text()
        assert "forge-agency" not in reqs

    def test_archetypes_count(self):
        """Verify all 9 universal archetypes exist."""
        assert len(UNIVERSAL_ARCHETYPES) >= 9
        names = [a.name for a in UNIVERSAL_ARCHETYPES]
        assert "QA Reviewer" in names
        assert "Strategic Planner" in names
        assert "Growth Hacker" in names
        assert "Revenue Optimizer" in names


class TestBuiltinToolsDirect:
    """Test built-in tools work directly."""

    @pytest.mark.asyncio
    async def test_file_tool(self):
        from forge.runtime.integrations.file_tool import read_write_file
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["AGENCY_DATA_DIR"] = tmp
            result = json.loads(await read_write_file("write", "test.txt", "hello"))
            assert result["success"]
            result = json.loads(await read_write_file("read", "test.txt"))
            assert result["content"] == "hello"

    @pytest.mark.asyncio
    async def test_sql_tool(self):
        from forge.runtime.integrations.sql_tool import query_database
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "test.db")
            await query_database("CREATE TABLE t (id INTEGER, name TEXT)", db_path=db)
            await query_database("INSERT INTO t VALUES (1, 'Alice')", db_path=db)
            result = json.loads(await query_database("SELECT * FROM t", db_path=db))
            assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_sql_blocks_drop(self):
        from forge.runtime.integrations.sql_tool import query_database
        result = json.loads(await query_database("DROP TABLE users"))
        assert "error" in result

    def test_toolkit_returns_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = BuiltinToolkit.all_tools(sandbox_dir=tmp)
            assert len(tools) >= 3
            names = [t.name for t in tools]
            assert "http_request" in names


class TestPlannerDirect:
    """Test planner without LLM."""

    @pytest.mark.asyncio
    async def test_plan_without_llm(self):
        planner = Planner()
        plan = await planner.plan("Do something complex")
        assert len(plan.steps) == 1  # Fallback single-step

    def test_plan_dag_resolution(self):
        plan = TaskPlan(task="Test", steps=[
            PlanStep(id="a", description="First"),
            PlanStep(id="b", description="Second", depends_on=["a"]),
            PlanStep(id="c", description="Third", depends_on=["a"]),
            PlanStep(id="d", description="Final", depends_on=["b", "c"]),
        ])
        ready = plan.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].id == "a"
        ready[0].status = StepStatus.COMPLETED
        ready2 = plan.get_ready_steps()
        assert len(ready2) == 2  # b and c can run in parallel


class TestGuardrailsDirect:
    """Test guardrails engine directly."""

    def test_pii_detection(self):
        engine = GuardrailsEngine()
        violations = engine.check_output("My SSN is 123-45-6789 and email is test@test.com")
        assert len(violations) >= 2

    def test_tool_blocking(self):
        engine = GuardrailsEngine(
            action_limiter=ActionLimiter(blocked_tools=["rm_rf"]),
            scope_guard=ScopeGuard(),
        )
        violations = engine.check_tool_call("rm_rf", {})
        assert any(v.severity == "block" for v in violations)

    def test_url_scope(self):
        engine = GuardrailsEngine(scope_guard=ScopeGuard())
        violations = engine.check_tool_call("http_request", {"url": "http://localhost:8080"})
        assert len(violations) > 0
        violations2 = engine.check_tool_call("http_request", {"url": "https://api.example.com"})
        assert len(violations2) == 0


class TestCheckpointingDirect:
    """Test checkpointing without agents."""

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(os.path.join(tmp, "cp.db"))
            cp_id = store.save("agent", "test", {"status": "working", "data": "hello"})
            loaded = store.load(cp_id)
            assert loaded is not None
            assert loaded["state"]["status"] == "working"
            store.close()

    def test_load_latest(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(os.path.join(tmp, "cp.db"))
            try:
                store.save("agent", "a1", {"step": 1})
                store.save("agent", "a1", {"step": 2})
                latest = store.load_latest("agent", "a1")
                assert latest is not None
                assert latest["state"]["step"] == 2
            finally:
                store.close()

    def test_list_checkpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(os.path.join(tmp, "cp.db"))
            store.save("agent", "a1", {"v": 1})
            store.save("agent", "a2", {"v": 2})
            cps = store.list_checkpoints()
            assert len(cps) == 2
            store.close()


class TestMessagesDirect:
    """Test typed message system."""

    def test_message_creation(self):
        msg = AgentMessage(sender="A", receiver="B", content="Hello", message_type=MessageType.TASK)
        assert msg.sender == "A"
        assert msg.id.startswith("msg-")

    def test_message_reply(self):
        msg = AgentMessage(sender="A", receiver="B", content="Task", trace_id="t1")
        reply = msg.reply(sender="B", content="Done")
        assert reply.receiver == "A"
        assert reply.trace_id == "t1"
        assert reply.parent_message_id == msg.id

    def test_message_escalate(self):
        msg = AgentMessage(sender="A", content="Problem")
        esc = msg.escalate(sender="A", reason="Can't handle")
        assert esc.message_type == MessageType.ESCALATION

    def test_message_bus(self):
        bus = MessageBus()
        received = []
        bus.subscribe("B", lambda m: received.append(m))
        bus.send(AgentMessage(sender="A", receiver="B", content="Hi"))
        assert len(received) == 1

    def test_bus_history(self):
        bus = MessageBus()
        bus.send(AgentMessage(sender="A", receiver="B", content="1"))
        bus.send(AgentMessage(sender="B", receiver="A", content="2"))
        history = bus.get_conversation("A", "B")
        assert len(history) == 2
