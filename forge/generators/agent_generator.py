"""Generates individual agent modules from blueprints."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from forge.core.blueprint import AgentBlueprint

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


def _sanitize_python_name(name: str) -> str:
    """Convert a display name to a valid Python identifier."""
    name = name.lower()
    name = re.sub(r'[^a-z0-9_]', '_', name)
    name = re.sub(r'_+', '_', name)
    return name.strip('_')


class AgentGenerator:
    """Generates Python agent modules from AgentBlueprint."""

    def __init__(self) -> None:
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.filters["pyname"] = _sanitize_python_name

    def generate(self, blueprint: AgentBlueprint, output_dir: Path) -> Path:
        """Generate an agent module file."""
        template = self.env.get_template("agent_module.py.j2")

        # Prepare tool parameters for template
        tools_data = []
        for tool in blueprint.tools:
            tools_data.append({
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "implementation_hint": tool.implementation_hint,
            })

        content = template.render(
            agent_name=blueprint.name,
            title=blueprint.title,
            role=blueprint.role.value,
            system_prompt=blueprint.system_prompt.replace('"""', '\\"\\"\\"'),
            tools=tools_data,
            model=blueprint.model,
            temperature=blueprint.temperature,
            max_iterations=blueprint.max_iterations,
        )

        safe_name = _sanitize_python_name(blueprint.name)
        output_path = output_dir / f"agent_{safe_name}.py"
        output_path.write_text(content, encoding="utf-8")
        logger.info(f"Generated agent module: {output_path}")
        return output_path
