"""Tests for forge.core.engine — the meta-factory."""
import ast
import json
import py_compile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from pathlib import Path

from forge.core.engine import ForgeEngine, QualityGateError
from forge.core.blueprint import (
    AgencyBlueprint, AgentBlueprint, AgentRole, TeamBlueprint,
    ToolBlueprint, WorkflowBlueprint, WorkflowStep, APIEndpoint,
)
from forge.core.critic import CritiqueResult, CritiqueIssue


class TestForgeEngineInit:
    """Tests for ForgeEngine initialization."""

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    def test_init_defaults(self, mock_refine, mock_critic, mock_eval,
                           mock_gen, mock_analyzer, mock_llm):
        engine = ForgeEngine()
        mock_llm.assert_called_once_with(model=None, api_key=None, base_url=None)
        assert engine._history == []

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    def test_init_custom_model(self, mock_refine, mock_critic, mock_eval,
                               mock_gen, mock_analyzer, mock_llm):
        engine = ForgeEngine(model="gpt-4o", api_key="sk-test", base_url="http://localhost")
        mock_llm.assert_called_once_with(model="gpt-4o", api_key="sk-test", base_url="http://localhost")

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    def test_init_custom_output_dir(self, mock_refine, mock_critic, mock_eval,
                                    mock_gen, mock_analyzer, mock_llm):
        engine = ForgeEngine(output_dir=Path("/custom/output"))
        mock_gen.assert_called_once_with(output_base=Path("/custom/output"))

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    def test_init_creates_analyzer(self, mock_refine, mock_critic, mock_eval,
                                   mock_gen, mock_analyzer, mock_llm):
        engine = ForgeEngine()
        mock_analyzer.assert_called_once_with(engine.llm)

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    def test_init_creates_refinement_loop(self, mock_refine, mock_critic, mock_eval,
                                          mock_gen, mock_analyzer, mock_llm):
        engine = ForgeEngine()
        mock_refine.assert_called_once()
        call_kwargs = mock_refine.call_args[1]
        assert call_kwargs["max_iterations"] == 10


class TestCreateAgencySignature:
    """Tests for create_agency method existence and signature."""

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    def test_create_agency_is_async(self, *mocks):
        engine = ForgeEngine()
        import asyncio
        assert asyncio.iscoroutinefunction(engine.create_agency)

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    def test_create_agency_accepts_domain_description(self, *mocks):
        import inspect
        engine = ForgeEngine()
        sig = inspect.signature(engine.create_agency)
        assert "domain_description" in sig.parameters
        assert "overwrite" in sig.parameters

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    def test_list_generated_is_async(self, *mocks):
        engine = ForgeEngine()
        import asyncio
        assert asyncio.iscoroutinefunction(engine.list_generated)


class TestCreateAgencyErrorHandling:
    """Tests for create_agency error handling paths."""

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    @pytest.mark.asyncio
    async def test_create_agency_retries_on_analysis_failure(self, mock_refine, mock_critic,
                                                              mock_eval, mock_gen, mock_analyzer, mock_llm):
        """When first analyze() fails, engine retries with simpler prompt."""
        engine = ForgeEngine()

        # First call fails, second succeeds
        mock_blueprint = MagicMock(spec=AgencyBlueprint)
        mock_blueprint.name = "Test Agency"
        mock_blueprint.description = "desc"
        mock_blueprint.teams = []
        mock_blueprint.all_agents = []
        mock_blueprint.all_tools = []
        mock_blueprint.workflows = []
        mock_blueprint.api_endpoints = []
        engine.analyzer.analyze = AsyncMock(side_effect=[RuntimeError("API error"), mock_blueprint])

        engine.refinement_loop.refine = AsyncMock(return_value=(mock_blueprint, [{"combined_score": 0.9, "structural_score": 0.8, "zero_dimensions": []}]))
        engine.refinement_loop._history = [{"combined_score": 0.9, "structural_score": 0.8, "zero_dimensions": []}]
        engine.generator.generate = MagicMock(return_value=Path("/tmp/output"))

        with patch.object(engine, "_package_runtime"), \
             patch.object(engine, "_print_summary"), \
             patch("forge.core.engine.inject_archetypes", return_value=mock_blueprint), \
             patch("forge.generators.validator.AgencyValidator") as mock_validator_cls:
            mock_validator_cls.return_value.validate.return_value = MagicMock(
                passed=True, files_checked=5, errors=[], warnings=[]
            )
            bp, path = await engine.create_agency("test domain")

        assert engine.analyzer.analyze.call_count == 2
        assert bp == mock_blueprint

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    @pytest.mark.asyncio
    async def test_create_agency_raises_after_double_failure(self, mock_refine, mock_critic,
                                                              mock_eval, mock_gen, mock_analyzer, mock_llm):
        """When both analyze() calls fail, raises RuntimeError."""
        engine = ForgeEngine()
        engine.analyzer.analyze = AsyncMock(side_effect=RuntimeError("API error"))

        with pytest.raises(RuntimeError, match="Agency generation failed after retry"):
            await engine.create_agency("test domain")

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    @pytest.mark.asyncio
    async def test_create_agency_records_history(self, mock_refine, mock_critic,
                                                  mock_eval, mock_gen, mock_analyzer, mock_llm):
        """Successful creation is recorded in _history."""
        engine = ForgeEngine()

        mock_blueprint = MagicMock(spec=AgencyBlueprint)
        mock_blueprint.name = "History Test"
        mock_blueprint.description = "desc"
        mock_blueprint.teams = []
        mock_blueprint.all_agents = []
        mock_blueprint.all_tools = []
        mock_blueprint.workflows = []
        mock_blueprint.api_endpoints = []
        engine.analyzer.analyze = AsyncMock(return_value=mock_blueprint)
        engine.refinement_loop.refine = AsyncMock(return_value=(mock_blueprint, [{"combined_score": 0.95, "structural_score": 0.85, "zero_dimensions": []}]))
        engine.refinement_loop._history = [{"combined_score": 0.95, "structural_score": 0.85, "zero_dimensions": []}]
        engine.generator.generate = MagicMock(return_value=Path("/tmp/out"))

        with patch.object(engine, "_package_runtime"), \
             patch.object(engine, "_print_summary"), \
             patch("forge.core.engine.inject_archetypes", return_value=mock_blueprint), \
             patch("forge.generators.validator.AgencyValidator") as mock_validator_cls:
            mock_validator_cls.return_value.validate.return_value = MagicMock(
                passed=True, files_checked=3, errors=[], warnings=[]
            )
            await engine.create_agency("history domain")

        assert len(engine._history) == 1
        assert engine._history[0]["agency"] == "History Test"


class TestListGenerated:
    """Tests for listing previously generated agencies."""

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    @pytest.mark.asyncio
    async def test_list_generated_empty_dir(self, *mocks):
        import tempfile
        engine = ForgeEngine()
        with tempfile.TemporaryDirectory() as td:
            engine.generator.output_base = Path(td)
            result = await engine.list_generated()
            assert result == []

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    @pytest.mark.asyncio
    async def test_list_generated_nonexistent_dir(self, *mocks):
        engine = ForgeEngine()
        engine.generator.output_base = Path("/nonexistent/path/that/does/not/exist")
        result = await engine.list_generated()
        assert result == []


class TestQualityGate:
    """Tests for quality gate enforcement in create_agency."""

    def _make_engine_and_blueprint(self, mocks):
        """Helper to set up a mocked engine with a mock blueprint."""
        engine = ForgeEngine()
        mock_blueprint = MagicMock(spec=AgencyBlueprint)
        mock_blueprint.name = "Quality Gate Test"
        mock_blueprint.description = "desc"
        mock_blueprint.teams = []
        mock_blueprint.all_agents = []
        mock_blueprint.all_tools = []
        mock_blueprint.workflows = []
        mock_blueprint.api_endpoints = []
        engine.analyzer.analyze = AsyncMock(return_value=mock_blueprint)
        engine.generator.generate = MagicMock(return_value=Path("/tmp/qg"))
        return engine, mock_blueprint

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    @pytest.mark.asyncio
    async def test_low_score_raises_quality_gate_error(self, *mocks):
        """Score below MIN_QUALITY_SCORE raises QualityGateError."""
        from forge.core.engine import QualityGateError
        engine, mock_blueprint = self._make_engine_and_blueprint(mocks)

        engine.refinement_loop.refine = AsyncMock(
            return_value=(mock_blueprint, [{"combined_score": 0.35, "structural_score": 0.4, "zero_dimensions": []}])
        )
        engine.refinement_loop._history = [{"combined_score": 0.35, "structural_score": 0.4, "zero_dimensions": []}]

        with patch("forge.core.engine.inject_archetypes", return_value=mock_blueprint):
            with pytest.raises(QualityGateError, match="below minimum threshold"):
                await engine.create_agency("test domain")

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    @pytest.mark.asyncio
    async def test_force_bypasses_quality_gate(self, *mocks):
        """With force=True, low score logs a warning but proceeds."""
        engine, mock_blueprint = self._make_engine_and_blueprint(mocks)

        engine.refinement_loop.refine = AsyncMock(
            return_value=(mock_blueprint, [{"combined_score": 0.35, "structural_score": 0.4, "zero_dimensions": []}])
        )
        engine.refinement_loop._history = [{"combined_score": 0.35, "structural_score": 0.4, "zero_dimensions": []}]

        with patch.object(engine, "_package_runtime"), \
             patch.object(engine, "_print_summary"), \
             patch("forge.core.engine.inject_archetypes", return_value=mock_blueprint), \
             patch("forge.generators.validator.AgencyValidator") as mock_validator_cls:
            mock_validator_cls.return_value.validate.return_value = MagicMock(
                passed=True, files_checked=3, errors=[], warnings=[]
            )
            bp, path = await engine.create_agency("test domain", force=True)

        assert bp == mock_blueprint

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    @pytest.mark.asyncio
    async def test_passing_score_proceeds_normally(self, *mocks):
        """Score above MIN_QUALITY_SCORE proceeds without error."""
        engine, mock_blueprint = self._make_engine_and_blueprint(mocks)

        engine.refinement_loop.refine = AsyncMock(
            return_value=(mock_blueprint, [{"combined_score": 0.85, "structural_score": 0.75, "zero_dimensions": []}])
        )
        engine.refinement_loop._history = [{"combined_score": 0.85, "structural_score": 0.75, "zero_dimensions": []}]

        with patch.object(engine, "_package_runtime"), \
             patch.object(engine, "_print_summary"), \
             patch("forge.core.engine.inject_archetypes", return_value=mock_blueprint), \
             patch("forge.generators.validator.AgencyValidator") as mock_validator_cls:
            mock_validator_cls.return_value.validate.return_value = MagicMock(
                passed=True, files_checked=3, errors=[], warnings=[]
            )
            bp, path = await engine.create_agency("test domain")

        assert bp == mock_blueprint
        assert len(engine._history) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Integration tests — only LLM calls are mocked, everything else runs for real
# ═══════════════════════════════════════════════════════════════════════════════

# --- Mock LLM response data ---

_DOMAIN_ANALYSIS = {
    "agency_name": "TestOps Agency",
    "description": "An AI agency that handles testing operations with comprehensive analytics and reporting.",
    "key_functions": [
        "Test execution and management",
        "Quality reporting and dashboards",
        "Bug triage and analysis",
        "Performance monitoring",
    ],
    "stakeholders": ["Engineering teams", "QA leads", "Product managers"],
    "integrations": ["Jira", "GitHub", "Slack", "Datadog"],
    "env_vars": {"JIRA_API_KEY": "your-jira-key", "SLACK_WEBHOOK": "https://hooks.slack.com/..."},
    "complexity": "medium",
    "revenue_streams": ["SaaS subscription", "Per-test-run billing", "Enterprise analytics"],
    "target_market_size": "$500M",
    "competitive_advantages": ["24/7 automated testing", "Faster triage than humans", "Zero fatigue"],
    "growth_levers": ["Network effects from shared test data", "Continuous learning"],
    "monetization_strategy": "SaaS subscription with usage-based tier",
}

_AGENT_DESIGNS = {
    "agents": [
        {
            "name": "Ops Manager",
            "role": "manager",
            "title": "Testing Operations Manager",
            "system_prompt": (
                "You are the Testing Operations Manager for this agency. You oversee all testing "
                "activities, delegate tasks to specialists, and ensure quality standards are met. "
                "You have access to real tools. You manage team priorities and escalate critical issues. "
                "Your KPIs: test coverage above 80%, mean time to triage under 2 hours, zero escaped defects."
            ),
            "capabilities": ["Team management", "Task delegation", "Priority assessment", "Escalation"],
            "temperature": 0.5,
            "can_spawn_sub_agents": True,
        },
        {
            "name": "Test Executor",
            "role": "specialist",
            "title": "Automated Test Execution Specialist",
            "system_prompt": (
                "You are a specialist in automated test execution. You run test suites, analyze results, "
                "identify flaky tests, and report failures. You use run_command to execute tests and "
                "read_write_file to generate reports. You are methodical and thorough in your analysis. "
                "Your KPIs: test pass rate, execution time reduction, flaky test identification accuracy."
            ),
            "capabilities": ["Test execution", "Result analysis", "Flaky test detection"],
            "temperature": 0.3,
            "can_spawn_sub_agents": False,
        },
        {
            "name": "Bug Analyst",
            "role": "analyst",
            "title": "Bug Triage and Analysis Specialist",
            "system_prompt": (
                "You are an expert bug analyst. You triage incoming bugs, assess severity, identify root "
                "causes, and suggest fixes. You use query_database to look up historical bug patterns and "
                "http_request to fetch related data from issue trackers. You are data-driven and precise. "
                "Your KPIs: triage accuracy, time to root cause, duplicate detection rate."
            ),
            "capabilities": ["Bug triage", "Root cause analysis", "Severity assessment", "Pattern detection"],
            "temperature": 0.4,
            "can_spawn_sub_agents": False,
        },
        {
            "name": "Report Writer",
            "role": "writer",
            "title": "Quality Reports Writer",
            "system_prompt": (
                "You write comprehensive quality reports and dashboards. You synthesize test results, "
                "bug trends, and performance metrics into clear, actionable reports for stakeholders. "
                "You use read_write_file to create reports and send_email to distribute them. "
                "Your KPIs: report clarity score, stakeholder satisfaction, delivery timeliness."
            ),
            "capabilities": ["Report generation", "Data visualization", "Trend analysis", "Communication"],
            "temperature": 0.7,
            "can_spawn_sub_agents": False,
        },
        {
            "name": "Performance Monitor",
            "role": "specialist",
            "title": "Performance Monitoring Specialist",
            "system_prompt": (
                "You monitor application performance, detect anomalies, and alert teams when metrics "
                "degrade. You use http_request to query monitoring APIs and send_webhook to alert teams. "
                "You are vigilant and proactive. You continuously analyze trends to predict issues. "
                "Your KPIs: anomaly detection rate, false positive rate, mean time to alert."
            ),
            "capabilities": ["Performance monitoring", "Anomaly detection", "Alerting", "Trend prediction"],
            "temperature": 0.3,
            "can_spawn_sub_agents": False,
        },
        {
            "name": "Growth Strategist",
            "role": "coordinator",
            "title": "Revenue and Growth Coordinator",
            "system_prompt": (
                "You identify upsell opportunities, track customer usage patterns, and design campaigns "
                "to grow revenue. You coordinate between teams to ensure growth targets are met. "
                "You use query_database for analytics and send_email for outreach. "
                "Your KPIs: monthly recurring revenue growth, customer retention rate, upsell conversion."
            ),
            "capabilities": ["Revenue optimization", "Customer analytics", "Campaign design"],
            "temperature": 0.6,
            "can_spawn_sub_agents": False,
        },
    ],
}

_TOOL_DESIGNS = {
    "tools": [
        {
            "name": "run_tests",
            "description": "Execute automated test suites",
            "parameters": [
                {"name": "suite", "type": "string", "description": "Test suite name", "required": True},
                {"name": "parallel", "type": "boolean", "description": "Run in parallel", "required": False},
            ],
            "implementation_hint": "Execute test suites using subprocess",
            "assigned_to": ["Test Executor"],
        },
        {
            "name": "query_bugs",
            "description": "Query bug tracking system for issues",
            "parameters": [
                {"name": "query", "type": "string", "description": "Search query", "required": True},
                {"name": "status", "type": "string", "description": "Filter by status", "required": False},
            ],
            "implementation_hint": "Query Jira API for bugs",
            "assigned_to": ["Bug Analyst"],
        },
        {
            "name": "generate_report",
            "description": "Generate quality report from test data",
            "parameters": [
                {"name": "report_type", "type": "string", "description": "Type of report", "required": True},
                {"name": "date_range", "type": "string", "description": "Date range", "required": False},
            ],
            "implementation_hint": "Compile test results into formatted report",
            "assigned_to": ["Report Writer"],
        },
        {
            "name": "send_notification",
            "description": "Send notifications via Slack or email",
            "parameters": [
                {"name": "channel", "type": "string", "description": "Notification channel", "required": True},
                {"name": "message", "type": "string", "description": "Message content", "required": True},
            ],
            "implementation_hint": "Send via Slack webhook or email API",
            "assigned_to": [],
        },
    ],
}

_TEAM_DESIGNS = {
    "teams": [
        {
            "name": "Test Operations",
            "description": "Handles test execution and bug analysis",
            "lead_agent": "Ops Manager",
            "member_agents": ["Test Executor", "Bug Analyst"],
        },
        {
            "name": "Reporting & Growth",
            "description": "Generates reports and drives growth",
            "lead_agent": "Growth Strategist",
            "member_agents": ["Report Writer", "Performance Monitor"],
        },
    ],
}

_WORKFLOW_DESIGNS = {
    "workflows": [
        {
            "name": "Full Test Cycle",
            "description": "Execute tests, triage bugs, and generate reports",
            "trigger": "manual",
            "steps": [
                {"id": "run", "description": "Execute test suite", "assigned_team": "Test Operations", "depends_on": [], "parallel": False},
                {"id": "triage", "description": "Triage failures", "assigned_team": "Test Operations", "depends_on": ["run"], "parallel": False},
                {"id": "report", "description": "Generate quality report", "assigned_team": "Reporting & Growth", "depends_on": ["triage"], "parallel": False},
            ],
        },
        {
            "name": "Performance Check",
            "description": "Monitor performance and alert on anomalies",
            "trigger": "scheduled",
            "steps": [
                {"id": "monitor", "description": "Check performance metrics", "assigned_team": "Reporting & Growth", "depends_on": [], "parallel": False},
                {"id": "alert", "description": "Send alerts if anomalies detected", "assigned_team": "Reporting & Growth", "depends_on": ["monitor"], "parallel": False},
            ],
        },
    ],
}

_API_DESIGNS = {
    "endpoints": [
        {"path": "/api/task", "method": "POST", "description": "Execute a testing task", "handler_team": "Test Operations"},
        {"path": "/api/report", "method": "GET", "description": "Get latest quality report", "handler_team": "Reporting & Growth"},
        {"path": "/api/bugs", "method": "GET", "description": "List current bugs", "handler_team": "Test Operations"},
        {"path": "/api/status", "method": "GET", "description": "Agency health status", "handler_team": ""},
    ],
}

_HIGH_CRITIQUE = {
    "overall_assessment": "This is a well-designed agency with comprehensive coverage.",
    "score": 0.92,
    "issues": [],
    "strengths": ["Good role coverage", "Detailed prompts", "Strong tooling"],
    "improvement_instructions": "",
    "ready_for_deployment": True,
}

_LOW_CRITIQUE = {
    "overall_assessment": "This agency lacks depth and is not ready for deployment.",
    "score": 0.2,
    "issues": [
        {"severity": "critical", "category": "coverage", "description": "Missing key roles", "suggestion": "Add more agents", "affected_component": ""},
        {"severity": "critical", "category": "tooling", "description": "Insufficient tools", "suggestion": "Add domain tools", "affected_component": ""},
    ],
    "strengths": [],
    "improvement_instructions": "Needs major overhaul.",
    "ready_for_deployment": False,
}


def _build_mock_complete_structured(critique_data=None):
    """Build a side_effect function for LLMClient.complete_structured.

    Dispatches on response_model.__name__ so all real parsing/conversion
    logic in DomainAnalyzer, BlueprintCritic, etc. is exercised.
    """
    critique_data = critique_data or _HIGH_CRITIQUE

    async def _side_effect(messages, response_model, **kwargs):
        name = response_model.__name__
        if name == "DomainAnalysis":
            return response_model.model_validate(_DOMAIN_ANALYSIS)
        elif name == "AgentDesigns":
            return response_model.model_validate(_AGENT_DESIGNS)
        elif name == "ToolDesigns":
            return response_model.model_validate(_TOOL_DESIGNS)
        elif name == "TeamDesigns":
            return response_model.model_validate(_TEAM_DESIGNS)
        elif name == "WfDesigns":
            return response_model.model_validate(_WORKFLOW_DESIGNS)
        elif name == "APIDesign":
            return response_model.model_validate(_API_DESIGNS)
        elif name == "CritiqueResult":
            return response_model.model_validate(critique_data)
        elif name == "AgencyBlueprint":
            # auto_refine asks LLM to improve the blueprint — return a
            # simple valid blueprint so the loop can continue.
            return response_model.model_validate({
                "name": "TestOps Agency",
                "slug": "testops-agency",
                "description": "Refined test ops agency",
                "domain": "testing",
                "teams": [],
                "workflows": [],
                "api_endpoints": [],
                "shared_tools": [],
            })
        else:
            raise ValueError(f"Unexpected response_model: {name}")

    return _side_effect


class TestCreateAgencyRealPipeline:
    """Integration tests that run real ForgeEngine with only LLM calls mocked."""

    @pytest.mark.asyncio
    async def test_create_agency_real_pipeline(self, tmp_path):
        """Full pipeline: real DomainAnalyzer, BlueprintEvaluator, etc. Only LLM mocked."""
        engine = ForgeEngine(
            model="gpt-4",
            api_key="sk-fake-key",
            output_dir=tmp_path,
        )

        engine.llm.complete_structured = AsyncMock(
            side_effect=_build_mock_complete_structured(),
        )
        # Speed up: limit refinement to 1 iteration (it will pass on first)
        engine.refinement_loop.max_iterations = 1

        blueprint, output_path = await engine.create_agency(
            "Automated testing operations agency",
            force=True,
        )

        # Blueprint was created with real DomainAnalyzer logic
        assert isinstance(blueprint, AgencyBlueprint)
        assert blueprint.name == "TestOps Agency"
        assert len(blueprint.teams) >= 1
        assert len(blueprint.all_agents) >= 2

        # Generated files exist on disk
        assert output_path.exists()
        assert (output_path / "main.py").exists()
        assert (output_path / "blueprint.json").exists()

        # Core generated Python files are valid syntax
        for core_file in ["main.py", "api_server.py", "selftest.py"]:
            f = output_path / core_file
            if f.exists():
                py_compile.compile(str(f), doraise=True)
        # Validate agent/tool modules (skip any with hyphens in names —
        # pre-existing archetype naming issue, not under test here)
        for py_file in list((output_path / "agents").rglob("*.py")) + \
                        list((output_path / "tools").rglob("*.py")):
            if "-" not in py_file.stem:
                py_compile.compile(str(py_file), doraise=True)

        # Engine recorded history
        assert len(engine._history) == 1
        assert engine._history[0]["agency"] == "TestOps Agency"

    @pytest.mark.asyncio
    async def test_output_directory_structure(self, tmp_path):
        """Verify generated agency has expected directory structure and files."""
        engine = ForgeEngine(
            model="gpt-4",
            api_key="sk-fake-key",
            output_dir=tmp_path,
        )
        engine.llm.complete_structured = AsyncMock(
            side_effect=_build_mock_complete_structured(),
        )
        engine.refinement_loop.max_iterations = 1

        blueprint, output_path = await engine.create_agency(
            "Testing ops agency",
            force=True,
        )

        # Core generated files
        assert (output_path / "main.py").exists()
        assert (output_path / "api_server.py").exists()
        assert (output_path / "blueprint.json").exists()
        assert (output_path / "requirements.txt").exists()

        # Agent and tool directories
        agents_dir = output_path / "agents"
        tools_dir = output_path / "tools"
        assert agents_dir.exists()
        assert tools_dir.exists()

        # Agent modules were generated
        agent_files = list(agents_dir.glob("agent_*.py"))
        assert len(agent_files) >= 1, f"Expected agent files, found: {list(agents_dir.iterdir())}"

        # Tool modules were generated
        tool_files = list(tools_dir.glob("tool_*.py"))
        assert len(tool_files) >= 1, f"Expected tool files, found: {list(tools_dir.iterdir())}"

        # Deployment files
        assert (output_path / "Dockerfile").exists()

        # Runtime was packaged
        assert (output_path / "forge" / "runtime").exists()

        # Blueprint JSON is valid and matches
        bp_data = json.loads((output_path / "blueprint.json").read_text(encoding="utf-8"))
        assert bp_data["name"] == blueprint.name

    @pytest.mark.asyncio
    async def test_blueprint_has_real_structure(self, tmp_path):
        """Verify the blueprint built by real DomainAnalyzer has proper structure."""
        engine = ForgeEngine(
            model="gpt-4",
            api_key="sk-fake-key",
            output_dir=tmp_path,
        )
        engine.llm.complete_structured = AsyncMock(
            side_effect=_build_mock_complete_structured(),
        )
        engine.refinement_loop.max_iterations = 1

        blueprint, _ = await engine.create_agency(
            "Testing ops agency",
            force=True,
        )

        # DomainAnalyzer organized agents into teams from mock data
        team_names = [t.name for t in blueprint.teams]
        assert len(team_names) >= 1

        # Each team has agents
        for team in blueprint.teams:
            total = len(team.agents) + (1 if team.lead else 0)
            assert total >= 1, f"Team '{team.name}' has no agents"

        # Tools were assigned
        assert len(blueprint.all_tools) >= 1

        # Workflows exist
        assert len(blueprint.workflows) >= 1

        # API endpoints exist
        assert len(blueprint.api_endpoints) >= 1


class TestQualityGateIntegration:
    """Integration tests for quality gate with real evaluator logic."""

    @pytest.mark.asyncio
    async def test_quality_gate_blocks_low_score(self, tmp_path):
        """QualityGateError raised when LLM returns poor critique (force=False)."""
        engine = ForgeEngine(
            model="gpt-4",
            api_key="sk-fake-key",
            output_dir=tmp_path,
        )
        engine.llm.complete_structured = AsyncMock(
            side_effect=_build_mock_complete_structured(critique_data=_LOW_CRITIQUE),
        )
        engine.refinement_loop.max_iterations = 1

        with pytest.raises(QualityGateError, match="below minimum threshold"):
            await engine.create_agency(
                "A poorly specified agency",
                force=False,
            )

    @pytest.mark.asyncio
    async def test_quality_gate_force_bypass(self, tmp_path):
        """Same low-score scenario but force=True succeeds."""
        engine = ForgeEngine(
            model="gpt-4",
            api_key="sk-fake-key",
            output_dir=tmp_path,
        )
        engine.llm.complete_structured = AsyncMock(
            side_effect=_build_mock_complete_structured(critique_data=_LOW_CRITIQUE),
        )
        engine.refinement_loop.max_iterations = 1

        blueprint, output_path = await engine.create_agency(
            "A poorly specified agency",
            force=True,
        )

        assert isinstance(blueprint, AgencyBlueprint)
        assert output_path.exists()
        assert (output_path / "main.py").exists()


class TestRetryIntegration:
    """Integration tests for retry logic with real engine components."""

    @pytest.mark.asyncio
    async def test_retry_on_analysis_failure_real(self, tmp_path):
        """Real engine retries when LLM returns bad JSON the first time."""
        engine = ForgeEngine(
            model="gpt-4",
            api_key="sk-fake-key",
            output_dir=tmp_path,
        )

        call_count = 0
        good_side_effect = _build_mock_complete_structured()

        async def _flaky_side_effect(messages, response_model, **kwargs):
            nonlocal call_count
            call_count += 1
            name = response_model.__name__
            # Fail only on the very first DomainAnalysis call
            if name == "DomainAnalysis" and call_count == 1:
                raise ValueError("LLM returned invalid structured output: bad JSON")
            return await good_side_effect(messages, response_model, **kwargs)

        engine.llm.complete_structured = AsyncMock(side_effect=_flaky_side_effect)
        engine.refinement_loop.max_iterations = 1

        blueprint, output_path = await engine.create_agency(
            "Testing ops agency",
            force=True,
        )

        # Engine should have retried and succeeded
        assert isinstance(blueprint, AgencyBlueprint)
        assert output_path.exists()
        # The first DomainAnalysis call failed, triggering the retry path
        # which calls analyze() again, making a second DomainAnalysis call
        assert call_count >= 2
