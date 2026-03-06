"""Tests for forge.runtime.persistence."""
import pytest
import tempfile
import os

from forge.runtime.persistence import SQLiteMemoryBackend, InMemoryBackend


class TestSQLiteMemoryBackendInit:
    """Tests for SQLiteMemoryBackend initialization."""

    def test_init_creates_db(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "test.db")
            backend = SQLiteMemoryBackend(db_path=db_path)
            assert os.path.exists(db_path)
            backend.close()

    def test_init_creates_schema(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "test.db")
            backend = SQLiteMemoryBackend(db_path=db_path)
            row = backend._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='memories'"
            ).fetchone()
            assert row is not None
            backend.close()


class TestSQLiteStoreAndRecall:
    """Tests for store/recall operations."""

    def test_store_and_recall_string(self):
        with tempfile.TemporaryDirectory() as td:
            backend = SQLiteMemoryBackend(db_path=os.path.join(td, "test.db"))
            backend.store("greeting", "hello world")
            assert backend.recall("greeting") == "hello world"
            backend.close()

    def test_store_and_recall_dict(self):
        with tempfile.TemporaryDirectory() as td:
            backend = SQLiteMemoryBackend(db_path=os.path.join(td, "test.db"))
            data = {"key": "value", "count": 42}
            backend.store("config", data)
            assert backend.recall("config") == data
            backend.close()

    def test_recall_missing_key_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            backend = SQLiteMemoryBackend(db_path=os.path.join(td, "test.db"))
            assert backend.recall("nonexistent") is None
            backend.close()

    def test_store_overwrites_existing(self):
        with tempfile.TemporaryDirectory() as td:
            backend = SQLiteMemoryBackend(db_path=os.path.join(td, "test.db"))
            backend.store("key", "v1")
            backend.store("key", "v2")
            assert backend.recall("key") == "v2"
            backend.close()

    def test_store_with_session_id(self):
        with tempfile.TemporaryDirectory() as td:
            backend = SQLiteMemoryBackend(db_path=os.path.join(td, "test.db"))
            backend.store("key", "session_val", session_id="sess-1")
            assert backend.recall("key", session_id="sess-1") == "session_val"
            backend.close()


class TestSQLiteSearch:
    """Tests for search operations."""

    def test_search_by_tag(self):
        with tempfile.TemporaryDirectory() as td:
            backend = SQLiteMemoryBackend(db_path=os.path.join(td, "test.db"))
            backend.store("item1", "data1", tags=["important"])
            backend.store("item2", "data2", tags=["trivial"])
            results = backend.search(tag="important")
            assert len(results) == 1
            assert results[0]["key"] == "item1"
            backend.close()

    def test_search_by_author(self):
        with tempfile.TemporaryDirectory() as td:
            backend = SQLiteMemoryBackend(db_path=os.path.join(td, "test.db"))
            backend.store("item1", "data1", author="alice")
            backend.store("item2", "data2", author="bob")
            results = backend.search(author="alice")
            assert len(results) == 1
            assert results[0]["key"] == "item1"
            backend.close()

    def test_search_by_keyword(self):
        with tempfile.TemporaryDirectory() as td:
            backend = SQLiteMemoryBackend(db_path=os.path.join(td, "test.db"))
            backend.store("report", "monthly revenue report")
            backend.store("log", "system startup log")
            results = backend.search(keyword="revenue")
            assert len(results) == 1
            assert results[0]["key"] == "report"
            backend.close()

    def test_search_empty_results(self):
        with tempfile.TemporaryDirectory() as td:
            backend = SQLiteMemoryBackend(db_path=os.path.join(td, "test.db"))
            results = backend.search(tag="nonexistent")
            assert results == []
            backend.close()


class TestSQLiteDeleteAndClear:
    """Tests for delete and clear operations."""

    def test_delete_existing_key(self):
        with tempfile.TemporaryDirectory() as td:
            backend = SQLiteMemoryBackend(db_path=os.path.join(td, "test.db"))
            backend.store("key", "value")
            assert backend.delete("key") is True
            assert backend.recall("key") is None
            backend.close()

    def test_delete_missing_key(self):
        with tempfile.TemporaryDirectory() as td:
            backend = SQLiteMemoryBackend(db_path=os.path.join(td, "test.db"))
            assert backend.delete("missing") is False
            backend.close()

    def test_clear_all(self):
        with tempfile.TemporaryDirectory() as td:
            backend = SQLiteMemoryBackend(db_path=os.path.join(td, "test.db"))
            backend.store("k1", "v1")
            backend.store("k2", "v2")
            backend.clear()
            assert backend.recall("k1") is None
            assert backend.recall("k2") is None
            backend.close()

    def test_clear_by_session(self):
        with tempfile.TemporaryDirectory() as td:
            backend = SQLiteMemoryBackend(db_path=os.path.join(td, "test.db"))
            backend.store("k1", "v1", session_id="s1")
            backend.store("k2", "v2", session_id="s2")
            backend.clear(session_id="s1")
            assert backend.recall("k1", session_id="s1") is None
            # s2 data should remain
            assert backend.recall("k2", session_id="s2") == "v2"
            backend.close()


class TestSQLitePersistenceAcrossReloads:
    """Tests that data survives closing and reopening."""

    def test_data_persists_across_reopen(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "persist.db")
            backend = SQLiteMemoryBackend(db_path=db_path)
            backend.store("persist_key", {"data": "survives"})
            backend.close()

            backend2 = SQLiteMemoryBackend(db_path=db_path)
            assert backend2.recall("persist_key") == {"data": "survives"}
            backend2.close()

    def test_list_recent(self):
        with tempfile.TemporaryDirectory() as td:
            backend = SQLiteMemoryBackend(db_path=os.path.join(td, "test.db"))
            for i in range(5):
                backend.store(f"item{i}", f"value{i}")
            recent = backend.list_recent(limit=3)
            assert len(recent) == 3
            backend.close()


class TestInMemoryBackend:
    """Tests for the InMemoryBackend (dict-based)."""

    def test_store_and_recall(self):
        backend = InMemoryBackend()
        backend.store("k", "v")
        assert backend.recall("k") == "v"

    def test_recall_missing(self):
        backend = InMemoryBackend()
        assert backend.recall("missing") is None

    def test_delete(self):
        backend = InMemoryBackend()
        backend.store("k", "v")
        assert backend.delete("k") is True
        assert backend.recall("k") is None

    def test_clear(self):
        backend = InMemoryBackend()
        backend.store("k1", "v1")
        backend.store("k2", "v2")
        backend.clear()
        assert backend.recall("k1") is None

    def test_search_by_keyword(self):
        backend = InMemoryBackend()
        backend.store("report", "monthly revenue")
        backend.store("log", "system log")
        results = backend.search(keyword="revenue")
        assert len(results) == 1

    def test_list_recent(self):
        backend = InMemoryBackend()
        for i in range(10):
            backend.store(f"item{i}", f"val{i}")
        recent = backend.list_recent(limit=3)
        assert len(recent) == 3
