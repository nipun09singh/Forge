"""Tests for forge.runtime.integrations"""

import json
import os
import tempfile
import pytest

from forge.runtime.integrations import BuiltinToolkit
from forge.runtime.integrations.file_tool import create_file_tool, read_write_file
from forge.runtime.integrations.sql_tool import create_sql_tool, query_database


class TestBuiltinToolkit:
    def test_all_tools(self, tmp_dir):
        tools = BuiltinToolkit.all_tools(sandbox_dir=tmp_dir, db_path=os.path.join(tmp_dir, "t.db"))
        assert len(tools) >= 3
        names = [t.name for t in tools]
        assert "http_request" in names
        assert "read_write_file" in names
        assert "query_database" in names

    def test_tool_names(self):
        names = BuiltinToolkit.get_tool_names()
        assert "http_request" in names
        assert "send_email" in names


class TestFileTool:
    @pytest.mark.asyncio
    async def test_write_and_read(self, tmp_dir):
        os.environ["AGENCY_DATA_DIR"] = tmp_dir
        result = await read_write_file("write", "test.txt", "hello world")
        data = json.loads(result)
        assert data["success"]

        result = await read_write_file("read", "test.txt")
        data = json.loads(result)
        assert data["content"] == "hello world"

    @pytest.mark.asyncio
    async def test_list_files(self, tmp_dir):
        os.environ["AGENCY_DATA_DIR"] = tmp_dir
        await read_write_file("write", "a.txt", "aaa")
        result = await read_write_file("list", ".")
        data = json.loads(result)
        assert len(data["entries"]) >= 1

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, tmp_dir):
        os.environ["AGENCY_DATA_DIR"] = tmp_dir
        result = await read_write_file("read", "../../etc/passwd")
        data = json.loads(result)
        assert "error" in data or "denied" in str(data).lower()


class TestSQLTool:
    @pytest.mark.asyncio
    async def test_create_and_query(self, tmp_dir):
        db = os.path.join(tmp_dir, "test.db")
        await query_database("CREATE TABLE users (id INTEGER, name TEXT)", db_path=db)
        await query_database("INSERT INTO users VALUES (1, 'Alice')", db_path=db)
        result = await query_database("SELECT * FROM users", db_path=db)
        data = json.loads(result)
        assert data["count"] == 1
        assert data["rows"][0]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_destructive_blocked(self, tmp_dir):
        db = os.path.join(tmp_dir, "test.db")
        result = await query_database("DROP TABLE users", db_path=db)
        data = json.loads(result)
        assert "error" in data
        assert "blocked" in data["error"].lower() or "not allowed" in data["error"].lower()
