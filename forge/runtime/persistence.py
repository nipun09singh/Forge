"""Persistent memory backends — SQLite and in-memory stores."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Retry settings for transient SQLite failures (e.g. database locked)
_MAX_RETRIES = 3
_RETRY_DELAY = 0.1  # seconds, doubles each retry


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

    def keys(self) -> list[str]:
        """Return all stored keys. Override in subclasses for efficiency."""
        return []

    def count(self) -> int:
        """Return the total number of stored entries."""
        return len(self.keys())


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

    def keys(self) -> list[str]:
        return list(self._store.keys())

    def count(self) -> int:
        return len(self._store)


class SQLiteMemoryBackend(MemoryBackend):
    """
    SQLite-backed persistent memory.

    Data survives process restarts. Supports keyword search, tag filtering,
    and session isolation.
    """

    def __init__(self, db_path: str = "agency_memory.db") -> None:
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._connect()
        self._init_schema()
        logger.info(f"SQLite memory initialized at {db_path}")

    def _connect(self) -> None:
        """Open (or reopen) the SQLite connection."""
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    def _ensure_connection(self) -> sqlite3.Connection:
        """Return a usable connection, reconnecting if necessary."""
        if self._conn is None:
            self._connect()
        try:
            assert self._conn is not None
            self._conn.execute("SELECT 1")
        except (sqlite3.OperationalError, sqlite3.ProgrammingError):
            logger.warning("SQLite connection lost, reconnecting…")
            self._connect()
        assert self._conn is not None
        return self._conn

    def _init_schema(self) -> None:
        conn = self._ensure_connection()
        conn.executescript("""
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
        conn.commit()

    def _execute_with_retry(self, operation: str, func):
        """Execute *func(conn)* with retry logic for transient SQLite errors."""
        last_exc: Exception | None = None
        delay = _RETRY_DELAY
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                conn = self._ensure_connection()
                return func(conn)
            except sqlite3.OperationalError as exc:
                last_exc = exc
                if "locked" in str(exc).lower() and attempt < _MAX_RETRIES:
                    logger.warning(
                        "SQLite %s attempt %d/%d failed (locked), retrying in %.2fs",
                        operation, attempt, _MAX_RETRIES, delay,
                    )
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
        raise last_exc  # type: ignore[misc]  # pragma: no cover

    def store(self, key: str, value: Any, author: str = "", tags: list[str] | None = None, session_id: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        value_str = json.dumps(value, default=str) if not isinstance(value, str) else value
        tags_str = json.dumps(tags or [])
        row_id = f"{session_id}:{key}" if session_id else key

        def _do_store(conn: sqlite3.Connection):
            conn.execute("""
                INSERT INTO memories (id, key, value, author, tags, session_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    value = excluded.value,
                    author = excluded.author,
                    tags = excluded.tags,
                    updated_at = excluded.updated_at
            """, (row_id, key, value_str, author, tags_str, session_id, now, now))
            conn.commit()

        self._execute_with_retry("store", _do_store)

    def recall(self, key: str, session_id: str = "") -> Any | None:
        conn = self._ensure_connection()
        row_id = f"{session_id}:{key}" if session_id else key
        row = conn.execute("SELECT value FROM memories WHERE id = ?", (row_id,)).fetchone()
        if not row:
            row = conn.execute("SELECT value FROM memories WHERE key = ? ORDER BY updated_at DESC LIMIT 1", (key,)).fetchone()
        if row:
            try:
                return json.loads(row["value"])
            except (json.JSONDecodeError, TypeError):
                return row["value"]
        return None

    def search(self, tag: str | None = None, author: str | None = None, keyword: str | None = None, session_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
        conn = self._ensure_connection()
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

        rows = conn.execute(query, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def list_recent(self, limit: int = 20, session_id: str = "") -> list[dict[str, Any]]:
        conn = self._ensure_connection()
        if session_id:
            rows = conn.execute(
                "SELECT * FROM memories WHERE session_id = ? ORDER BY updated_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM memories ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def delete(self, key: str, session_id: str = "") -> bool:
        conn = self._ensure_connection()
        row_id = f"{session_id}:{key}" if session_id else key
        cursor = conn.execute("DELETE FROM memories WHERE id = ?", (row_id,))
        conn.commit()
        return cursor.rowcount > 0

    def clear(self, session_id: str = "") -> None:
        conn = self._ensure_connection()
        if session_id:
            conn.execute("DELETE FROM memories WHERE session_id = ?", (session_id,))
        else:
            conn.execute("DELETE FROM memories")
        conn.commit()

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

    def keys(self) -> list[str]:
        conn = self._ensure_connection()
        rows = conn.execute("SELECT DISTINCT key FROM memories").fetchall()
        return [r["key"] for r in rows]

    def count(self) -> int:
        conn = self._ensure_connection()
        row = conn.execute("SELECT COUNT(*) AS cnt FROM memories").fetchone()
        return row["cnt"] if row else 0

    def close(self) -> None:
        """Close the SQLite database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
