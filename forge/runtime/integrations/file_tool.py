"""File Tool — reads and writes real files in a sandboxed directory."""

from __future__ import annotations

import json
import os
from pathlib import Path
from forge.runtime.tools import Tool, ToolParameter

def create_file_tool(sandbox_dir: str = "./data") -> Tool:
    _sandbox = Path(sandbox_dir)
    _sandbox.mkdir(parents=True, exist_ok=True)

    async def read_write_file(action: str, path: str, content: str = "") -> str:
        """Read, write, append, or list files in the sandboxed data directory."""
        sandbox = Path(os.getenv("AGENCY_DATA_DIR", str(_sandbox))).resolve()
        sandbox.mkdir(parents=True, exist_ok=True)

        # Security: check unresolved path first (prevents path traversal)
        unresolved = sandbox / path
        try:
            unresolved.relative_to(sandbox)
        except ValueError:
            return json.dumps({"error": "Access denied: path is outside sandbox directory."})
        # Then check resolved path (follows symlinks — prevents symlink traversal)
        target = unresolved.resolve()
        try:
            target.relative_to(sandbox.resolve())
        except ValueError:
            return json.dumps({"error": "Access denied: symlink points outside sandbox directory."})

        try:
            if action == "read":
                if not target.exists():
                    return json.dumps({"error": f"File not found: {path}"})
                text = target.read_text(encoding="utf-8", errors="replace")
                return json.dumps({"path": path, "content": text[:10000], "size": target.stat().st_size, "truncated": len(text) > 10000})

            elif action == "write":
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                return json.dumps({"success": True, "path": path, "bytes_written": len(content.encode())})

            elif action == "append":
                target.parent.mkdir(parents=True, exist_ok=True)
                with open(target, "a", encoding="utf-8") as f:
                    f.write(content)
                return json.dumps({"success": True, "path": path, "bytes_appended": len(content.encode())})

            elif action == "list":
                if target.is_dir():
                    entries = []
                    for entry in sorted(target.iterdir()):
                        entries.append({
                            "name": entry.name,
                            "type": "dir" if entry.is_dir() else "file",
                            "size": entry.stat().st_size if entry.is_file() else 0,
                        })
                    return json.dumps({"path": path, "entries": entries[:200]})
                return json.dumps({"error": f"Not a directory: {path}"})

            elif action == "delete":
                if target.exists():
                    target.unlink()
                    return json.dumps({"success": True, "path": path})
                return json.dumps({"error": f"File not found: {path}"})

            else:
                return json.dumps({"error": f"Unknown action: {action}. Use: read, write, append, list, delete"})

        except Exception as e:
            return json.dumps({"error": str(e)})

    return Tool(
        name="read_write_file",
        description="Read, write, append, list, or delete files in the agency's data directory. All paths are sandboxed.",
        parameters=[
            ToolParameter(name="action", type="string", description="Action: read, write, append, list, delete"),
            ToolParameter(name="path", type="string", description="File path relative to data directory"),
            ToolParameter(name="content", type="string", description="Content to write (for write/append actions)", required=False),
        ],
        _fn=read_write_file,
    )
