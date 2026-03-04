"""Built-in tool integrations — real working tools for Forge agencies."""

from forge.runtime.integrations.http_tool import create_http_tool
from forge.runtime.integrations.email_tool import create_email_tool
from forge.runtime.integrations.sql_tool import create_sql_tool
from forge.runtime.integrations.file_tool import create_file_tool
from forge.runtime.integrations.webhook_tool import create_webhook_tool
from forge.runtime.tools import Tool


class BuiltinToolkit:
    """
    Registry of all built-in tool integrations.

    These are REAL, working tools — not stubs. They make actual HTTP requests,
    send real emails, query real databases, and read/write real files.
    """

    @staticmethod
    def all_tools(
        sandbox_dir: str = "./data",
        db_path: str = "./data/agency.db",
        smtp_host: str | None = None,
    ) -> list[Tool]:
        """Get all built-in tools."""
        tools = [
            create_http_tool(),
            create_file_tool(sandbox_dir=sandbox_dir),
            create_sql_tool(db_path=db_path),
        ]
        if smtp_host:
            tools.append(create_email_tool(smtp_host=smtp_host))
        tools.append(create_webhook_tool())
        return tools

    @staticmethod
    def get_tool_names() -> list[str]:
        """Get names of all available built-in tools."""
        return ["http_request", "send_email", "query_database", "read_write_file", "send_webhook"]
