"""Master agency generator — orchestrates all sub-generators to produce a complete agency."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from forge.core.blueprint import AgencyBlueprint
from forge.generators.agent_generator import AgentGenerator
from forge.generators.tool_generator import ToolGenerator
from forge.generators.orchestration_gen import OrchestrationGenerator
from forge.generators.deployment_gen import DeploymentGenerator

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


class AgencyGenerator:
    """
    Generates a complete, deployable AI agency from an AgencyBlueprint.
    
    Orchestrates sub-generators to produce:
    - Agent modules with tools
    - Main orchestration file
    - API server
    - Deployment configs (Docker, requirements)
    - README documentation
    """

    def __init__(self, output_base: Path | None = None) -> None:
        self.output_base = output_base or Path("generated")
        self.agent_gen = AgentGenerator()
        self.tool_gen = ToolGenerator()
        self.orchestration_gen = OrchestrationGenerator()
        self.deployment_gen = DeploymentGenerator()
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def generate(self, blueprint: AgencyBlueprint, overwrite: bool = False) -> Path:
        """
        Generate a complete agency project.
        
        Returns the path to the generated agency directory.
        """
        output_dir = self.output_base / blueprint.slug
        
        if output_dir.exists():
            if overwrite:
                shutil.rmtree(output_dir)
                logger.info(f"Removed existing agency directory: {output_dir}")
            else:
                raise FileExistsError(
                    f"Agency directory already exists: {output_dir}. Use overwrite=True to replace."
                )

        # Create directory structure
        output_dir.mkdir(parents=True, exist_ok=True)
        agents_dir = output_dir / "agents"
        agents_dir.mkdir(exist_ok=True)
        tools_dir = output_dir / "tools"
        tools_dir.mkdir(exist_ok=True)

        generated_files: list[Path] = []

        # 1. Generate shared tools
        logger.info("Generating shared tools...")
        shared_tool_paths = self.tool_gen.generate_all(blueprint.shared_tools, tools_dir)
        generated_files.extend(shared_tool_paths)

        # 2. Generate agent-specific tools
        for agent_bp in blueprint.all_agents:
            if agent_bp.tools:
                agent_tool_paths = self.tool_gen.generate_all(agent_bp.tools, tools_dir)
                generated_files.extend(agent_tool_paths)

        # 3. Generate agent modules
        logger.info("Generating agent modules...")
        for agent_bp in blueprint.all_agents:
            path = self.agent_gen.generate(agent_bp, agents_dir)
            generated_files.append(path)

        # 4. Generate main orchestration
        logger.info("Generating orchestration...")
        main_path = self.orchestration_gen.generate_main(blueprint, output_dir)
        generated_files.append(main_path)

        api_path = self.orchestration_gen.generate_api_server(blueprint, output_dir)
        generated_files.append(api_path)

        # 5. Generate deployment configs
        logger.info("Generating deployment configs...")
        deploy_paths = self.deployment_gen.generate_all(blueprint, output_dir)
        generated_files.extend(deploy_paths)

        # 6. Create __init__.py files
        (agents_dir / "__init__.py").write_text('"""Generated agent modules."""\n', encoding="utf-8")
        (tools_dir / "__init__.py").write_text('"""Generated tool modules."""\n', encoding="utf-8")

        # 7. Write the blueprint as JSON for reference
        blueprint_path = output_dir / "blueprint.json"
        blueprint_path.write_text(blueprint.model_dump_json(indent=2), encoding="utf-8")
        generated_files.append(blueprint_path)

        # 8. Generate self-test
        self._generate_selftest(blueprint, output_dir)

        logger.info(
            f"Agency '{blueprint.name}' generated at {output_dir} "
            f"({len(generated_files)} files)"
        )
        return output_dir

    def _generate_selftest(self, blueprint: AgencyBlueprint, output_dir: Path) -> Path:
        """Generate a self-test script for the agency."""
        template = self.env.get_template("selftest.py.j2")
        test_content = template.render(
            agency_name=blueprint.name,
            agency_description=blueprint.description,
            expected_teams=len(blueprint.teams),
        )
        test_path = output_dir / "test_agency.py"
        test_path.write_text(test_content, encoding="utf-8")
        logger.info(f"Generated self-test: {test_path}")
        return test_path
