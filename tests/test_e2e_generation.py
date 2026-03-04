"""End-to-end tests for agency code generation."""

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from forge.core.blueprint import (
    AgencyBlueprint, AgentBlueprint, AgentRole, TeamBlueprint,
    ToolBlueprint, WorkflowBlueprint, WorkflowStep, APIEndpoint,
)
from forge.core.archetypes import inject_archetypes
from forge.core.quality import BlueprintEvaluator
from forge.generators.agency_generator import AgencyGenerator


@pytest.fixture
def output_dir(tmp_path):
    """Temporary output directory for generated agencies."""
    yield tmp_path
    # Cleanup handled by tmp_path fixture


@pytest.fixture
def email_blueprint():
    """Blueprint with email tools to test built-in detection."""
    agent = AgentBlueprint(
        name="Outreach Agent",
        role=AgentRole.SPECIALIST,
        title="Email Outreach Specialist",
        system_prompt="You send personalized outreach emails to prospects.",
        capabilities=["Send emails", "Track opens"],
        tools=[
            ToolBlueprint(
                name="send_email",
                description="Send an email to a customer",
                parameters=[
                    {"name": "to", "type": "string", "description": "Recipient", "required": True},
                    {"name": "subject", "type": "string", "description": "Subject", "required": True},
                    {"name": "body", "type": "string", "description": "Body", "required": True},
                ],
            ),
            ToolBlueprint(
                name="http_request",
                description="Make API calls",
                parameters=[
                    {"name": "url", "type": "string", "description": "URL", "required": True},
                ],
            ),
        ],
    )

    lead = AgentBlueprint(
        name="Team Lead",
        role=AgentRole.MANAGER,
        title="Operations Lead",
        system_prompt="You manage the outreach team.",
        capabilities=["Team management"],
        can_spawn_sub_agents=True,
    )

    return AgencyBlueprint(
        name="Email Test Agency",
        slug="email-test-agency",
        description="Tests email tool generation",
        domain="Email outreach and communication",
        teams=[TeamBlueprint(
            name="Outreach Team",
            description="Email outreach",
            lead=lead,
            agents=[agent],
        )],
        workflows=[WorkflowBlueprint(
            name="Send Campaign",
            steps=[WorkflowStep(id="s1", description="Send emails")],
        )],
        api_endpoints=[APIEndpoint(path="/api/task", method="POST", description="Task")],
        shared_tools=[
            ToolBlueprint(name="send_webhook", description="Send notifications", parameters=[
                {"name": "url", "type": "string", "description": "URL", "required": True},
                {"name": "payload", "type": "string", "description": "Data", "required": True},
            ]),
        ],
        model="gpt-4",
    )


class TestE2EGeneration:
    def test_generates_all_expected_files(self, email_blueprint, output_dir):
        """Verify all expected files are created."""
        gen = AgencyGenerator(output_base=output_dir)
        path = gen.generate(email_blueprint)

        assert (path / "main.py").exists()
        assert (path / "api_server.py").exists()
        assert (path / "blueprint.json").exists()
        assert (path / "Dockerfile").exists()
        assert (path / "docker-compose.yml").exists()
        assert (path / "requirements.txt").exists()
        assert (path / "README.md").exists()
        assert (path / "agents").is_dir()
        assert (path / "tools").is_dir()

    def test_email_tool_uses_builtin(self, email_blueprint, output_dir):
        """Verify email tool imports from built-in integrations, not a stub."""
        gen = AgencyGenerator(output_base=output_dir)
        path = gen.generate(email_blueprint)

        email_tool_path = path / "tools" / "tool_send_email.py"
        assert email_tool_path.exists(), "tool_send_email.py should be generated"

        content = email_tool_path.read_text(encoding="utf-8")
        assert "forge.runtime.integrations" in content, \
            f"Email tool should import from built-in integrations, got:\n{content}"

    def test_http_tool_uses_builtin(self, email_blueprint, output_dir):
        """Verify HTTP tool imports from built-in integrations."""
        gen = AgencyGenerator(output_base=output_dir)
        path = gen.generate(email_blueprint)

        http_tool_path = path / "tools" / "tool_http_request.py"
        assert http_tool_path.exists(), "tool_http_request.py should be generated"

        content = http_tool_path.read_text(encoding="utf-8")
        assert "forge.runtime.integrations" in content, \
            f"HTTP tool should import from built-in integrations, got:\n{content}"

    def test_webhook_tool_uses_builtin(self, email_blueprint, output_dir):
        """Verify webhook tool imports from built-in integrations."""
        gen = AgencyGenerator(output_base=output_dir)
        path = gen.generate(email_blueprint)

        webhook_tool_path = path / "tools" / "tool_send_webhook.py"
        assert webhook_tool_path.exists()

        content = webhook_tool_path.read_text(encoding="utf-8")
        assert "forge.runtime.integrations" in content

    def test_requirements_no_forge_pip(self, email_blueprint, output_dir):
        """Verify requirements.txt doesn't reference forge-agency pip package."""
        gen = AgencyGenerator(output_base=output_dir)
        path = gen.generate(email_blueprint)

        content = (path / "requirements.txt").read_text(encoding="utf-8")
        assert "forge-agency" not in content, \
            "requirements.txt should not reference forge-agency (runtime is bundled)"

    def test_blueprint_json_valid(self, email_blueprint, output_dir):
        """Verify blueprint.json is valid and round-trips."""
        import json
        gen = AgencyGenerator(output_base=output_dir)
        path = gen.generate(email_blueprint)

        bp_path = path / "blueprint.json"
        content = bp_path.read_text(encoding="utf-8")
        data = json.loads(content)
        assert data["name"] == "Email Test Agency"
        assert data["slug"] == "email-test-agency"

    def test_archetype_injection_then_generate(self, email_blueprint, output_dir):
        """Verify generation works after injecting archetypes."""
        enhanced = inject_archetypes(email_blueprint)
        assert len(enhanced.all_agents) > len(email_blueprint.all_agents)

        gen = AgencyGenerator(output_base=output_dir)
        path = gen.generate(enhanced)

        agent_files = list((path / "agents").glob("agent_*.py"))
        assert len(agent_files) >= 5, f"Expected 5+ agent files after archetype injection, got {len(agent_files)}"

    def test_quality_score_for_generated_blueprint(self, email_blueprint):
        """Verify the blueprint scores reasonably on quality evaluation."""
        enhanced = inject_archetypes(email_blueprint)
        evaluator = BlueprintEvaluator()
        score = evaluator.evaluate(enhanced)
        
        assert score.overall_score > 0.3, f"Blueprint should score above 0.3, got {score.overall_score}"
        assert len(score.dimension_scores) >= 10

    def test_overwrite_flag(self, email_blueprint, output_dir):
        """Verify overwrite flag works."""
        gen = AgencyGenerator(output_base=output_dir)
        gen.generate(email_blueprint)

        # Without overwrite should fail
        with pytest.raises(FileExistsError):
            gen.generate(email_blueprint, overwrite=False)

        # With overwrite should succeed
        path = gen.generate(email_blueprint, overwrite=True)
        assert path.exists()
