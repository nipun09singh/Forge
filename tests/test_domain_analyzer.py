"""Behavioral tests for DomainAnalyzer — the core 6-phase blueprint design engine."""

import asyncio
import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forge.core.domain_analyzer import DomainAnalyzer
from forge.core.llm import LLMClient
from forge.core.blueprint import (
    AgencyBlueprint,
    AgentBlueprint,
    AgentRole,
    APIEndpoint,
    TeamBlueprint,
    ToolBlueprint,
    WorkflowBlueprint,
    WorkflowStep,
)


# ---------------------------------------------------------------------------
# Helpers — build mock Pydantic model instances that complete_structured returns
# ---------------------------------------------------------------------------

def _make_mock_llm() -> LLMClient:
    """Create an LLMClient with a mocked AsyncOpenAI so no network calls happen."""
    with patch("forge.core.llm.AsyncOpenAI"):
        llm = LLMClient(api_key="sk-fake-key")
    llm.complete_structured = AsyncMock()
    return llm


def _ns(**kwargs):
    """Shorthand for SimpleNamespace."""
    return SimpleNamespace(**kwargs)


def _domain_analysis_result(**overrides):
    """Return an object that behaves like a DomainAnalysis pydantic model."""
    defaults = {
        "agency_name": "HealthPilot AI",
        "description": "AI-driven hospital management agency",
        "key_functions": ["patient_intake", "appointment_scheduling", "billing"],
        "stakeholders": ["hospital admins", "doctors", "patients"],
        "integrations": ["EHR system", "billing platform"],
        "env_vars": {"EHR_API_KEY": "", "BILLING_API_KEY": ""},
        "complexity": "high",
        "revenue_streams": ["SaaS subscription", "per-transaction billing"],
        "target_market_size": "$50B",
        "competitive_advantages": ["24/7 availability"],
        "growth_levers": ["network effects"],
        "monetization_strategy": "SaaS",
    }
    defaults.update(overrides)
    obj = _ns(**defaults)
    obj.model_dump = lambda: defaults
    return obj


def _agent_designs_result(agents=None):
    """Return an object matching the AgentDesigns schema."""
    if agents is None:
        agents = [
            _ns(name="HospitalManager", role="manager",
                title="Hospital Operations Manager",
                system_prompt="You manage hospital ops.",
                capabilities=["scheduling", "staff_coordination"],
                temperature=0.5, can_spawn_sub_agents=True),
            _ns(name="PatientCareSpecialist", role="specialist",
                title="Patient Care Specialist",
                system_prompt="You handle patient interactions.",
                capabilities=["intake", "triage", "follow-up"],
                temperature=0.7, can_spawn_sub_agents=False),
            _ns(name="BillingAnalyst", role="analyst",
                title="Medical Billing Analyst",
                system_prompt="You handle billing.",
                capabilities=["invoicing", "insurance_claims"],
                temperature=0.3, can_spawn_sub_agents=False),
        ]
    return _ns(agents=agents)


def _tool_designs_result(tools=None):
    """Return an object matching the ToolDesigns schema."""
    if tools is None:
        tools = [
            _ns(name="lookup_patient", description="Look up patient records",
                parameters=[{"name": "patient_id", "type": "string", "description": "ID", "required": True}],
                implementation_hint="Query EHR",
                assigned_to=["PatientCareSpecialist"]),
            _ns(name="submit_claim", description="Submit insurance claim",
                parameters=[], implementation_hint="Call billing API",
                assigned_to=["BillingAnalyst"]),
            _ns(name="send_notification", description="Send notification to staff",
                parameters=[], implementation_hint="Push notification",
                assigned_to=[]),
        ]
    return _ns(tools=tools)


def _team_designs_result(teams=None):
    """Return an object matching the TeamDesigns schema."""
    if teams is None:
        teams = [
            _ns(name="Clinical Team", description="Handles patient-facing operations",
                lead_agent="HospitalManager", member_agents=["PatientCareSpecialist"]),
            _ns(name="Finance Team", description="Billing and revenue",
                lead_agent="BillingAnalyst", member_agents=[]),
        ]
    return _ns(teams=teams)


def _workflow_designs_result(workflows=None):
    """Return an object matching the WfDesigns schema."""
    if workflows is None:
        workflows = [
            _ns(name="Patient Intake", description="Register and triage new patients",
                trigger="api_call", steps=[
                    _ns(id="s1", description="Collect info", assigned_team="Clinical Team", depends_on=[], parallel=False),
                    _ns(id="s2", description="Insurance verify", assigned_team="Finance Team", depends_on=["s1"], parallel=False),
                ]),
        ]
    return _ns(workflows=workflows)


def _api_designs_result(endpoints=None):
    """Return an object matching the APIDesign schema."""
    if endpoints is None:
        endpoints = [
            _ns(path="/api/task", method="POST", description="General task", handler_team="Clinical Team"),
            _ns(path="/api/patients", method="GET", description="List patients", handler_team="Clinical Team"),
            _ns(path="/api/billing", method="POST", description="Submit bill", handler_team="Finance Team"),
        ]
    return _ns(endpoints=endpoints)


def _wire_all_phases(llm, domain_result=None, agents_result=None,
                     tools_result=None, teams_result=None,
                     workflows_result=None, api_result=None):
    """Wire complete_structured to return phase-appropriate mocks in call order."""
    llm.complete_structured = AsyncMock(side_effect=[
        domain_result or _domain_analysis_result(),
        agents_result or _agent_designs_result(),
        tools_result or _tool_designs_result(),
        teams_result or _team_designs_result(),
        workflows_result or _workflow_designs_result(),
        api_result or _api_designs_result(),
    ])


# ---------------------------------------------------------------------------
# Phase 1 — Domain Analysis
# ---------------------------------------------------------------------------

class TestPhase1DomainAnalysis:
    """Test the _analyze_domain phase in isolation."""

    @pytest.mark.asyncio
    async def test_returns_dict_from_structured_response(self):
        llm = _make_mock_llm()
        llm.complete_structured.return_value = _domain_analysis_result()
        analyzer = DomainAnalyzer(llm)

        result = await analyzer._analyze_domain("hospital management system")

        assert isinstance(result, dict)
        assert "agency_name" in result
        assert "description" in result
        assert "key_functions" in result

    @pytest.mark.asyncio
    async def test_passes_domain_description_to_llm(self):
        llm = _make_mock_llm()
        llm.complete_structured.return_value = _domain_analysis_result()
        analyzer = DomainAnalyzer(llm)

        await analyzer._analyze_domain("veterinary clinic management")

        call_args = llm.complete_structured.call_args
        messages = call_args[0][0]
        user_msg = next(m for m in messages if m["role"] == "user")
        assert "veterinary clinic management" in user_msg["content"]

    @pytest.mark.asyncio
    async def test_env_vars_included(self):
        llm = _make_mock_llm()
        llm.complete_structured.return_value = _domain_analysis_result(
            env_vars={"DATABASE_URL": "postgres://...", "STRIPE_KEY": ""}
        )
        analyzer = DomainAnalyzer(llm)

        result = await analyzer._analyze_domain("e-commerce platform")

        assert "DATABASE_URL" in result["env_vars"]
        assert "STRIPE_KEY" in result["env_vars"]


# ---------------------------------------------------------------------------
# Phase 2 — Agent Design
# ---------------------------------------------------------------------------

class TestPhase2AgentDesign:
    """Test the _design_agents phase."""

    @pytest.mark.asyncio
    async def test_returns_agent_blueprints(self):
        llm = _make_mock_llm()
        llm.complete_structured.return_value = _agent_designs_result()
        analyzer = DomainAnalyzer(llm)
        analysis = {"key_functions": ["scheduling"], "integrations": []}

        agents = await analyzer._design_agents("hospital management", analysis)

        assert isinstance(agents, list)
        assert all(isinstance(a, AgentBlueprint) for a in agents)
        assert len(agents) == 3

    @pytest.mark.asyncio
    async def test_maps_known_roles(self):
        llm = _make_mock_llm()
        llm.complete_structured.return_value = _agent_designs_result()
        analyzer = DomainAnalyzer(llm)

        agents = await analyzer._design_agents("hospital", {})

        roles = {a.role for a in agents}
        assert AgentRole.MANAGER in roles
        assert AgentRole.SPECIALIST in roles
        assert AgentRole.ANALYST in roles

    @pytest.mark.asyncio
    async def test_unknown_role_maps_to_custom(self):
        agent_mock = _ns(
            name="Wizard", role="wizard",
            title="Magic Wizard", system_prompt="You do magic.",
            capabilities=["spells"], temperature=0.9,
            can_spawn_sub_agents=False,
        )
        llm = _make_mock_llm()
        llm.complete_structured.return_value = _agent_designs_result(agents=[agent_mock])
        analyzer = DomainAnalyzer(llm)

        agents = await analyzer._design_agents("fantasy", {})

        assert agents[0].role == AgentRole.CUSTOM

    @pytest.mark.asyncio
    async def test_preserves_spawn_flag(self):
        llm = _make_mock_llm()
        llm.complete_structured.return_value = _agent_designs_result()
        analyzer = DomainAnalyzer(llm)

        agents = await analyzer._design_agents("hospital", {})

        manager = next(a for a in agents if a.name == "HospitalManager")
        assert manager.can_spawn_sub_agents is True
        specialist = next(a for a in agents if a.name == "PatientCareSpecialist")
        assert specialist.can_spawn_sub_agents is False


# ---------------------------------------------------------------------------
# Phase 3 — Tool Design
# ---------------------------------------------------------------------------

class TestPhase3ToolDesign:
    """Test the _design_tools phase."""

    @pytest.mark.asyncio
    async def test_assigns_tools_to_agents(self):
        llm = _make_mock_llm()
        llm.complete_structured.return_value = _tool_designs_result()
        analyzer = DomainAnalyzer(llm)
        agents = [
            AgentBlueprint(name="PatientCareSpecialist", role=AgentRole.SPECIALIST, system_prompt="care"),
            AgentBlueprint(name="BillingAnalyst", role=AgentRole.ANALYST, system_prompt="billing"),
        ]

        updated, shared = await analyzer._design_tools("hospital", {}, agents)

        care_agent = next(a for a in updated if a.name == "PatientCareSpecialist")
        assert any(t.name == "lookup_patient" for t in care_agent.tools)

        billing_agent = next(a for a in updated if a.name == "BillingAnalyst")
        assert any(t.name == "submit_claim" for t in billing_agent.tools)

    @pytest.mark.asyncio
    async def test_shared_tools_returned_separately(self):
        llm = _make_mock_llm()
        llm.complete_structured.return_value = _tool_designs_result()
        analyzer = DomainAnalyzer(llm)
        agents = [
            AgentBlueprint(name="PatientCareSpecialist", role=AgentRole.SPECIALIST, system_prompt="care"),
            AgentBlueprint(name="BillingAnalyst", role=AgentRole.ANALYST, system_prompt="billing"),
        ]

        _, shared = await analyzer._design_tools("hospital", {}, agents)

        assert len(shared) == 1
        assert shared[0].name == "send_notification"

    @pytest.mark.asyncio
    async def test_agent_without_tools_unchanged(self):
        llm = _make_mock_llm()
        tool = _ns(
            name="submit_claim", description="x", parameters=[],
            implementation_hint="", assigned_to=["BillingAnalyst"],
        )
        llm.complete_structured.return_value = _tool_designs_result(tools=[tool])
        analyzer = DomainAnalyzer(llm)
        agents = [
            AgentBlueprint(name="UnrelatedAgent", role=AgentRole.SUPPORT, system_prompt="support"),
            AgentBlueprint(name="BillingAnalyst", role=AgentRole.ANALYST, system_prompt="billing"),
        ]

        updated, _ = await analyzer._design_tools("hospital", {}, agents)

        unrelated = next(a for a in updated if a.name == "UnrelatedAgent")
        assert len(unrelated.tools) == 0


# ---------------------------------------------------------------------------
# Phase 4 — Team Organization
# ---------------------------------------------------------------------------

class TestPhase4TeamOrganization:
    """Test the _organize_teams phase."""

    @pytest.mark.asyncio
    async def test_creates_teams_with_leads(self):
        llm = _make_mock_llm()
        llm.complete_structured.return_value = _team_designs_result()
        analyzer = DomainAnalyzer(llm)
        agents = [
            AgentBlueprint(name="HospitalManager", role=AgentRole.MANAGER, system_prompt="manage"),
            AgentBlueprint(name="PatientCareSpecialist", role=AgentRole.SPECIALIST, system_prompt="care"),
            AgentBlueprint(name="BillingAnalyst", role=AgentRole.ANALYST, system_prompt="bill"),
        ]

        teams = await analyzer._organize_teams("hospital", {}, agents)

        assert len(teams) == 2
        clinical = next(t for t in teams if t.name == "Clinical Team")
        assert clinical.lead.name == "HospitalManager"
        assert any(a.name == "PatientCareSpecialist" for a in clinical.agents)

    @pytest.mark.asyncio
    async def test_unassigned_agents_go_to_general_team(self):
        llm = _make_mock_llm()
        # Team design only mentions HospitalManager, not the others
        llm.complete_structured.return_value = _team_designs_result(teams=[
            _ns(name="Ops", description="ops", lead_agent="HospitalManager", member_agents=[]),
        ])
        analyzer = DomainAnalyzer(llm)
        agents = [
            AgentBlueprint(name="HospitalManager", role=AgentRole.MANAGER, system_prompt="m"),
            AgentBlueprint(name="Orphan", role=AgentRole.SUPPORT, system_prompt="o"),
        ]

        teams = await analyzer._organize_teams("hospital", {}, agents)

        general = next(t for t in teams if t.name == "General")
        assert any(a.name == "Orphan" for a in general.agents)


# ---------------------------------------------------------------------------
# Phase 5 — Workflow Design
# ---------------------------------------------------------------------------

class TestPhase5WorkflowDesign:
    """Test the _design_workflows phase."""

    @pytest.mark.asyncio
    async def test_creates_workflows_with_steps(self):
        llm = _make_mock_llm()
        llm.complete_structured.return_value = _workflow_designs_result()
        analyzer = DomainAnalyzer(llm)
        teams = [TeamBlueprint(name="Clinical Team", description="clinical")]

        workflows = await analyzer._design_workflows("hospital", {"key_functions": ["intake"]}, teams)

        assert len(workflows) == 1
        wf = workflows[0]
        assert isinstance(wf, WorkflowBlueprint)
        assert len(wf.steps) == 2
        assert wf.steps[1].depends_on == ["s1"]


# ---------------------------------------------------------------------------
# Phase 6 — API Design
# ---------------------------------------------------------------------------

class TestPhase6APIDesign:
    """Test the _design_api phase."""

    @pytest.mark.asyncio
    async def test_creates_api_endpoints(self):
        llm = _make_mock_llm()
        llm.complete_structured.return_value = _api_designs_result()
        analyzer = DomainAnalyzer(llm)
        teams = [TeamBlueprint(name="Clinical Team", description="clinical")]

        endpoints = await analyzer._design_api("hospital", {"key_functions": []}, teams)

        assert len(endpoints) == 3
        assert all(isinstance(ep, APIEndpoint) for ep in endpoints)
        paths = {ep.path for ep in endpoints}
        assert "/api/task" in paths


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

class TestFullPipeline:
    """Test the analyze() method end-to-end with all 6 phases mocked."""

    @pytest.mark.asyncio
    async def test_full_pipeline_produces_valid_blueprint(self):
        llm = _make_mock_llm()
        _wire_all_phases(llm)
        analyzer = DomainAnalyzer(llm)

        blueprint = await analyzer.analyze("hospital management system")

        assert isinstance(blueprint, AgencyBlueprint)
        assert blueprint.name == "HealthPilot AI"
        assert blueprint.slug == "healthpilot-ai"
        assert len(blueprint.teams) >= 1
        assert len(blueprint.all_agents) >= 1
        assert len(blueprint.workflows) >= 1
        assert len(blueprint.api_endpoints) >= 1

    @pytest.mark.asyncio
    async def test_all_six_llm_calls_made(self):
        llm = _make_mock_llm()
        _wire_all_phases(llm)
        analyzer = DomainAnalyzer(llm)

        await analyzer.analyze("hospital management")

        assert llm.complete_structured.call_count == 6

    @pytest.mark.asyncio
    async def test_blueprint_has_shared_tools(self):
        llm = _make_mock_llm()
        _wire_all_phases(llm)
        analyzer = DomainAnalyzer(llm)

        blueprint = await analyzer.analyze("hospital management")

        assert len(blueprint.shared_tools) >= 1
        assert blueprint.shared_tools[0].name == "send_notification"

    @pytest.mark.asyncio
    async def test_environment_variables_propagated(self):
        llm = _make_mock_llm()
        _wire_all_phases(llm, domain_result=_domain_analysis_result(
            env_vars={"MY_SECRET": "default_val"}
        ))
        analyzer = DomainAnalyzer(llm)

        blueprint = await analyzer.analyze("hospital management")

        assert "MY_SECRET" in blueprint.environment_variables

    @pytest.mark.asyncio
    async def test_model_passed_to_blueprint(self):
        llm = _make_mock_llm()
        _wire_all_phases(llm)
        analyzer = DomainAnalyzer(llm)

        blueprint = await analyzer.analyze("hospital management", model="gpt-4o")

        assert blueprint.model == "gpt-4o"


# ---------------------------------------------------------------------------
# Error recovery
# ---------------------------------------------------------------------------

class TestErrorRecovery:
    """Test that failures in individual phases produce safe fallbacks."""

    @pytest.mark.asyncio
    async def test_phase1_failure_uses_fallback(self):
        llm = _make_mock_llm()
        llm.complete_structured = AsyncMock(side_effect=[
            ValueError("LLM returned garbage"),          # Phase 1 fails
            _agent_designs_result(),                      # Phase 2
            _tool_designs_result(),                       # Phase 3
            _team_designs_result(),                       # Phase 4
            _workflow_designs_result(),                   # Phase 5
            _api_designs_result(),                        # Phase 6
        ])
        analyzer = DomainAnalyzer(llm)

        blueprint = await analyzer.analyze("hospital management system")

        assert blueprint.name == "AI Agency"  # fallback name
        assert isinstance(blueprint, AgencyBlueprint)

    @pytest.mark.asyncio
    async def test_phase2_failure_gives_empty_agents(self):
        llm = _make_mock_llm()
        llm.complete_structured = AsyncMock(side_effect=[
            _domain_analysis_result(),
            RuntimeError("Phase 2 exploded"),             # Phase 2 fails
            _tool_designs_result(),                       # Phase 3
            # Phase 4 will get empty agents -> fallback team
            _team_designs_result(teams=[]),                # Phase 4
            _workflow_designs_result(),                    # Phase 5
            _api_designs_result(),                        # Phase 6
        ])
        analyzer = DomainAnalyzer(llm)

        blueprint = await analyzer.analyze("hospital")

        # Should not crash; agents list is empty
        assert isinstance(blueprint, AgencyBlueprint)

    @pytest.mark.asyncio
    async def test_phase3_failure_proceeds_without_tools(self):
        llm = _make_mock_llm()
        llm.complete_structured = AsyncMock(side_effect=[
            _domain_analysis_result(),
            _agent_designs_result(),
            Exception("Tool design failed"),              # Phase 3 fails
            _team_designs_result(),
            _workflow_designs_result(),
            _api_designs_result(),
        ])
        analyzer = DomainAnalyzer(llm)

        blueprint = await analyzer.analyze("hospital")

        assert isinstance(blueprint, AgencyBlueprint)
        assert len(blueprint.shared_tools) == 0

    @pytest.mark.asyncio
    async def test_phase5_failure_proceeds_without_workflows(self):
        llm = _make_mock_llm()
        llm.complete_structured = AsyncMock(side_effect=[
            _domain_analysis_result(),
            _agent_designs_result(),
            _tool_designs_result(),
            _team_designs_result(),
            Exception("Workflow design failed"),          # Phase 5 fails
            _api_designs_result(),
        ])
        analyzer = DomainAnalyzer(llm)

        blueprint = await analyzer.analyze("hospital")

        assert isinstance(blueprint, AgencyBlueprint)
        assert blueprint.workflows == []

    @pytest.mark.asyncio
    async def test_phase6_failure_proceeds_without_api(self):
        llm = _make_mock_llm()
        llm.complete_structured = AsyncMock(side_effect=[
            _domain_analysis_result(),
            _agent_designs_result(),
            _tool_designs_result(),
            _team_designs_result(),
            _workflow_designs_result(),
            Exception("API design failed"),               # Phase 6 fails
        ])
        analyzer = DomainAnalyzer(llm)

        blueprint = await analyzer.analyze("hospital")

        assert isinstance(blueprint, AgencyBlueprint)
        assert blueprint.api_endpoints == []


# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------

class TestSlugGeneration:
    """Test the _make_slug utility."""

    def test_basic_slug(self):
        assert DomainAnalyzer._make_slug("My Cool Agency") == "my-cool-agency"

    def test_special_characters_removed(self):
        assert DomainAnalyzer._make_slug("Health & Wellness (Pro)") == "health-wellness-pro"

    def test_multiple_spaces_collapsed(self):
        assert DomainAnalyzer._make_slug("Lots   Of   Spaces") == "lots-of-spaces"

    def test_leading_trailing_hyphens_stripped(self):
        assert DomainAnalyzer._make_slug("  --test--  ") == "test"


# ---------------------------------------------------------------------------
# Domain-appropriate outputs
# ---------------------------------------------------------------------------

class TestDomainAppropriateness:
    """Test that different domains produce contextually relevant blueprints."""

    @pytest.mark.asyncio
    async def test_ecommerce_domain(self):
        """E-commerce domain should produce e-commerce-related blueprint."""
        llm = _make_mock_llm()
        ecom_domain = _domain_analysis_result(
            agency_name="ShopBot AI",
            description="E-commerce automation agency",
            key_functions=["order_processing", "inventory_mgmt", "customer_support"],
        )
        ecom_agents = _agent_designs_result(agents=[
            _ns(name="OrderManager", role="manager", title="Order Ops Manager",
                system_prompt="Handle orders", capabilities=["order_tracking"],
                temperature=0.5, can_spawn_sub_agents=True),
            _ns(name="InventorySpecialist", role="specialist", title="Inventory Specialist",
                system_prompt="Manage stock", capabilities=["stock_levels"],
                temperature=0.3, can_spawn_sub_agents=False),
        ])
        ecom_tools = _tool_designs_result(tools=[
            _ns(name="track_order", description="Track order", parameters=[],
                implementation_hint="", assigned_to=["OrderManager"]),
            _ns(name="check_stock", description="Check stock", parameters=[],
                implementation_hint="", assigned_to=["InventorySpecialist"]),
        ])
        ecom_teams = _team_designs_result(teams=[
            _ns(name="Ops Team", description="Operations",
                lead_agent="OrderManager", member_agents=["InventorySpecialist"]),
        ])
        _wire_all_phases(llm, domain_result=ecom_domain, agents_result=ecom_agents,
                         tools_result=ecom_tools, teams_result=ecom_teams)
        analyzer = DomainAnalyzer(llm)

        blueprint = await analyzer.analyze("e-commerce platform for fashion retail")

        assert blueprint.name == "ShopBot AI"
        assert "e-commerce" in blueprint.description.lower() or "commerce" in blueprint.description.lower()

    @pytest.mark.asyncio
    async def test_education_domain(self):
        """Education domain should produce education-related blueprint."""
        llm = _make_mock_llm()
        edu_domain = _domain_analysis_result(
            agency_name="EduAssist AI",
            description="AI tutoring and curriculum management",
            key_functions=["tutoring", "grading", "curriculum_design"],
        )
        edu_agents = _agent_designs_result(agents=[
            _ns(name="TutorAgent", role="specialist", title="AI Tutor",
                system_prompt="You tutor students", capabilities=["math", "science"],
                temperature=0.7, can_spawn_sub_agents=False),
        ])
        edu_tools = _tool_designs_result(tools=[
            _ns(name="quiz_gen", description="Generate quiz", parameters=[],
                implementation_hint="", assigned_to=["TutorAgent"]),
        ])
        edu_teams = _team_designs_result(teams=[
            _ns(name="Teaching Team", description="Education",
                lead_agent="TutorAgent", member_agents=[]),
        ])
        _wire_all_phases(llm, domain_result=edu_domain, agents_result=edu_agents,
                         tools_result=edu_tools, teams_result=edu_teams)
        analyzer = DomainAnalyzer(llm)

        blueprint = await analyzer.analyze("online education platform")

        assert blueprint.name == "EduAssist AI"
        agents = blueprint.all_agents
        agent_names = [a.name for a in agents]
        assert "TutorAgent" in agent_names


# ---------------------------------------------------------------------------
# Blueprint structural integrity
# ---------------------------------------------------------------------------

class TestBlueprintStructure:
    """Verify that the produced blueprint has all required structural elements."""

    @pytest.mark.asyncio
    async def test_all_agents_accessible_via_property(self):
        llm = _make_mock_llm()
        _wire_all_phases(llm)
        analyzer = DomainAnalyzer(llm)

        blueprint = await analyzer.analyze("hospital management")

        all_agents = blueprint.all_agents
        # Leads + members from teams should all be reachable
        assert len(all_agents) >= 2

    @pytest.mark.asyncio
    async def test_all_tools_accessible_via_property(self):
        llm = _make_mock_llm()
        _wire_all_phases(llm)
        analyzer = DomainAnalyzer(llm)

        blueprint = await analyzer.analyze("hospital management")

        all_tools = blueprint.all_tools
        tool_names = {t.name for t in all_tools}
        assert "send_notification" in tool_names  # shared tool
        assert "lookup_patient" in tool_names     # agent tool

    @pytest.mark.asyncio
    async def test_domain_truncated_to_500_chars(self):
        llm = _make_mock_llm()
        _wire_all_phases(llm)
        analyzer = DomainAnalyzer(llm)
        long_domain = "x" * 1000

        blueprint = await analyzer.analyze(long_domain)

        assert len(blueprint.domain) <= 500

    @pytest.mark.asyncio
    async def test_workflow_steps_have_dependencies(self):
        llm = _make_mock_llm()
        _wire_all_phases(llm)
        analyzer = DomainAnalyzer(llm)

        blueprint = await analyzer.analyze("hospital management")

        wf = blueprint.workflows[0]
        step2 = next(s for s in wf.steps if s.id == "s2")
        assert "s1" in step2.depends_on
