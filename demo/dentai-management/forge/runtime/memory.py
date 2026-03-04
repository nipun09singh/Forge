"""Shared memory store for cross-agent context."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any

from forge.runtime.persistence import MemoryBackend, InMemoryBackend, SQLiteMemoryBackend


@dataclass
class MemoryEntry:
    """A single memory entry."""
    key: str
    value: Any
    author: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tags: list[str] = field(default_factory=list)


class SharedMemory:
    """
    Shared memory store enabling agents to share context.
    
    Supports key-value storage, tagging, and search.
    Thread-safe via asyncio Lock.
    """

    def __init__(self, max_history: int = 10_000) -> None:
        self._store: dict[str, MemoryEntry] = {}
        self._history: list[MemoryEntry] = []
        self._max_history = max_history
        self._lock = asyncio.Lock()
        self._backend: MemoryBackend = InMemoryBackend()

    def __repr__(self) -> str:
        return f"SharedMemory(entries={len(self._store)}, backend={type(self._backend).__name__})"

    @classmethod
    def persistent(cls, db_path: str = "agency_memory.db") -> "SharedMemory":
        """Create a SharedMemory instance backed by SQLite for persistence."""
        instance = cls()
        instance._backend = SQLiteMemoryBackend(db_path)
        return instance

    @classmethod
    def with_backend(cls, backend: MemoryBackend) -> "SharedMemory":
        """Create a SharedMemory instance with a custom backend."""
        instance = cls()
        instance._backend = backend
        return instance

    def store(self, key: str, value: Any, author: str = "", tags: list[str] | None = None) -> None:
        """Store a value (sync version for convenience)."""
        entry = MemoryEntry(key=key, value=value, author=author, tags=tags or [])
        self._store[key] = entry
        self._history.append(entry)
        # Prevent unbounded memory growth
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        self._backend.store(key, value, author, tags)

    async def astore(self, key: str, value: Any, author: str = "", tags: list[str] | None = None) -> None:
        """Store a value (async thread-safe version)."""
        async with self._lock:
            self.store(key, value, author, tags)

    def recall(self, key: str) -> Any | None:
        """Retrieve a value by key."""
        entry = self._store.get(key)
        if entry:
            return entry.value
        # Fall back to persistent backend
        return self._backend.recall(key)

    async def arecall(self, key: str) -> Any | None:
        """Retrieve a value by key (async)."""
        async with self._lock:
            return self.recall(key)

    def search(self, tag: str | None = None, author: str | None = None) -> list[MemoryEntry]:
        """Search memories by tag or author."""
        results = list(self._store.values())
        if tag:
            results = [e for e in results if tag in e.tags]
        if author:
            results = [e for e in results if e.author == author]
        return results

    def get_context_summary(self, max_entries: int = 20) -> str:
        """Get a summary of recent memory for agent context injection."""
        recent = self._history[-max_entries:]
        lines = []
        for entry in recent:
            preview = str(entry.value)[:200]
            lines.append(f"[{entry.author or 'system'}] {entry.key}: {preview}")
        return "\n".join(lines)

    def clear(self) -> None:
        """Clear all memory."""
        self._store.clear()
        self._history.clear()
        self._backend.clear()

    def search_keyword(self, keyword: str, limit: int = 20) -> list[dict]:
        """Search memories by keyword (uses persistent backend)."""
        return self._backend.search(keyword=keyword, limit=limit)
