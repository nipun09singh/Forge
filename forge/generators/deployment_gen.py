"""Generates deployment configuration files (Docker, requirements, README)."""

from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from forge.core.blueprint import AgencyBlueprint

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


class DeploymentGenerator:
    """Generates deployment files: Dockerfile, docker-compose, requirements, README."""

    def __init__(self) -> None:
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def generate_all(self, blueprint: AgencyBlueprint, output_dir: Path) -> list[Path]:
        """Generate all deployment files."""
        paths = []
        paths.append(self._generate_dockerfile(blueprint, output_dir))
        paths.append(self._generate_docker_compose(blueprint, output_dir))
        paths.append(self._generate_requirements(blueprint, output_dir))
        paths.append(self._generate_readme(blueprint, output_dir))
        return paths

    def _generate_dockerfile(self, blueprint: AgencyBlueprint, output_dir: Path) -> Path:
        template = self.env.get_template("dockerfile.j2")
        content = template.render()
        path = output_dir / "Dockerfile"
        path.write_text(content, encoding="utf-8")
        logger.info(f"Generated Dockerfile: {path}")
        return path

    def _generate_docker_compose(self, blueprint: AgencyBlueprint, output_dir: Path) -> Path:
        template = self.env.get_template("docker_compose.yml.j2")
        content = template.render(
            slug=blueprint.slug,
            model=blueprint.model,
            env_vars=blueprint.environment_variables,
        )
        path = output_dir / "docker-compose.yml"
        path.write_text(content, encoding="utf-8")
        logger.info(f"Generated docker-compose.yml: {path}")
        return path

    def _generate_requirements(self, blueprint: AgencyBlueprint, output_dir: Path) -> Path:
        template = self.env.get_template("requirements.txt.j2")
        content = template.render(agency_name=blueprint.name)
        path = output_dir / "requirements.txt"
        path.write_text(content, encoding="utf-8")
        logger.info(f"Generated requirements.txt: {path}")
        return path

    def _generate_readme(self, blueprint: AgencyBlueprint, output_dir: Path) -> Path:
        template = self.env.get_template("readme.md.j2")
        content = template.render(
            agency_name=blueprint.name,
            description=blueprint.description,
            domain=blueprint.domain,
            model=blueprint.model,
            teams=blueprint.teams,
            api_endpoints=blueprint.api_endpoints,
            env_vars=blueprint.environment_variables,
        )
        path = output_dir / "README.md"
        path.write_text(content, encoding="utf-8")
        logger.info(f"Generated README.md: {path}")
        return path
