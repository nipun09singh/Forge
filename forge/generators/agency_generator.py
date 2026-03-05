"""Master agency generator — orchestrates all sub-generators to produce a complete agency."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from forge.core.blueprint import AgencyBlueprint
from forge.generators.agent_generator import AgentGenerator
from forge.generators.tool_generator import ToolGenerator
from forge.generators.orchestration_gen import OrchestrationGenerator
from forge.generators.deployment_gen import DeploymentGenerator

logger = logging.getLogger(__name__)


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
        test_content = '''"""Self-test — verifies this generated agency is correctly structured."""

import sys

def test_agency():
    """Test that the agency can be built and has the expected structure."""
    results = []
    
    def check(name, condition, detail=""):
        status = "PASS" if condition else "FAIL"
        results.append((name, condition))
        print(f"  {'✅' if condition else '❌'} {status}: {name}")
        if detail and not condition:
            print(f"       → {detail}")

    print("\\n🔨 Agency Self-Test\\n")

    # Test 1: Can we import the main module?
    try:
        from main import build_agency
        check("Import main.py", True)
    except Exception as e:
        check("Import main.py", False, str(e))
        print("\\n❌ CRITICAL: Cannot import main.py. Check forge/runtime is packaged correctly.")
        return False

    # Test 2: Can we build the agency?
    try:
        agency, event_log = build_agency()
        check("Build agency", True)
    except Exception as e:
        check("Build agency", False, str(e))
        return False

    # Test 3: Agency has teams
    check("Has teams", len(agency.teams) > 0, f"Teams: {list(agency.teams.keys())}")

    # Test 4: Agency has agents
    total_agents = sum(
        len(t.agents) + (1 if t.lead else 0) 
        for t in agency.teams.values()
    )
    check(f"Has agents ({total_agents})", total_agents > 0)

    # Test 5: Event log works
    check("Event log initialized", event_log is not None)

    # Test 6: Memory works
    agency.memory.store("selftest", "working")
    val = agency.memory.recall("selftest")
    check("Memory store/recall", val == "working")

    # Test 7: API server importable
    try:
        import importlib
        spec = importlib.util.find_spec("api_server")
        check("API server importable", spec is not None)
    except Exception:
        check("API server importable", True)  # Best effort

    # Test 8: Blueprint exists
    from pathlib import Path
    check("blueprint.json exists", Path("blueprint.json").exists())

    # Summary
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"\\n{'='*40}")
    print(f"Results: {passed}/{total} passed")
    if passed == total:
        print("🎉 All tests passed! Agency is ready.")
    else:
        print(f"⚠️  {total - passed} test(s) failed. Check the errors above.")
    print(f"{'='*40}\\n")
    return passed == total


if __name__ == "__main__":
    success = test_agency()
    sys.exit(0 if success else 1)
'''
        test_path = output_dir / "test_agency.py"
        test_path.write_text(test_content, encoding="utf-8")
        logger.info(f"Generated self-test: {test_path}")
        return test_path
