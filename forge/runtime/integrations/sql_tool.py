"""SQL Tool — runs real SQL queries against SQLite databases."""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any
from forge.runtime.tools import Tool, ToolParameter

_DB_PATH = "./data/agency.db"


async def query_database(query: str, db_path: str = "") -> str:
    """Execute a SQL query against a SQLite database."""
    path = db_path or os.getenv("AGENCY_DB_PATH", _DB_PATH)

    # Validate db_path is not accessing sensitive system locations
    abs_path = os.path.abspath(path)
    blocked_prefixes = ["/etc", "/var", "/usr", "/sys", "/proc", "C:\\Windows", "C:\\System"]
    for prefix in blocked_prefixes:
        if abs_path.lower().startswith(prefix.lower()):
            return json.dumps({"error": f"Database path in system directory is blocked: {prefix}"})

    # Safety: block destructive and dangerous operations
    query_upper = query.strip().upper()
    blocked_prefixes_sql = ("DROP", "TRUNCATE", "ALTER", "ATTACH", "DETACH")
    if any(query_upper.startswith(cmd) for cmd in blocked_prefixes_sql):
        return json.dumps({"error": "Destructive operations (DROP, TRUNCATE, ALTER, ATTACH, DETACH) are blocked for safety."})
    # Block DELETE without WHERE clause (mass deletion)
    if query_upper.startswith("DELETE") and "WHERE" not in query_upper:
        return json.dumps({"error": "DELETE without WHERE clause is blocked for safety. Use WHERE to specify rows."})
    # Block dangerous SQLite functions
    if "LOAD_EXTENSION" in query_upper:
        return json.dumps({"error": "load_extension is blocked for security."})

    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA trusted_schema = OFF")
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(query)

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


def create_sql_tool(db_path: str = "") -> Tool:
    if db_path:
        global _DB_PATH
        _DB_PATH = db_path
    return Tool(
        name="query_database",
        description="Execute SQL queries against a SQLite database. Supports SELECT, INSERT, UPDATE, DELETE, CREATE TABLE. DROP/TRUNCATE/ALTER are blocked.",
        parameters=[
            ToolParameter(name="query", type="string", description="The SQL query to execute"),
            ToolParameter(name="db_path", type="string", description="Optional path to database file", required=False),
        ],
        _fn=query_database,
    )
