"""Tests for forge.runtime.knowledge — RAG layer and domain knowledge."""

import os
import tempfile
import pytest

from forge.runtime.knowledge import (
    AgentKnowledgeBase,
    DomainKnowledge,
    KnowledgeStore,
    chunk_text,
    get_domain_knowledge,
)


# ═══════════════════════════════════════════════════════════
# Chunking
# ═══════════════════════════════════════════════════════════

class TestChunking:
    def test_empty_text(self):
        assert chunk_text("") == []

    def test_short_text_single_chunk(self):
        chunks = chunk_text("hello world", chunk_size=500)
        assert len(chunks) == 1
        assert chunks[0] == "hello world"

    def test_long_text_multiple_chunks(self):
        words = ["word"] * 1000
        text = " ".join(words)
        chunks = chunk_text(text, chunk_size=100, chunk_overlap=20)
        assert len(chunks) > 1
        # Each chunk should be non-empty
        for c in chunks:
            assert len(c) > 0

    def test_overlap_produces_shared_content(self):
        words = [f"w{i}" for i in range(200)]
        text = " ".join(words)
        chunks = chunk_text(text, chunk_size=100, chunk_overlap=50)
        assert len(chunks) >= 2
        # Overlapping chunks should share some words
        first_words = set(chunks[0].split())
        second_words = set(chunks[1].split())
        assert first_words & second_words, "Overlapping chunks should share words"


# ═══════════════════════════════════════════════════════════
# KnowledgeStore — BM25 (stdlib) backend
# ═══════════════════════════════════════════════════════════

class TestKnowledgeStoreBM25:
    def _make_store(self) -> KnowledgeStore:
        return KnowledgeStore(backend="bm25")

    def test_ingest_text(self):
        store = self._make_store()
        count = store.ingest("The quick brown fox jumps over the lazy dog.")
        assert count >= 1
        assert store.document_count >= 1

    def test_ingest_long_text_creates_chunks(self):
        store = self._make_store()
        text = " ".join(["knowledge"] * 2000)
        count = store.ingest(text)
        assert count > 1

    def test_query_returns_relevant_results(self):
        store = self._make_store()
        store.ingest("Python is a programming language used for web development.")
        store.ingest("Cats are fluffy domestic animals that love sleeping.")
        store.ingest("Machine learning uses algorithms to find patterns in data.")

        results = store.query("programming language", top_k=2)
        assert len(results) >= 1
        assert any("Python" in r or "programming" in r for r in results)

    def test_query_empty_store(self):
        store = self._make_store()
        assert store.query("anything") == []

    def test_clear(self):
        store = self._make_store()
        store.ingest("some text")
        assert store.document_count >= 1
        store.clear()
        assert store.document_count == 0

    def test_ingest_file(self):
        store = self._make_store()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("Refund policy: 30 days for unused items.")
            f.flush()
            path = f.name
        try:
            count = store.ingest_file(path)
            assert count >= 1
            results = store.query("refund policy")
            assert len(results) >= 1
        finally:
            os.unlink(path)

    def test_ingest_directory(self):
        store = self._make_store()
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                p = os.path.join(tmpdir, f"doc{i}.txt")
                with open(p, "w", encoding="utf-8") as f:
                    f.write(f"Document number {i} about topic {i}")
            count = store.ingest_directory(tmpdir, glob_pattern="*.txt")
            assert count >= 3

    def test_backend_name(self):
        store = self._make_store()
        assert "BM25" in store.backend_name


# ═══════════════════════════════════════════════════════════
# DomainKnowledge — static injection (backward compat)
# ═══════════════════════════════════════════════════════════

class TestDomainKnowledgeStatic:
    def test_to_prompt_injection(self):
        dk = DomainKnowledge(
            domain="test",
            policies=["Be polite"],
            compliance_rules=["Never lie"],
        )
        text = dk.to_prompt_injection()
        assert "Be polite" in text
        assert "Never lie" in text

    def test_empty_knowledge(self):
        dk = DomainKnowledge()
        assert dk.to_prompt_injection() == ""

    def test_serialization_roundtrip(self):
        dk = DomainKnowledge(domain="test", policies=["p1"], compliance_rules=["r1"])
        data = dk.to_dict()
        dk2 = DomainKnowledge.from_dict(data)
        assert dk2.domain == "test"
        assert dk2.policies == ["p1"]

    def test_get_domain_knowledge(self):
        dk = get_domain_knowledge("customer_support")
        assert dk.domain == "customer_support"
        assert len(dk.policies) > 0

    def test_get_domain_knowledge_unknown(self):
        dk = get_domain_knowledge("unknown_domain_xyz")
        assert dk.domain == "unknown_domain_xyz"
        assert dk.policies == []


# ═══════════════════════════════════════════════════════════
# DomainKnowledge — RAG integration
# ═══════════════════════════════════════════════════════════

class TestDomainKnowledgeRAG:
    def test_enable_rag_creates_store(self):
        dk = DomainKnowledge(domain="test")
        store = dk.enable_rag(backend="bm25")
        assert store is not None
        assert dk.knowledge_store is store

    def test_enable_rag_auto_ingests_reference_docs(self):
        dk = DomainKnowledge(
            domain="test",
            reference_docs=["Refund policy allows returns within 30 days."],
        )
        dk.enable_rag(backend="bm25")
        assert dk.knowledge_store is not None
        assert dk.knowledge_store.document_count >= 1

    def test_rag_context_returns_relevant_text(self):
        dk = DomainKnowledge(domain="test")
        dk.enable_rag(backend="bm25")
        dk.knowledge_store.ingest("Python programming is great for data science.")
        dk.knowledge_store.ingest("Cats enjoy warm sunny spots by the window.")

        ctx = dk.rag_context("python data science")
        assert "Python" in ctx or "programming" in ctx

    def test_rag_context_empty_without_store(self):
        dk = DomainKnowledge(domain="test")
        assert dk.rag_context("anything") == ""

    def test_to_rag_prompt_injection_combines(self):
        dk = DomainKnowledge(
            domain="test",
            policies=["Always be helpful"],
        )
        dk.enable_rag(backend="bm25")
        dk.knowledge_store.ingest("Shipping takes 3-5 business days for standard orders.")

        text = dk.to_rag_prompt_injection("how long does shipping take")
        assert "Always be helpful" in text
        assert "Retrieved Context" in text

    def test_to_rag_prompt_injection_fallback_no_store(self):
        dk = DomainKnowledge(domain="test", policies=["p1"])
        text = dk.to_rag_prompt_injection("anything")
        # Should fall back to static injection
        assert "p1" in text
        assert "Retrieved Context" not in text


# ═══════════════════════════════════════════════════════════
# AgentKnowledgeBase
# ═══════════════════════════════════════════════════════════

class TestAgentKnowledgeBase:
    def test_add_and_retrieve(self):
        kb = AgentKnowledgeBase(backend="bm25")
        kb.add_knowledge("Our product supports Python 3.8 and above.")
        kb.add_knowledge("Pricing starts at $10 per month for the basic plan.")

        result = kb.retrieve("what python versions are supported")
        assert "Python" in result

    def test_add_knowledge_file(self):
        kb = AgentKnowledgeBase(backend="bm25")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("API rate limits: 100 requests per minute for free tier.")
            f.flush()
            path = f.name
        try:
            count = kb.add_knowledge_file(path)
            assert count >= 1
            result = kb.retrieve("rate limits")
            assert "rate" in result.lower() or "100" in result
        finally:
            os.unlink(path)

    def test_retrieve_empty(self):
        kb = AgentKnowledgeBase(backend="bm25")
        assert kb.retrieve("anything") == ""

    def test_clear(self):
        kb = AgentKnowledgeBase(backend="bm25")
        kb.add_knowledge("test data")
        assert kb.document_count >= 1
        kb.clear()
        assert kb.document_count == 0

    def test_document_count(self):
        kb = AgentKnowledgeBase(backend="bm25")
        kb.add_knowledge("chunk one about topic A")
        kb.add_knowledge("chunk two about topic B")
        assert kb.document_count >= 2
