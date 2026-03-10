"""SQL Tool — runs real SQL queries against SQLite databases."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Any, TYPE_CHECKING
from forge.runtime.tools import Tool, ToolParameter
from forge.runtime.guardrails import SqlSanitizer

if TYPE_CHECKING:
    from forge.runtime.policies import SecurityPolicy

logger = logging.getLogger(__name__)

_DB_PATH = "./data/agency.db"
# Allow CREATE TABLE for the sql_tool (needed for schema setup)
# but keep DROP/ALTER/TRUNCATE blocked
_sanitizer = SqlSanitizer(
    allowed_query_types={"SELECT", "INSERT", "UPDATE", "DELETE", "WITH", "CREATE"},
    blocked_statements={"DROP", "ALTER", "TRUNCATE", "EXEC", "EXECUTE",
                        "GRANT", "REVOKE", "ATTACH", "DETACH", "PRAGMA", "VACUUM",
                        "RENAME"},
)


async def query_database(query: str, db_path: str = "") -> str:
    """Execute a SQL query against a SQLite database."""
    path = db_path or os.getenv("AGENCY_DB_PATH", _DB_PATH)

    # Validate db_path is not accessing sensitive system locations
    abs_path = os.path.abspath(path)
    blocked_prefixes = ["/etc", "/var", "/usr", "/sys", "/proc", "C:\\Windows", "C:\\System"]
    for prefix in blocked_prefixes:
        if abs_path.lower().startswith(prefix.lower()):
            return json.dumps({"error": f"Database path in system directory is blocked: {prefix}"})

    # --- SQL validation via SqlSanitizer (defense-in-depth) ---
    cleaned = _sanitizer.sanitize(query)

    violation = _sanitizer.validate(cleaned)
    if violation is not None:
        if violation.severity == "block":
            return json.dumps({"error": violation.description})
        logger.warning("SQL guardrail warning: %s", violation.description)

    violation = _sanitizer.is_parameterized(cleaned)
    if violation is not None:
        if violation.severity == "block":
            return json.dumps({"error": violation.description})
        logger.warning("SQL guardrail warning: %s", violation.description)

    query_upper = cleaned.upper()

    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA trusted_schema = OFF")
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(cleaned)

        if query_upper.startswith("SELECT") or query_upper.startswith("WITH") or query_upper.startswith("PRAGMA"):
            rows = cursor.fetchall()
            results = [dict(row) for row in rows[:100]]  # Limit to 100 rows
            conn.close()
            return json.dumps({"rows": results, "count": len(results), "truncated": len(rows) > 100}, indent=2, default=str)
        else:
            conn.commit()
            affected = cursor.rowcount
            conn.close()
            return json.dumps({"success": True, "rows_affected": affected})
    except Exception as e:
        return json.dumps({"error": str(e)})


def create_sql_tool(db_path: str = "", policy: "SecurityPolicy | None" = None) -> Tool:
    if db_path:
        global _DB_PATH
        _DB_PATH = db_path
    if policy is not None:
        global _sanitizer
        _sanitizer = SqlSanitizer(policy=policy)
    return Tool(
        name="query_database",
        description="Execute SQL queries against a SQLite database. Supports SELECT, INSERT, UPDATE, DELETE, CREATE TABLE. DROP/TRUNCATE/ALTER are blocked.",
        parameters=[
            ToolParameter(name="query", type="string", description="The SQL query to execute"),
            ToolParameter(name="db_path", type="string", description="Optional path to database file", required=False),
        ],
        _fn=query_database,
    )
