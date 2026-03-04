"""Generates the main agency orchestration file from AgencyBlueprint."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from forge.core.blueprint import AgencyBlueprint

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


def _sanitize_python_name(name: str) -> str:
    """Convert a display name to a valid Python identifier."""
    name = name.lower()
    name = re.sub(r'[^a-z0-9_]', '_', name)
    name = re.sub(r'_+', '_', name)
    return name.strip('_')


class OrchestrationGenerator:
    """Generates the main agency entry point and API server from AgencyBlueprint."""

    def __init__(self) -> None:
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.filters["add_suffix"] = lambda value, suffix: value + suffix
        self.env.filters["pyname"] = _sanitize_python_name

    def generate_main(self, blueprint: AgencyBlueprint, output_dir: Path) -> Path:
        """Generate the main.py agency entry point."""
        template = self.env.get_template("agency_main.py.j2")

        teams_data = []
        for team in blueprint.teams:
            team_data = {
                "name": team.name,
                "safe_name": _sanitize_python_name(team.name),
                "description": team.description,
                "lead": None,
                "agents": [],
            }
            if team.lead:
                team_data["lead"] = {
                    "name": team.lead.name,
                    "role": team.lead.role.value,
                    "system_prompt": team.lead.system_prompt.replace('"""', '\\"\\"\\"'),
                    "model": team.lead.model,
                    "temperature": team.lead.temperature,
                    "tools": [{"name": t.name} for t in team.lead.tools],
                }
            for agent in team.agents:
                team_data["agents"].append({
                    "name": agent.name,
                    "role": agent.role.value,
                    "system_prompt": agent.system_prompt.replace('"""', '\\"\\"\\"'),
                    "model": agent.model,
                    "temperature": agent.temperature,
                    "tools": [{"name": t.name} for t in agent.tools],
                })
            teams_data.append(team_data)

        shared_tools_data = []
        for tool in blueprint.shared_tools:
            shared_tools_data.append({
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            })

        content = template.render(
            agency_name=blueprint.name,
            slug=blueprint.slug,
            description=blueprint.description,
            model=blueprint.model,
            teams=teams_data,
            shared_tools=shared_tools_data,
        )

        output_path = output_dir / "main.py"
        output_path.write_text(content, encoding="utf-8")
        logger.info(f"Generated main.py: {output_path}")
        return output_path

    def generate_api_server(self, blueprint: AgencyBlueprint, output_dir: Path) -> Path:
        """Generate the FastAPI server."""
        template = self.env.get_template("api_server.py.j2")

        content = template.render(
            agency_name=blueprint.name,
            slug=blueprint.slug,
            description=blueprint.description,
            api_endpoints=blueprint.api_endpoints,
        )

        output_path = output_dir / "api_server.py"
        output_path.write_text(content, encoding="utf-8")
        logger.info(f"Generated api_server.py: {output_path}")
        return output_path
