"""Tests for forge.runtime.memory and persistence"""

import asyncio
import os
import tempfile
import logging
from unittest.mock import MagicMock, patch
import pytest
from forge.runtime.memory import SharedMemory, MemoryEntry
from forge.runtime.persistence import InMemoryBackend, SQLiteMemoryBackend


class TestSharedMemory:
    def test_store_and_recall(self):
        mem = SharedMemory()
        mem.store("key1", "value1")
        assert mem.recall("key1") == "value1"

    def test_recall_missing(self):
        mem = SharedMemory()
        assert mem.recall("nonexistent") is None

    def test_search_by_tag(self):
        mem = SharedMemory()
        mem.store("k1", "v1", tags=["important"])
        mem.store("k2", "v2", tags=["other"])
        results = mem.search(tag="important")
        assert len(results) == 1

    def test_search_by_author(self):
        mem = SharedMemory()
        mem.store("k1", "v1", author="alice")
        mem.store("k2", "v2", author="bob")
        results = mem.search(author="alice")
        assert len(results) == 1

    def test_context_summary(self):
        mem = SharedMemory()
        mem.store("k1", "hello world", author="test")
        summary = mem.get_context_summary()
        assert "hello world" in summary

    def test_clear(self):
        mem = SharedMemory()
        mem.store("k1", "v1")
        mem.clear()
        assert mem.recall("k1") is None


class TestSearchPersistence:
    """search() should query the persistent backend, not just _store."""

    def test_search_finds_backend_entries_after_store_cleared(self, tmp_dir):
        db_path = os.path.join(tmp_dir, "search_persist.db")
        mem = SharedMemory.persistent(db_path)
        mem.store("k1", "v1", author="alice", tags=["important"])
        mem.store("k2", "v2", author="bob", tags=["trivial"])

        # Clear the in-memory cache — backend still has data
        mem._store.clear()
        assert mem._store == {}

        results = mem.search()
        assert len(results) == 2

    def test_search_by_tag_from_backend(self, tmp_dir):
        db_path = os.path.join(tmp_dir, "search_tag.db")
        mem = SharedMemory.persistent(db_path)
        mem.store("k1", "v1", tags=["important"])
        mem.store("k2", "v2", tags=["trivial"])

        mem._store.clear()
        results = mem.search(tag="important")
        assert len(results) == 1
        assert results[0].key == "k1"

    def test_search_by_author_from_backend(self, tmp_dir):
        db_path = os.path.join(tmp_dir, "search_author.db")
        mem = SharedMemory.persistent(db_path)
        mem.store("k1", "v1", author="alice")
        mem.store("k2", "v2", author="bob")

        mem._store.clear()
        results = mem.search(author="alice")
        assert len(results) == 1
        assert results[0].key == "k1"

    def test_no_duplicates_when_in_both_stores(self, tmp_dir):
        db_path = os.path.join(tmp_dir, "search_dedup.db")
        mem = SharedMemory.persistent(db_path)
        mem.store("k1", "v1", author="alice", tags=["important"])
        mem.store("k2", "v2", author="bob", tags=["trivial"])

        # _store and backend both have the entries — no duplicates expected
        results = mem.search()
        keys = [r.key for r in results]
        assert sorted(keys) == ["k1", "k2"]

    def test_search_merges_store_and_backend(self, tmp_dir):
        db_path = os.path.join(tmp_dir, "search_merge.db")
        mem = SharedMemory.persistent(db_path)
        mem.store("k1", "v1", author="alice", tags=["t"])

        # Add an entry only in _store (bypass backend)
        mem._store["k2"] = MemoryEntry(key="k2", value="v2", author="alice", tags=["t"])

        # Add an entry only in backend (bypass _store)
        mem._backend.store("k3", "v3", author="alice", tags=["t"])

        results = mem.search(author="alice", tag="t")
        keys = sorted(r.key for r in results)
        assert keys == ["k1", "k2", "k3"]

    def test_search_survives_new_instance(self, tmp_dir):
        """After restart (new SharedMemory, same db), search still works."""
        db_path = os.path.join(tmp_dir, "search_restart.db")
        mem1 = SharedMemory.persistent(db_path)
        mem1.store("k1", "v1", author="alice", tags=["important"])

        # Simulate restart
        mem2 = SharedMemory.persistent(db_path)
        results = mem2.search(tag="important")
        assert len(results) == 1
        assert results[0].key == "k1"


class TestPersistentMemory:
    def test_sqlite_store_recall(self, tmp_dir):
        db_path = os.path.join(tmp_dir, "test.db")
        mem = SharedMemory.persistent(db_path)
        mem.store("key1", "persistent_value", author="test")
        assert mem.recall("key1") == "persistent_value"

    def test_sqlite_survives_new_instance(self, tmp_dir):
        db_path = os.path.join(tmp_dir, "test.db")
        mem1 = SharedMemory.persistent(db_path)
        mem1.store("key1", "survive_this")
        # New instance, same db
        mem2 = SharedMemory.persistent(db_path)
        result = mem2.recall("key1")
        assert result is not None

    def test_sqlite_keyword_search(self, tmp_dir):
        db_path = os.path.join(tmp_dir, "test.db")
        mem = SharedMemory.persistent(db_path)
        mem.store("note1", "The customer is happy")
        mem.store("note2", "The server is down")
        results = mem.search_keyword("customer")
        assert len(results) >= 1


class TestInMemoryBackend:
    def test_store_recall(self):
        backend = InMemoryBackend()
        backend.store("k", "v")
        assert backend.recall("k") == "v"

    def test_search(self):
        backend = InMemoryBackend()
        backend.store("k1", "hello world", tags=["greet"])
        results = backend.search(tag="greet")
        assert len(results) == 1

    def test_delete(self):
        backend = InMemoryBackend()
        backend.store("k", "v")
        assert backend.delete("k")
        assert backend.recall("k") is None

    def test_clear(self):
        backend = InMemoryBackend()
        backend.store("k1", "v1")
        backend.store("k2", "v2")
        backend.clear()
        assert backend.recall("k1") is None


class TestSQLiteBackend:
    def test_store_recall(self, tmp_dir):
        db = SQLiteMemoryBackend(os.path.join(tmp_dir, "t.db"))
        db.store("k", "v")
        assert db.recall("k") == "v"
        db.close()

    def test_search_keyword(self, tmp_dir):
        db = SQLiteMemoryBackend(os.path.join(tmp_dir, "t.db"))
        db.store("doc1", "machine learning is great")
        db.store("doc2", "databases are useful")
        results = db.search(keyword="machine")
        assert len(results) >= 1
        db.close()

    def test_list_recent(self, tmp_dir):
        db = SQLiteMemoryBackend(os.path.join(tmp_dir, "t.db"))
        db.store("a", "1")
        db.store("b", "2")
        recent = db.list_recent(limit=5)
        assert len(recent) == 2
        db.close()

    def test_keys_and_count(self, tmp_dir):
        db = SQLiteMemoryBackend(os.path.join(tmp_dir, "t.db"))
        db.store("x", "1")
        db.store("y", "2")
        assert set(db.keys()) == {"x", "y"}
        assert db.count() == 2
        db.close()

    def test_reconnect_after_close(self, tmp_dir):
        db = SQLiteMemoryBackend(os.path.join(tmp_dir, "t.db"))
        db.store("k", "v")
        db.close()
        # _ensure_connection should reconnect transparently
        assert db.recall("k") == "v"
        db.close()


class TestBackendFailureHandling:
    """Verify SharedMemory behaves correctly when the backend fails."""

    def test_store_logs_warning_on_backend_failure(self, caplog):
        """Backend failure is logged but doesn't crash."""
        backend = MagicMock(spec=InMemoryBackend)
        backend.store.side_effect = RuntimeError("disk full")
        backend.keys.return_value = []
        backend.count.return_value = 0

        mem = SharedMemory.with_backend(backend)
        with caplog.at_level(logging.ERROR):
            mem.store("k1", "v1")
        assert "backend write failed" in caplog.text.lower()

    def test_data_available_from_store_after_backend_failure(self):
        """Even if backend fails, the value is cached in _store."""
        backend = MagicMock(spec=InMemoryBackend)
        backend.store.side_effect = RuntimeError("oops")

        mem = SharedMemory.with_backend(backend)
        mem.store("k1", "val")
        assert mem.recall("k1") == "val"


class TestSync:
    """Tests for SharedMemory.sync()."""

    def test_sync_reconciles_diverged_stores(self, tmp_dir):
        db_path = os.path.join(tmp_dir, "sync.db")
        mem = SharedMemory.persistent(db_path)

        # Write two entries normally
        mem.store("a", "1")
        mem.store("b", "2")

        # Manually remove one from the backend to simulate divergence
        mem._backend.delete("b")
        health = mem.health_check()
        assert not health["healthy"]
        assert "b" in health["only_in_store"]

        # sync should push 'b' back to the backend
        report = mem.sync()
        assert "b" in report["synced"]
        assert report["store_count"] == report["backend_count"]

    def test_sync_reports_failures(self):
        backend = MagicMock(spec=InMemoryBackend)
        backend.keys.return_value = []
        backend.count.return_value = 0
        backend.store.side_effect = RuntimeError("fail")

        mem = SharedMemory.with_backend(backend)
        # Directly inject an entry into _store (bypass backend)
        from forge.runtime.memory import MemoryEntry
        mem._store["orphan"] = MemoryEntry(key="orphan", value="v")

        report = mem.sync()
        assert "orphan" in report["failed"]


class TestHealthCheck:
    """Tests for SharedMemory.health_check()."""

    def test_healthy_when_in_sync(self, tmp_dir):
        db_path = os.path.join(tmp_dir, "hc.db")
        mem = SharedMemory.persistent(db_path)
        mem.store("x", "1")
        result = mem.health_check()
        assert result["healthy"]
        assert result["store_count"] == result["backend_count"]

    def test_detects_divergence(self, tmp_dir):
        db_path = os.path.join(tmp_dir, "hc2.db")
        mem = SharedMemory.persistent(db_path)
        mem.store("x", "1")

        # Simulate backend-only entry
        mem._backend.store("ghost", "boo")
        result = mem.health_check()
        assert not result["healthy"]
        assert "ghost" in result["only_in_backend"]


# ---------------------------------------------------------------------------
# Edge-case tests — divergence detection, sync recovery, concurrency
# ---------------------------------------------------------------------------

class TestHealthCheckDivergenceEdge:
    """health_check detects divergence from both directions."""

    def test_detects_store_only_entries(self, tmp_dir):
        """Entries only in _store (not backend) are reported."""
        db_path = os.path.join(tmp_dir, "hc3.db")
        mem = SharedMemory.persistent(db_path)

        # Store normally
        mem.store("good", "value")

        # Inject directly into _store, bypassing backend
        mem._store["orphan"] = MemoryEntry(key="orphan", value="lost")

        result = mem.health_check()
        assert not result["healthy"]
        assert "orphan" in result["only_in_store"]
        assert result["store_count"] == 2
        assert result["backend_count"] == 1

    def test_detects_both_directions(self, tmp_dir):
        """Detects entries only-in-store AND only-in-backend simultaneously."""
        db_path = os.path.join(tmp_dir, "hc4.db")
        mem = SharedMemory.persistent(db_path)

        mem.store("shared", "ok")
        mem._store["local_only"] = MemoryEntry(key="local_only", value="l")
        mem._backend.store("backend_only", "b")

        result = mem.health_check()
        assert not result["healthy"]
        assert "local_only" in result["only_in_store"]
        assert "backend_only" in result["only_in_backend"]


class TestSyncRecoveryAfterBackendFailure:
    """sync() reconciles after backend recovery."""

    def test_sync_pushes_all_missing_to_backend(self, tmp_dir):
        """sync() writes all _store entries missing from the backend."""
        db_path = os.path.join(tmp_dir, "sync2.db")
        mem = SharedMemory.persistent(db_path)

        mem.store("a", "1")
        mem.store("b", "2")
        mem.store("c", "3")

        # Simulate backend losing two entries
        mem._backend.delete("a")
        mem._backend.delete("c")

        assert not mem.health_check()["healthy"]

        report = mem.sync()
        assert set(report["synced"]) == {"a", "c"}
        assert report["failed"] == []

        # After sync, health should be restored
        assert mem.health_check()["healthy"]

    def test_sync_after_full_backend_wipe(self, tmp_dir):
        """sync() recovers after all backend data is lost."""
        db_path = os.path.join(tmp_dir, "sync3.db")
        mem = SharedMemory.persistent(db_path)

        mem.store("x", "10")
        mem.store("y", "20")

        # Wipe backend
        mem._backend.clear()
        assert mem._backend.count() == 0

        report = mem.sync()
        assert set(report["synced"]) == {"x", "y"}
        assert mem._backend.count() == 2


class TestConcurrentStoreRecall:
    """Concurrent async store/recall operations."""

    @pytest.mark.asyncio
    async def test_concurrent_astore(self):
        """Multiple concurrent astore() calls don't corrupt state."""
        mem = SharedMemory()

        async def _store(i):
            await mem.astore(f"key_{i}", f"value_{i}", author=f"agent_{i}")

        await asyncio.gather(*[_store(i) for i in range(20)])
        assert len(mem._store) == 20
        for i in range(20):
            assert mem.recall(f"key_{i}") == f"value_{i}"

    @pytest.mark.asyncio
    async def test_concurrent_astore_and_arecall(self):
        """Concurrent store and recall don't deadlock or corrupt."""
        mem = SharedMemory()
        # Pre-populate some keys
        for i in range(10):
            mem.store(f"pre_{i}", f"val_{i}")

        async def _store(i):
            await mem.astore(f"new_{i}", f"new_val_{i}")

        async def _recall(i):
            return await mem.arecall(f"pre_{i}")

        stores = [_store(i) for i in range(10)]
        recalls = [_recall(i) for i in range(10)]
        results = await asyncio.gather(*stores, *recalls)

        # Recall results are the last 10
        recall_results = results[10:]
        for i, val in enumerate(recall_results):
            assert val == f"val_{i}"

        # New stores should all be present
        for i in range(10):
            assert mem.recall(f"new_{i}") == f"new_val_{i}"
