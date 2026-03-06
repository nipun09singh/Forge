"""Forge Engine — the meta-agency that generates AI agencies."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from forge.core.blueprint import AgencyBlueprint
from forge.core.domain_analyzer import DomainAnalyzer
from forge.core.llm import LLMClient
from forge.generators.agency_generator import AgencyGenerator
from forge.core.archetypes import inject_archetypes
from forge.core.critic import BlueprintCritic, RefinementLoop
from forge.core.quality import BlueprintEvaluator, QualityRubric, format_quality_report

logger = logging.getLogger(__name__)
console = Console()


class ForgeEngine:
    """
    The Forge — a meta-agency that generates complete AI agencies.
    
    The Forge itself operates as a team of internal AI agents:
    - Domain Analyst: Understands the domain
    - Architect: Designs the agency structure
    - Agent Smith: Crafts agent personas
    - Toolmaker: Designs tools
    - Deployer: Packages for deployment
    
    All orchestrated by this engine.
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        output_dir: Path | None = None,
    ):
        self.llm = LLMClient(model=model, api_key=api_key, base_url=base_url)
        self.analyzer = DomainAnalyzer(self.llm)
        self.generator = AgencyGenerator(output_base=output_dir or Path("generated"))
        self.model = self.llm.model
        self.evaluator = BlueprintEvaluator()
        self.critic = BlueprintCritic(self.llm)
        self.refinement_loop = RefinementLoop(
            llm=self.llm,
            evaluator=self.evaluator,
            critic=self.critic,
            max_iterations=10,  # Will iterate up to 10 times for quality
        )
        self._history: list[dict[str, Any]] = []

    async def create_agency(
        self,
        domain_description: str,
        overwrite: bool = False,
        inject_archetypes_flag: bool = True,
    ) -> tuple[AgencyBlueprint, Path]:
        """
        Create a complete AI agency from a domain description.
        
        Returns the blueprint and path to the generated project.
        """
        console.print(Panel(
            f"[bold cyan]🔨 Forge[/bold cyan] — Generating AI Agency\n\n"
            f"[dim]{domain_description[:200]}{'...' if len(domain_description) > 200 else ''}[/dim]",
            title="Forge Engine",
            border_style="cyan",
        ))

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            # Phase 1: Analyze domain and create blueprint
            task = progress.add_task("Analyzing domain and designing agency...", total=None)
            try:
                blueprint = await self.analyzer.analyze(domain_description, model=self.model)
            except Exception as e:
                logger.error(f"Domain analysis failed: {e}. Retrying with simpler prompt...")
                try:
                    # Retry with a simpler approach
                    blueprint = await self.analyzer.analyze(
                        f"Simple agency for: {domain_description[:200]}", model=self.model
                    )
                except Exception as e2:
                    raise RuntimeError(f"Agency generation failed after retry: {e2}") from e
            progress.update(task, description="[green]✓ Blueprint drafted")

            # Phase 2: Inject universal archetypes (optional — founder mode skips this)
            if inject_archetypes_flag:
                progress.update(task, description="Injecting universal agent archetypes...")
                blueprint = inject_archetypes(blueprint)
                progress.update(task, description="[green]✓ Universal archetypes injected")
            else:
                progress.update(task, description="[cyan]⚡ Founder mode: AI decides agents (no archetype injection)")

            # Phase 3: Critique & Refinement Loop — iterate until quality standards are met
            progress.update(task, description="Running critique & refinement loop...")
            blueprint, refinement_history = await self.refinement_loop.refine(
                blueprint=blueprint,
                domain_description=domain_description,
            )
            iterations = len(refinement_history)
            final_score = refinement_history[-1]["combined_score"] if refinement_history else 0
            progress.update(task, description=f"[green]✓ Quality verified ({iterations} iterations, score: {final_score:.0%})")

            # Phase 4: Generate the agency project
            progress.update(task, description="Generating agency code...")
            output_path = self.generator.generate(blueprint, overwrite=overwrite)
            progress.update(task, description="[green]✓ Agency generated")

            # Phase 5: Copy runtime into generated agency
            progress.update(task, description="Packaging runtime...")
            self._package_runtime(output_path)
            progress.update(task, description="[green]✓ Runtime packaged")

            # Phase 6: Validate generated agency
            progress.update(task, description="Validating generated agency...")
            from forge.generators.validator import AgencyValidator
            validator = AgencyValidator()
            validation = validator.validate(output_path)
            if validation.passed:
                progress.update(task, description=f"[green]✓ Validation passed ({validation.files_checked} files checked)")
            else:
                progress.update(task, description=f"[yellow]⚠ Validation: {len(validation.errors)} errors, {len(validation.warnings)} warnings")

        # Summary
        self._print_summary(blueprint, output_path)
        
        # Record in history
        self._history.append({
            "domain": domain_description[:200],
            "agency": blueprint.name,
            "path": str(output_path),
            "agents": len(blueprint.all_agents),
            "teams": len(blueprint.teams),
        })

        return blueprint, output_path

    def _package_runtime(self, output_path: Path) -> None:
        """Copy the Forge runtime into the generated agency."""
        import shutil
        runtime_src = Path(__file__).parent.parent / "runtime"
        runtime_dst = output_path / "forge" / "runtime"

        if runtime_dst.exists():
            shutil.rmtree(runtime_dst)

        # Create forge package in output
        forge_pkg = output_path / "forge"
        forge_pkg.mkdir(exist_ok=True)
        (forge_pkg / "__init__.py").write_text(
            '"""Forge runtime — bundled with generated agency."""\n',
            encoding="utf-8",
        )

        # Copy runtime tree, excluding stale bytecode
        _ignore = shutil.ignore_patterns("__pycache__")
        shutil.copytree(str(runtime_src), str(runtime_dst), ignore=_ignore)
        logger.info(f"Packaged runtime into {runtime_dst}")

        # Ensure integrations sub-package is present
        integrations_dst = runtime_dst / "integrations"
        if not integrations_dst.exists():
            integrations_src = runtime_src / "integrations"
            if integrations_src.exists():
                shutil.copytree(str(integrations_src), str(integrations_dst),
                                ignore=_ignore)
            else:
                integrations_dst.mkdir(exist_ok=True)

        # Guarantee __init__.py chain so imports always resolve
        for init_path in (
            runtime_dst / "__init__.py",
            integrations_dst / "__init__.py",
        ):
            if not init_path.exists():
                init_path.write_text("", encoding="utf-8")
        logger.info(f"Verified __init__.py chain in {forge_pkg}")

    def _print_summary(self, blueprint: AgencyBlueprint, output_path: Path) -> None:
        """Print a summary of the generated agency."""
        lines = []
        lines.append(f"[bold green]✅ Agency Generated Successfully![/bold green]\n")
        lines.append(f"[bold]{blueprint.name}[/bold]")
        lines.append(f"{blueprint.description}\n")
        lines.append(f"📁 Location: [cyan]{output_path}[/cyan]")
        lines.append(f"👥 Teams: {len(blueprint.teams)}")
        lines.append(f"🤖 Agents: {len(blueprint.all_agents)}")
        lines.append(f"🔧 Tools: {len(blueprint.all_tools)}")
        lines.append(f"📋 Workflows: {len(blueprint.workflows)}")
        lines.append(f"🌐 API Endpoints: {len(blueprint.api_endpoints)}")
        lines.append(f"🔄 Quality Iterations: {len(self.refinement_loop._history)}")
        if self.refinement_loop._history:
            final = self.refinement_loop._history[-1]
            lines.append(f"📊 Final Quality Score: {final['combined_score']:.0%}")
        lines.append("")
        lines.append("[bold]Teams:[/bold]")
        for team in blueprint.teams:
            lead_str = f" (lead: {team.lead.name})" if team.lead else ""
            lines.append(f"  • {team.name}{lead_str} — {len(team.agents)} agents")
        lines.append("")
        lines.append("[dim]Next steps:[/dim]")
        lines.append(f"  cd {output_path}")
        lines.append(f"  pip install -r requirements.txt")
        lines.append(f"  export OPENAI_API_KEY='your-key'")
        lines.append(f"  python main.py")

        console.print(Panel("\n".join(lines), title="🏢 Agency Summary", border_style="green"))

    async def list_generated(self) -> list[dict[str, Any]]:
        """List previously generated agencies."""
        agencies = []
        base = self.generator.output_base
        if base.exists():
            for d in base.iterdir():
                if d.is_dir() and (d / "blueprint.json").exists():
                    bp = AgencyBlueprint.model_validate_json(
                        (d / "blueprint.json").read_text(encoding="utf-8")
                    )
                    agencies.append({
                        "name": bp.name,
                        "slug": bp.slug,
                        "path": str(d),
                        "agents": len(bp.all_agents),
                        "teams": len(bp.teams),
                    })
        return agencies
