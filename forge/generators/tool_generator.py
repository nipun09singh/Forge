"""Generates custom tool modules from blueprints, with built-in tool detection."""

from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from forge.core.blueprint import ToolBlueprint

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

# Map of tool names to their built-in integration module
BUILTIN_TOOL_MAP = {
    "http_request": "from forge.runtime.integrations.http_tool import create_http_tool\n\n{name}_tool = create_http_tool()",
    "send_email": "from forge.runtime.integrations.email_tool import create_email_tool\n\n{name}_tool = create_email_tool()",
    "query_database": "from forge.runtime.integrations.sql_tool import create_sql_tool\n\n{name}_tool = create_sql_tool()",
    "read_write_file": "from forge.runtime.integrations.file_tool import create_file_tool\n\n{name}_tool = create_file_tool()",
    "send_webhook": "from forge.runtime.integrations.webhook_tool import create_webhook_tool\n\n{name}_tool = create_webhook_tool()",
    "run_command": "from forge.runtime.integrations.command_tool import create_command_tool\n\n{name}_tool = create_command_tool()",
    "git_operation": "from forge.runtime.integrations.git_tool import create_git_tool\n\n{name}_tool = create_git_tool()",
    "browse_web": "from forge.runtime.integrations.browser_tool import create_browser_tool\n\n{name}_tool = create_browser_tool()",
    "web_search": "from forge.runtime.integrations.search_tool import create_search_tool\n\n{name}_tool = create_search_tool()",
    "send_sms": "from forge.runtime.integrations.twilio_tool import create_twilio_tool\n\n{name}_tool = create_twilio_tool()",
    "stripe_payment": "from forge.runtime.integrations.stripe_tool import create_stripe_tool\n\n{name}_tool = create_stripe_tool()",
    "calendar": "from forge.runtime.integrations.calendar_tool import create_calendar_tool\n\n{name}_tool = create_calendar_tool()",
}

# Exact matching: known aliases → built-in tools
BUILTIN_PATTERN_MAP = {
    "http_request": "http_request",
    "make_http": "http_request",
    "api_request": "http_request",
    "send_email": "send_email",
    "email_send": "send_email",
    "query_database": "query_database",
    "query_db": "query_database",
    "sql_query": "query_database",
    "database_query": "query_database",
    "read_write_file": "read_write_file",
    "file_read": "read_write_file",
    "file_write": "read_write_file",
    "send_webhook": "send_webhook",
    "webhook_send": "send_webhook",
    "run_command": "run_command",
    "execute_command": "run_command",
    "shell_command": "run_command",
    "run_script": "run_command",
    "exec_command": "run_command",
    "git_operation": "git_operation",
    "git": "git_operation",
    "version_control": "git_operation",
    "browse_web": "browse_web",
    "browse_url": "browse_web",
    "fetch_webpage": "browse_web",
    "web_search": "web_search",
    "read_url": "browse_web",
    "search_web": "web_search",
    "internet_search": "web_search",
    "send_sms": "send_sms",
    "sms": "send_sms",
    "text_message": "send_sms",
    "twilio": "send_sms",
    "stripe_payment": "stripe_payment",
    "payment": "stripe_payment",
    "charge": "stripe_payment",
    "billing": "stripe_payment",
    "calendar": "calendar",
    "schedule": "calendar",
    "booking": "calendar",
    "appointment": "calendar",
}


class ToolGenerator:
    """Generates Python tool modules from ToolBlueprint, using built-in integrations when possible."""

    def __init__(self) -> None:
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def _detect_builtin(self, name: str) -> str | None:
        """Check if a tool name matches a built-in integration."""
        if name in BUILTIN_TOOL_MAP:
            return name
        if name in BUILTIN_PATTERN_MAP:
            return BUILTIN_PATTERN_MAP[name]
        return None

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """Sanitize a blueprint name for use as a Python identifier and filename."""
        import re
        # Strip anything that's not alphanumeric or underscore
        safe = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        safe = re.sub(r'_+', '_', safe).strip('_')
        if not safe or not safe[0].isalpha():
            safe = "tool_" + safe
        return safe

    def generate(self, blueprint: ToolBlueprint, output_dir: Path) -> Path:
        """Generate a tool module file. Uses built-in integration if available."""
        builtin = self._detect_builtin(blueprint.name)

        # Sanitize name for safe code generation
        safe_name = self._sanitize_name(blueprint.name)
        # Sanitize description — escape quotes for use in f-strings
        safe_desc = blueprint.description.replace('"', '\\"').replace('\n', ' ')[:200]

        if builtin and builtin in BUILTIN_TOOL_MAP:
            # Generate a module that imports from built-in integrations
            content = (
                f'"""Tool: {safe_name} — powered by Forge built-in integration."""\n\n'
                f'{BUILTIN_TOOL_MAP[builtin].format(name=safe_name)}\n'
            )
            logger.info(f"Using built-in integration for tool: {blueprint.name} → {builtin}")
        else:
            # Domain-specific tool: generate a functional mock-backed tool
            # If a backend_ref is provided, try importing the real implementation
            # and fall back to mock if unavailable.
            # Serialize parameters as a Python literal (not JSON — booleans
            # must be True/False, not true/false)
            params_literal = repr(
                [{"name": self._sanitize_name(p.get("name", "arg")),
                  "type": p.get("type", "string"),
                  "description": p.get("description", p.get("name", ""))[:100],
                  "required": p.get("required", True)}
                 for p in blueprint.parameters]
            )
            param_lines = [
                f'        ToolParameter(name="{self._sanitize_name(p.get("name", "arg"))}", '
                f'type="{p.get("type", "string")}", '
                f'description="{p.get("description", p.get("name", "")).replace(chr(34), chr(92) + chr(34))[:100]}", '
                f'required={p.get("required", True)}),'
                for p in blueprint.parameters
            ]

            if blueprint.backend_ref:
                # Generate code that tries the real backend, falls back to mock
                ref_module, _, ref_attr = blueprint.backend_ref.rpartition(".")
                lines = [
                    f'"""Domain tool: {safe_name}',
                    f'',
                    f'{safe_desc}',
                    f'"""',
                    f'',
                    f'import logging',
                    f'',
                    f'from forge.runtime.tools import Tool, ToolParameter',
                    f'',
                    f'_logger = logging.getLogger(__name__)',
                    f'',
                    f'try:',
                    f'    from {ref_module} import {ref_attr} as _real_fn',
                    f'    {safe_name} = _real_fn',
                    f'except ImportError:',
                    f'    from forge.runtime.integrations.mock_backends import create_mock_tool_function',
                    f'    {safe_name} = create_mock_tool_function(',
                    f'        "{safe_name}",',
                    f'        "{safe_desc}",',
                    f'        {params_literal},',
                    f'    )',
                    f'    _logger.warning("Real backend not available for {safe_name}, using mock")',
                    f'',
                    f'',
                    f'{safe_name}_tool = Tool(',
                    f'    name="{safe_name}",',
                    f'    description="{safe_desc}",',
                    f'    parameters=[',
                    *param_lines,
                    f'    ],',
                    f'    _fn={safe_name},',
                    f')',
                    f'',
                ]
                logger.info(f"Generated domain tool (backend_ref={blueprint.backend_ref}): {safe_name}")
            else:
                lines = [
                    f'"""Domain tool: {safe_name}',
                    f'',
                    f'{safe_desc}',
                    f'"""',
                    f'',
                    f'from forge.runtime.tools import Tool, ToolParameter',
                    f'from forge.runtime.integrations.mock_backends import create_mock_tool_function',
                    f'',
                    f'',
                    f'# Create functional mock tool instead of stub',
                    f'{safe_name} = create_mock_tool_function(',
                    f'    "{safe_name}",',
                    f'    "{safe_desc}",',
                    f'    {params_literal},',
                    f')',
                    f'',
                    f'',
                    f'{safe_name}_tool = Tool(',
                    f'    name="{safe_name}",',
                    f'    description="{safe_desc}",',
                    f'    parameters=[',
                    *param_lines,
                    f'    ],',
                    f'    _fn={safe_name},',
                    f')',
                    f'',
                ]
                logger.info(f"Generated domain tool (mock-backed): {safe_name}")

            content = "\n".join(lines)

        output_path = output_dir / f"tool_{self._sanitize_name(blueprint.name)}.py"
        output_path.write_text(content, encoding="utf-8")
        return output_path

    def generate_all(self, blueprints: list[ToolBlueprint], output_dir: Path) -> list[Path]:
        """Generate all tool modules."""
        paths = []
        seen = set()
        for bp in blueprints:
            if bp.name not in seen:
                seen.add(bp.name)
                paths.append(self.generate(bp, output_dir))
        return paths
