"""Tests for forge.runtime.memory and persistence"""

import os
import tempfile
import pytest
from forge.runtime.memory import SharedMemory
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
