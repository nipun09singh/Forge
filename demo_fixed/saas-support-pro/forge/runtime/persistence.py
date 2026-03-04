"""Persistent memory backends — SQLite and in-memory stores."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class MemoryBackend(ABC):
    """Abstract base class for memory storage backends."""

    @abstractmethod
    def store(self, key: str, value: Any, author: str = "", tags: list[str] | None = None, session_id: str = "") -> None:
        """Store a value by key."""
        ...

    @abstractmethod
    def recall(self, key: str, session_id: str = "") -> Any | None:
        """Retrieve a value by key."""
        ...

    @abstractmethod
    def search(self, tag: str | None = None, author: str | None = None, keyword: str | None = None, session_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
        """Search memories by tag, author, or keyword."""
        ...

    @abstractmethod
    def list_recent(self, limit: int = 20, session_id: str = "") -> list[dict[str, Any]]:
        """List the most recent memory entries."""
        ...

    @abstractmethod
    def delete(self, key: str, session_id: str = "") -> bool:
        """Delete a memory entry by key."""
        ...

    @abstractmethod
    def clear(self, session_id: str = "") -> None:
        """Clear all memory entries."""
        ...


class InMemoryBackend(MemoryBackend):
    """In-memory backend (dict-based) — backward compatible with existing SharedMemory."""

    MAX_HISTORY = 10_000

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._history: list[dict[str, Any]] = []

    def store(self, key: str, value: Any, author: str = "", tags: list[str] | None = None, session_id: str = "") -> None:
        entry = {
            "key": key,
            "value": value,
            "author": author,
            "tags": tags or [],
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._store[key] = entry
        self._history.append(entry)
        # Prevent unbounded memory growth
        if len(self._history) > self.MAX_HISTORY:
            self._history = self._history[-self.MAX_HISTORY:]

    def recall(self, key: str, session_id: str = "") -> Any | None:
        entry = self._store.get(key)
        return entry["value"] if entry else None

    def search(self, tag: str | None = None, author: str | None = None, keyword: str | None = None, session_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
        results = list(self._store.values())
        if tag:
            results = [e for e in results if tag in e.get("tags", [])]
        if author:
            results = [e for e in results if e.get("author") == author]
        if keyword:
            kw = keyword.lower()
            results = [e for e in results if kw in str(e.get("value", "")).lower() or kw in e.get("key", "").lower()]
        if session_id:
            results = [e for e in results if e.get("session_id") == session_id]
        return results[:limit]

    def list_recent(self, limit: int = 20, session_id: str = "") -> list[dict[str, Any]]:
        items = self._history
        if session_id:
            items = [e for e in items if e.get("session_id") == session_id]
        return items[-limit:]

    def delete(self, key: str, session_id: str = "") -> bool:
        if key in self._store:
            del self._store[key]
            return True
        return False

    def clear(self, session_id: str = "") -> None:
        if session_id:
            keys_to_del = [k for k, v in self._store.items() if v.get("session_id") == session_id]
            for k in keys_to_del:
                del self._store[k]
        else:
            self._store.clear()
            self._history.clear()


class SQLiteMemoryBackend(MemoryBackend):
    """
    SQLite-backed persistent memory.

    Data survives process restarts. Supports keyword search, tag filtering,
    and session isolation.
    """

    def __init__(self, db_path: str = "agency_memory.db") -> None:
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        logger.info(f"SQLite memory initialized at {db_path}")

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                author TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                session_id TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key);
            CREATE INDEX IF NOT EXISTS idx_memories_session ON memories(session_id);
            CREATE INDEX IF NOT EXISTS idx_memories_author ON memories(author);
            CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
        """)
        self._conn.commit()

    def store(self, key: str, value: Any, author: str = "", tags: list[str] | None = None, session_id: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        value_str = json.dumps(value, default=str) if not isinstance(value, str) else value
        tags_str = json.dumps(tags or [])

        # Upsert
        self._conn.execute("""
            INSERT INTO memories (id, key, value, author, tags, session_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                value = excluded.value,
                author = excluded.author,
                tags = excluded.tags,
                updated_at = excluded.updated_at
        """, (f"{session_id}:{key}" if session_id else key, key, value_str, author, tags_str, session_id, now, now))
        self._conn.commit()

    def recall(self, key: str, session_id: str = "") -> Any | None:
        row_id = f"{session_id}:{key}" if session_id else key
        row = self._conn.execute("SELECT value FROM memories WHERE id = ?", (row_id,)).fetchone()
        if not row:
            # Fallback: search by key without session prefix
            row = self._conn.execute("SELECT value FROM memories WHERE key = ? ORDER BY updated_at DESC LIMIT 1", (key,)).fetchone()
        if row:
            try:
                return json.loads(row["value"])
            except (json.JSONDecodeError, TypeError):
                return row["value"]
        return None

    def search(self, tag: str | None = None, author: str | None = None, keyword: str | None = None, session_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
        query = "SELECT * FROM memories WHERE 1=1"
        params: list[Any] = []

        if tag:
            query += " AND tags LIKE ?"
            params.append(f'%"{tag}"%')
        if author:
            query += " AND author = ?"
            params.append(author)
        if keyword:
            query += " AND (value LIKE ? OR key LIKE ?)"
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)

        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def list_recent(self, limit: int = 20, session_id: str = "") -> list[dict[str, Any]]:
        if session_id:
            rows = self._conn.execute(
                "SELECT * FROM memories WHERE session_id = ? ORDER BY updated_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM memories ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def delete(self, key: str, session_id: str = "") -> bool:
        row_id = f"{session_id}:{key}" if session_id else key
        cursor = self._conn.execute("DELETE FROM memories WHERE id = ?", (row_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def clear(self, session_id: str = "") -> None:
        if session_id:
            self._conn.execute("DELETE FROM memories WHERE session_id = ?", (session_id,))
        else:
            self._conn.execute("DELETE FROM memories")
        self._conn.commit()

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        try:
            d["tags"] = json.loads(d.get("tags", "[]"))
        except (json.JSONDecodeError, TypeError):
            d["tags"] = []
        try:
            d["value"] = json.loads(d.get("value", ""))
        except (json.JSONDecodeError, TypeError):
            pass
        return d

    def close(self) -> None:
        """Close the SQLite database connection."""
        self._conn.close()
