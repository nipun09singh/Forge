"""Tests for forge.core.quality"""

import pytest
from forge.core.quality import (
    BlueprintEvaluator,
    QualityDimension,
    QualityRubric,
    QualityScore,
    DimensionScore,
    format_quality_report,
)
from forge.core.blueprint import (
    AgencyBlueprint,
    AgentBlueprint,
    AgentRole,
    TeamBlueprint,
    ToolBlueprint,
    WorkflowBlueprint,
    WorkflowStep,
    APIEndpoint,
)


# ---------------------------------------------------------------------------
# Blueprint factory helpers
# ---------------------------------------------------------------------------

def _make_agent(name: str, role: AgentRole = AgentRole.SPECIALIST,
                prompt: str = "You are a helpful specialist.", **kwargs) -> AgentBlueprint:
    return AgentBlueprint(name=name, role=role, system_prompt=prompt, **kwargs)


def _healthcare_blueprint(*, include_qa: bool = True, include_sales: bool = False) -> AgencyBlueprint:
    """Rich healthcare blueprint with optional QA/sales agents."""
    agents = [
        _make_agent("PatientIntake", AgentRole.COORDINATOR,
                     "You coordinate patient intake and triage. Handle errors and escalate failures.",
                     capabilities=["Patient triage", "Scheduling"],
                     tools=[ToolBlueprint(name="lookup_patient", description="Lookup patient records",
                                          parameters=[{"name": "id", "type": "string", "description": "Patient ID", "required": True}])]),
        _make_agent("DiagnosticAnalyst", AgentRole.ANALYST,
                     "You analyse lab results and imaging data. Retry on transient failures.",
                     capabilities=["Lab analysis", "Imaging review"]),
        _make_agent("TreatmentSpecialist", AgentRole.SPECIALIST,
                     "You recommend treatment plans based on diagnosis. Provide fallback options.",
                     tools=[ToolBlueprint(name="drug_interactions", description="Check drug interactions",
                                          parameters=[{"name": "drugs", "type": "string", "description": "List", "required": True}])]),
        _make_agent("HealthcareWriter", AgentRole.WRITER,
                     "You draft medical reports and discharge summaries."),
        _make_agent("SelfImprovementBot", AgentRole.CUSTOM,
                     "You monitor analytics and optimize agency performance. Adapt and learn from outcomes."),
    ]

    if include_qa:
        agents.append(
            _make_agent("QA_Reviewer", AgentRole.REVIEWER,
                         "You review all outputs for quality and accuracy. Audit and validate."))

    if include_sales:
        agents.append(
            _make_agent("SalesRep", AgentRole.SPECIALIST,
                         "You handle revenue, billing and upsell."))

    lead = _make_agent("ClinicManager", AgentRole.MANAGER,
                        "You manage the healthcare team and delegate tasks.",
                        capabilities=["Delegation", "Scheduling"],
                        can_spawn_sub_agents=True)

    return AgencyBlueprint(
        name="Healthcare Agency",
        slug="healthcare-agency",
        description="AI-powered healthcare support",
        domain="Healthcare: patient intake, diagnostics, treatment planning, and follow-up care.",
        teams=[
            TeamBlueprint(name="Clinical Team", description="Core clinical ops",
                          lead=lead, agents=agents, allow_dynamic_scaling=True),
        ],
        workflows=[
            WorkflowBlueprint(name="Patient Flow", steps=[
                WorkflowStep(id="intake", description="Patient intake and triage"),
                WorkflowStep(id="diag", description="Run diagnostics", depends_on=["intake"]),
                WorkflowStep(id="treat", description="Propose treatment", depends_on=["diag"]),
                WorkflowStep(id="review", description="Quality review of recommendations", depends_on=["treat"]),
            ]),
            WorkflowBlueprint(name="Follow-up", steps=[
                WorkflowStep(id="f1", description="Schedule follow-up"),
                WorkflowStep(id="f2", description="Feedback collection", depends_on=["f1"]),
            ]),
        ],
        api_endpoints=[
            APIEndpoint(path="/api/task", method="POST", description="Submit a task"),
            APIEndpoint(path="/api/patient", method="GET", description="Get patient info"),
        ],
        shared_tools=[
            ToolBlueprint(name="send_email", description="Send email", parameters=[]),
            ToolBlueprint(name="http_request", description="HTTP calls", parameters=[]),
        ],
        model="gpt-4",
    )


def _minimal_blueprint() -> AgencyBlueprint:
    """Bare-bones blueprint that should score poorly on most dimensions."""
    agent = _make_agent("Helper", AgentRole.SPECIALIST, "Help people.")
    return AgencyBlueprint(
        name="Minimal",
        slug="minimal",
        description="Minimal",
        domain="General",
        teams=[TeamBlueprint(name="Team", agents=[agent])],
    )


# ---------------------------------------------------------------------------
# Original tests (preserved)
# ---------------------------------------------------------------------------

class TestBlueprintEvaluator:
    def test_evaluate_produces_score(self, sample_blueprint):
        evaluator = BlueprintEvaluator()
        score = evaluator.evaluate(sample_blueprint)
        assert isinstance(score, QualityScore)
        assert 0 <= score.overall_score <= 1

    def test_evaluate_has_dimensions(self, sample_blueprint):
        evaluator = BlueprintEvaluator()
        score = evaluator.evaluate(sample_blueprint)
        assert len(score.dimension_scores) >= 10

    def test_custom_threshold(self, sample_blueprint):
        rubric = QualityRubric(threshold=0.5)
        evaluator = BlueprintEvaluator(rubric=rubric)
        score = evaluator.evaluate(sample_blueprint)
        assert score.threshold == 0.5


class TestQualityReport:
    def test_format_report(self, sample_blueprint):
        evaluator = BlueprintEvaluator()
        score = evaluator.evaluate(sample_blueprint)
        report = format_quality_report(score)
        assert "Quality Assessment" in report
        assert "Overall Score" in report


# ---------------------------------------------------------------------------
# Domain-appropriate scoring
# ---------------------------------------------------------------------------

class TestDomainAppropriateScoring:
    """Verify that well-built blueprints score well and sparse ones score poorly."""

    def test_healthcare_with_all_archetypes_scores_well(self):
        bp = _healthcare_blueprint(include_qa=True)
        score = BlueprintEvaluator().evaluate(bp)
        assert score.overall_score >= 0.6, f"Expected ≥0.6, got {score.overall_score}"

    def test_healthcare_without_sales_not_penalised_by_default(self):
        """Business archetypes are opt-in; absence should not hurt the score."""
        bp = _healthcare_blueprint(include_qa=True, include_sales=False)
        score_no_sales = BlueprintEvaluator().evaluate(bp)
        bp_sales = _healthcare_blueprint(include_qa=True, include_sales=True)
        score_with_sales = BlueprintEvaluator().evaluate(bp_sales)
        # Without business archetypes flag, adding a sales agent should have
        # negligible impact on scoring (only indirectly via agent count).
        assert abs(score_no_sales.overall_score - score_with_sales.overall_score) < 0.15

    def test_minimal_blueprint_scores_low(self):
        bp = _minimal_blueprint()
        score = BlueprintEvaluator().evaluate(bp)
        assert score.overall_score < 0.5, f"Minimal blueprint should score <0.5, got {score.overall_score}"
        assert len(score.critical_issues) > 0, "Minimal blueprint should have critical issues"

    def test_iteration_tracked(self):
        bp = _healthcare_blueprint()
        score = BlueprintEvaluator().evaluate(bp, iteration=3)
        assert score.iteration == 3


# ---------------------------------------------------------------------------
# Individual dimension tests
# ---------------------------------------------------------------------------

class TestRoleCoverage:
    def test_many_agents_high_score(self):
        bp = _healthcare_blueprint()
        evaluator = BlueprintEvaluator()
        dim = _get_dim(evaluator.evaluate(bp), QualityDimension.ROLE_COVERAGE)
        assert dim.score >= 0.7

    def test_single_agent_low_score(self):
        bp = _minimal_blueprint()
        dim = _get_dim(BlueprintEvaluator().evaluate(bp), QualityDimension.ROLE_COVERAGE)
        assert dim.score <= 0.5


class TestAgentDepth:
    def test_shallow_prompts_penalised(self):
        """Agents with very short prompts lose points."""
        agent = _make_agent("ShallowBot", prompt="Hi")
        bp = AgencyBlueprint(name="X", slug="x", description="x", domain="x",
                             teams=[TeamBlueprint(name="T", agents=[agent])])
        dim = _get_dim(BlueprintEvaluator().evaluate(bp), QualityDimension.AGENT_DEPTH)
        assert dim.score < 0.8


class TestTooling:
    def test_no_tools_low_score(self):
        bp = _minimal_blueprint()  # helper agent has no tools
        dim = _get_dim(BlueprintEvaluator().evaluate(bp), QualityDimension.TOOLING)
        assert dim.score <= 0.5

    def test_rich_tools_higher_score(self):
        bp = _healthcare_blueprint()
        dim = _get_dim(BlueprintEvaluator().evaluate(bp), QualityDimension.TOOLING)
        assert dim.score >= 0.5


class TestTeamArchitecture:
    def test_team_with_lead_scores_well(self):
        bp = _healthcare_blueprint()
        dim = _get_dim(BlueprintEvaluator().evaluate(bp), QualityDimension.TEAM_ARCHITECTURE)
        assert dim.score >= 0.8

    def test_team_without_lead_penalised(self):
        bp = _minimal_blueprint()  # no lead
        dim = _get_dim(BlueprintEvaluator().evaluate(bp), QualityDimension.TEAM_ARCHITECTURE)
        assert dim.score < 1.0


class TestWorkflowCompleteness:
    def test_no_workflows_low_score(self):
        bp = _minimal_blueprint()
        dim = _get_dim(BlueprintEvaluator().evaluate(bp), QualityDimension.WORKFLOW_COMPLETENESS)
        assert dim.score <= 0.3

    def test_good_workflows_high_score(self):
        bp = _healthcare_blueprint()
        dim = _get_dim(BlueprintEvaluator().evaluate(bp), QualityDimension.WORKFLOW_COMPLETENESS)
        assert dim.score >= 0.8


class TestUniversals:
    def test_all_mandatory_present(self):
        """Healthcare blueprint has QA, intake, self-improvement, analytics."""
        bp = _healthcare_blueprint(include_qa=True)
        dim = _get_dim(BlueprintEvaluator().evaluate(bp), QualityDimension.UNIVERSALS)
        assert dim.score >= 0.5

    def test_missing_mandatory_penalised(self):
        bp = _minimal_blueprint()
        dim = _get_dim(BlueprintEvaluator().evaluate(bp), QualityDimension.UNIVERSALS)
        assert dim.score < 0.5

    def test_business_archetypes_ignored_when_opt_out(self):
        bp = _healthcare_blueprint(include_qa=True)
        rubric_off = QualityRubric(include_business_archetypes=False)
        score_off = BlueprintEvaluator(rubric_off).evaluate(bp)
        dim_off = _get_dim(score_off, QualityDimension.UNIVERSALS)
        rubric_on = QualityRubric(include_business_archetypes=True)
        score_on = BlueprintEvaluator(rubric_on).evaluate(bp)
        dim_on = _get_dim(score_on, QualityDimension.UNIVERSALS)
        # With business archetypes on but missing, score should be lower
        assert dim_on.score <= dim_off.score

    def test_include_business_archetypes_true(self):
        bp = _healthcare_blueprint(include_qa=True)
        rubric = QualityRubric(include_business_archetypes=True)
        score = BlueprintEvaluator(rubric).evaluate(bp)
        dim = _get_dim(score, QualityDimension.UNIVERSALS)
        # Without growth/customer_success/lead_generation/revenue agents the
        # score should be noticeably lower than 1.0
        assert dim.score < 1.0


class TestCollaboration:
    def test_good_workflows_boost_score(self):
        bp = _healthcare_blueprint()
        dim = _get_dim(BlueprintEvaluator().evaluate(bp), QualityDimension.WORKFLOW_COMPLETENESS)
        assert dim.score >= 0.8


# ---------------------------------------------------------------------------
# Report contents
# ---------------------------------------------------------------------------

class TestQualityReportContents:
    def test_report_contains_all_dimensions(self):
        bp = _healthcare_blueprint()
        score = BlueprintEvaluator().evaluate(bp)
        report = format_quality_report(score)
        for dim in QualityDimension:
            assert dim.value in report, f"Dimension {dim.value} missing from report"

    def test_report_shows_pass_or_fail(self):
        bp = _healthcare_blueprint()
        score = BlueprintEvaluator().evaluate(bp)
        report = format_quality_report(score)
        assert "PASSED" in report or "FAILED" in report


# ---------------------------------------------------------------------------
# Threshold filtering
# ---------------------------------------------------------------------------

class TestThresholdFiltering:
    def test_low_threshold_passes_easily(self):
        bp = _minimal_blueprint()
        rubric = QualityRubric(threshold=0.1)
        score = BlueprintEvaluator(rubric).evaluate(bp)
        assert score.passed is True

    def test_high_threshold_fails_easily(self):
        bp = _minimal_blueprint()
        rubric = QualityRubric(threshold=0.99)
        score = BlueprintEvaluator(rubric).evaluate(bp)
        assert score.passed is False

    def test_critical_vs_recommendations(self):
        bp = _minimal_blueprint()
        score = BlueprintEvaluator().evaluate(bp)
        # Minimal blueprint should have at least some critical issues (<0.5 dims)
        assert len(score.critical_issues) > 0
        # And possibly some recommendations (0.5-0.8 dims)
        assert isinstance(score.recommendations, list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_dim(score: QualityScore, dim: QualityDimension) -> DimensionScore:
    for ds in score.dimension_scores:
        if ds.dimension == dim:
            return ds
    raise ValueError(f"Dimension {dim} not found in score")
