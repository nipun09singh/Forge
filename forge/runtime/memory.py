"""Shared memory store for cross-agent context."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any

from forge.runtime.persistence import MemoryBackend, InMemoryBackend, SQLiteMemoryBackend

logger = logging.getLogger(__name__)


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
        """Store a value (sync version for convenience).

        Writes to the persistent backend *first* so that a backend failure
        never leaves the two stores silently diverged.  If the backend write
        fails the entry is still cached in-memory, but a warning is logged.
        """
        entry = MemoryEntry(key=key, value=value, author=author, tags=tags or [])
        try:
            self._backend.store(key, value, author, tags)
        except Exception as exc:
            logger.error("Memory backend write failed for '%s': %s", key, exc)
        self._store[key] = entry
        self._history.append(entry)
        # Prevent unbounded memory growth
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

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
        """Search memories by tag or author.

        Queries both the in-memory ``_store`` and the persistent
        ``_backend``, merging results and deduplicating by key so that
        entries present in both stores are returned only once (the
        in-memory version wins).
        """
        # 1. Filter in-memory entries
        results = list(self._store.values())
        if tag:
            results = [e for e in results if tag in e.tags]
        if author:
            results = [e for e in results if e.author == author]

        seen_keys = {e.key for e in results}

        # 2. Query persistent backend and merge novel entries
        try:
            backend_rows = self._backend.search(tag=tag, author=author)
            for row in backend_rows:
                key = row.get("key", "")
                if key not in seen_keys:
                    entry = MemoryEntry(
                        key=key,
                        value=row.get("value"),
                        author=row.get("author", ""),
                        timestamp=row.get("created_at", row.get("updated_at", "")),
                        tags=row.get("tags", []),
                    )
                    results.append(entry)
                    seen_keys.add(key)
        except Exception as exc:
            logger.error("search: backend query failed: %s", exc)

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

    def sync(self) -> dict[str, Any]:
        """Reconcile in-memory _store with the persistent backend.

        Writes any _store entries missing from the backend.
        Returns a report of what was synced.
        """
        synced: list[str] = []
        failed: list[str] = []
        backend_keys = set(self._backend.keys())

        for key, entry in self._store.items():
            if key not in backend_keys:
                try:
                    self._backend.store(key, entry.value, entry.author, entry.tags)
                    synced.append(key)
                except Exception as exc:
                    logger.error("sync: failed to write '%s' to backend: %s", key, exc)
                    failed.append(key)

        report: dict[str, Any] = {
            "synced": synced,
            "failed": failed,
            "store_count": len(self._store),
            "backend_count": self._backend.count(),
        }
        if synced:
            logger.info("sync: wrote %d missing entries to backend", len(synced))
        if failed:
            logger.warning("sync: %d entries failed to write", len(failed))
        return report

    def health_check(self) -> dict[str, Any]:
        """Compare _store and _backend, reporting any divergence."""
        store_keys = set(self._store.keys())
        backend_keys = set(self._backend.keys())

        only_in_store = store_keys - backend_keys
        only_in_backend = backend_keys - store_keys

        healthy = not only_in_store and not only_in_backend
        result: dict[str, Any] = {
            "healthy": healthy,
            "store_count": len(store_keys),
            "backend_count": len(backend_keys),
            "only_in_store": sorted(only_in_store),
            "only_in_backend": sorted(only_in_backend),
        }
        if not healthy:
            logger.warning(
                "Memory health check: divergence detected — "
                "%d only in store, %d only in backend",
                len(only_in_store), len(only_in_backend),
            )
        return result
