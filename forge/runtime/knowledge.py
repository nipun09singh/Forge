"""Domain knowledge — policies, rules, vocabulary, and patterns for specific domains.

Domain knowledge is what differentiates a generic chatbot from a domain expert.
It's injected into agent prompts and critic evaluations to ensure agents
behave correctly for their specific business context.

Includes a RAG (Retrieval-Augmented Generation) layer with tiered backends:
  1. ChromaDB vector store (if ``chromadb`` is installed)
  2. TF-IDF retrieval via scikit-learn (if ``sklearn`` is installed)
  3. BM25-style keyword retrieval using only the standard library
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency probing
# ---------------------------------------------------------------------------
try:
    import chromadb  # type: ignore[import-untyped]
    _HAS_CHROMADB = True
except ImportError:  # pragma: no cover
    _HAS_CHROMADB = False

try:
    from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]
    from sklearn.metrics.pairwise import cosine_similarity  # type: ignore[import-untyped]
    _HAS_SKLEARN = True
except ImportError:  # pragma: no cover
    _HAS_SKLEARN = False


# ═══════════════════════════════════════════════════════════
# Text chunking utilities
# ═══════════════════════════════════════════════════════════

def _estimate_tokens(text: str) -> int:
    """Rough token count (~4 chars per token for English text)."""
    return max(1, len(text) // 4)


def chunk_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 100,
) -> list[str]:
    """Split *text* into overlapping chunks measured in approximate tokens.

    Uses word boundaries to avoid splitting mid-word.
    """
    words = text.split()
    if not words:
        return []

    # Convert token targets to approximate word counts (avg ~1.3 words/token)
    words_per_chunk = max(1, int(chunk_size * 0.75))
    overlap_words = max(0, int(chunk_overlap * 0.75))

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + words_per_chunk, len(words))
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk.strip())
        if end >= len(words):
            break
        start += words_per_chunk - overlap_words
    return chunks


# ═══════════════════════════════════════════════════════════
# Retrieval backends
# ═══════════════════════════════════════════════════════════

class _RetrievalBackend:
    """Abstract interface for a retrieval backend."""

    def add(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        raise NotImplementedError

    def query(self, question: str, top_k: int = 5) -> list[str]:
        raise NotImplementedError

    def count(self) -> int:
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError


class _BM25Backend(_RetrievalBackend):
    """BM25-style keyword retrieval using only the standard library."""

    _STOP_WORDS = frozenset(
        "a an the is are was were be been being have has had do does did "
        "will would shall should may might can could of in to for on with "
        "at by from as into about between through after before above below "
        "and or but not no nor so yet both either neither each every all "
        "some any few more most other such only own same than too very it "
        "its he she they them their his her this that these those i me my "
        "we our you your".split()
    )

    def __init__(self) -> None:
        self._docs: list[str] = []
        self._doc_ids: list[str] = []
        self._metadata: list[dict[str, Any]] = []

    def _tokenize(self, text: str) -> list[str]:
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        return [t for t in tokens if t not in self._STOP_WORDS and len(t) > 1]

    def add(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        self._docs.append(text)
        self._doc_ids.append(doc_id)
        self._metadata.append(metadata or {})

    def query(self, question: str, top_k: int = 5) -> list[str]:
        if not self._docs:
            return []
        query_tokens = self._tokenize(question)
        if not query_tokens:
            return self._docs[:top_k]

        n = len(self._docs)
        avg_dl = sum(len(self._tokenize(d)) for d in self._docs) / max(n, 1)

        # IDF
        df: Counter[str] = Counter()
        for doc in self._docs:
            doc_terms = set(self._tokenize(doc))
            for t in query_tokens:
                if t in doc_terms:
                    df[t] += 1

        k1, b = 1.5, 0.75
        scores: list[float] = []
        for doc in self._docs:
            doc_tokens = self._tokenize(doc)
            dl = len(doc_tokens)
            tf = Counter(doc_tokens)
            score = 0.0
            for t in query_tokens:
                if df[t] == 0:
                    continue
                idf = math.log((n - df[t] + 0.5) / (df[t] + 0.5) + 1.0)
                tf_norm = (tf[t] * (k1 + 1)) / (tf[t] + k1 * (1 - b + b * dl / max(avg_dl, 1)))
                score += idf * tf_norm
            scores.append(score)

        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [self._docs[i] for i in ranked[:top_k]]

    def count(self) -> int:
        return len(self._docs)

    def clear(self) -> None:
        self._docs.clear()
        self._doc_ids.clear()
        self._metadata.clear()


class _TfidfBackend(_RetrievalBackend):
    """TF-IDF retrieval using scikit-learn."""

    def __init__(self) -> None:
        self._docs: list[str] = []
        self._doc_ids: list[str] = []
        self._metadata: list[dict[str, Any]] = []
        self._vectorizer: Any = None
        self._matrix: Any = None
        self._dirty = True

    def add(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        self._docs.append(text)
        self._doc_ids.append(doc_id)
        self._metadata.append(metadata or {})
        self._dirty = True

    def _rebuild(self) -> None:
        if not self._dirty or not self._docs:
            return
        self._vectorizer = TfidfVectorizer(stop_words="english")
        self._matrix = self._vectorizer.fit_transform(self._docs)
        self._dirty = False

    def query(self, question: str, top_k: int = 5) -> list[str]:
        if not self._docs:
            return []
        self._rebuild()
        q_vec = self._vectorizer.transform([question])
        sims = cosine_similarity(q_vec, self._matrix).flatten()
        ranked = sims.argsort()[::-1][:top_k]
        return [self._docs[i] for i in ranked]

    def count(self) -> int:
        return len(self._docs)

    def clear(self) -> None:
        self._docs.clear()
        self._doc_ids.clear()
        self._metadata.clear()
        self._dirty = True


class _ChromaBackend(_RetrievalBackend):
    """ChromaDB vector-store backend."""

    def __init__(self, collection_name: str = "knowledge") -> None:
        self._client = chromadb.Client()
        self._collection = self._client.get_or_create_collection(name=collection_name)

    def add(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        self._collection.add(
            ids=[doc_id],
            documents=[text],
            metadatas=[metadata or {}],
        )

    def query(self, question: str, top_k: int = 5) -> list[str]:
        if self._collection.count() == 0:
            return []
        results = self._collection.query(query_texts=[question], n_results=min(top_k, self._collection.count()))
        docs = results.get("documents", [[]])
        return docs[0] if docs else []

    def count(self) -> int:
        return self._collection.count()

    def clear(self) -> None:
        # Re-create collection to clear it
        name = self._collection.name
        self._client.delete_collection(name)
        self._collection = self._client.get_or_create_collection(name=name)


def _make_backend(backend: str | None = None, **kwargs: Any) -> _RetrievalBackend:
    """Create the best available retrieval backend."""
    if backend == "chromadb" or (backend is None and _HAS_CHROMADB):
        if not _HAS_CHROMADB:
            raise ImportError("chromadb is not installed")
        return _ChromaBackend(**kwargs)
    if backend == "tfidf" or (backend is None and _HAS_SKLEARN):
        if not _HAS_SKLEARN:
            raise ImportError("scikit-learn is not installed")
        return _TfidfBackend()
    return _BM25Backend()


# ═══════════════════════════════════════════════════════════
# KnowledgeStore — document ingestion and retrieval
# ═══════════════════════════════════════════════════════════

class KnowledgeStore:
    """Manages document ingestion, chunking, and semantic retrieval.

    Automatically selects the best available backend:
      chromadb → sklearn TF-IDF → stdlib BM25.
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
        backend: str | None = None,
        **backend_kwargs: Any,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._backend = _make_backend(backend, **backend_kwargs)
        self._next_id = 0

    # -- ingestion ---------------------------------------------------------

    def _next_doc_id(self) -> str:
        self._next_id += 1
        return f"chunk-{self._next_id:06d}"

    def ingest(self, text: str, metadata: dict[str, Any] | None = None) -> int:
        """Ingest free-form text. Returns the number of chunks created."""
        chunks = chunk_text(text, self.chunk_size, self.chunk_overlap)
        for chunk in chunks:
            self._backend.add(self._next_doc_id(), chunk, metadata)
        return len(chunks)

    def ingest_file(self, path: str | Path) -> int:
        """Read a text file and ingest its contents. Returns chunk count."""
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        return self.ingest(text, metadata={"source": str(p)})

    def ingest_directory(self, path: str | Path, glob_pattern: str = "**/*.txt") -> int:
        """Recursively ingest text files from a directory."""
        total = 0
        for file_path in sorted(Path(path).glob(glob_pattern)):
            if file_path.is_file():
                total += self.ingest_file(file_path)
        return total

    # -- retrieval ---------------------------------------------------------

    def query(self, question: str, top_k: int = 5) -> list[str]:
        """Retrieve the most relevant chunks for *question*."""
        return self._backend.query(question, top_k=top_k)

    # -- housekeeping ------------------------------------------------------

    @property
    def document_count(self) -> int:
        return self._backend.count()

    def clear(self) -> None:
        self._backend.clear()
        self._next_id = 0

    @property
    def backend_name(self) -> str:
        return type(self._backend).__name__.strip("_")


@dataclass
class DomainKnowledge:
    """
    Knowledge about a specific business domain.
    
    This is injected into agents and critics to ensure domain-appropriate behavior.
    Can be loaded from a file, generated by LLM, or built programmatically.
    """
    domain: str = ""
    
    # Business rules and policies
    policies: list[str] = field(default_factory=list)
    
    # Compliance rules (used by ComplianceCritic)
    compliance_rules: list[str] = field(default_factory=list)
    
    # Domain vocabulary (so agents use correct terminology)
    vocabulary: dict[str, str] = field(default_factory=dict)
    
    # Quality criteria (what "good" looks like in this domain)
    quality_criteria: list[str] = field(default_factory=list)
    
    # Common failure patterns (learned from past mistakes)
    failure_patterns: list[dict[str, str]] = field(default_factory=list)
    
    # Reference documents / FAQ content
    reference_docs: list[str] = field(default_factory=list)
    
    # Escalation triggers (when to involve humans)
    escalation_triggers: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._knowledge_store: KnowledgeStore | None = None

    # -- RAG knowledge store -----------------------------------------------

    def enable_rag(self, backend: str | None = None, **kwargs: Any) -> KnowledgeStore:
        """Create and attach a :class:`KnowledgeStore` for RAG retrieval."""
        self._knowledge_store = KnowledgeStore(backend=backend, **kwargs)
        # Auto-ingest reference_docs if any
        for doc in self.reference_docs:
            self._knowledge_store.ingest(doc, metadata={"source": "reference_docs"})
        return self._knowledge_store

    @property
    def knowledge_store(self) -> KnowledgeStore | None:
        return self._knowledge_store

    def rag_context(self, question: str, top_k: int = 5) -> str:
        """Query the knowledge store and return relevant context as text."""
        if self._knowledge_store is None or self._knowledge_store.document_count == 0:
            return ""
        chunks = self._knowledge_store.query(question, top_k=top_k)
        if not chunks:
            return ""
        return "\n\n---\n\n".join(chunks)

    def to_rag_prompt_injection(self, question: str, top_k: int = 5) -> str:
        """Combine static domain knowledge with RAG-retrieved context.

        Falls back to plain :meth:`to_prompt_injection` when no store is
        configured or no relevant chunks are found.
        """
        static = self.to_prompt_injection()
        rag = self.rag_context(question, top_k=top_k)

        sections = []
        if static:
            sections.append(static)
        if rag:
            sections.append("## Retrieved Context (most relevant)\n" + rag)
        return "\n\n".join(sections) if sections else ""

    def to_prompt_injection(self) -> str:
        """Convert knowledge to text that can be injected into agent prompts."""
        sections = []

        if self.policies:
            sections.append("## Business Policies\n" + "\n".join(f"- {p}" for p in self.policies))

        if self.compliance_rules:
            sections.append("## Compliance Rules (MUST follow)\n" + "\n".join(f"- {r}" for r in self.compliance_rules))

        if self.vocabulary:
            vocab_lines = [f"- {term}: {definition}" for term, definition in self.vocabulary.items()]
            sections.append("## Domain Vocabulary\n" + "\n".join(vocab_lines))

        if self.quality_criteria:
            sections.append("## Quality Standards\n" + "\n".join(f"- {c}" for c in self.quality_criteria))

        if self.failure_patterns:
            patterns = [f"- AVOID: {p.get('pattern', '')} → INSTEAD: {p.get('solution', '')}" for p in self.failure_patterns]
            sections.append("## Known Failure Patterns (avoid these)\n" + "\n".join(patterns))

        if self.escalation_triggers:
            sections.append("## Escalation Triggers (involve human when)\n" + "\n".join(f"- {t}" for t in self.escalation_triggers))

        return "\n\n".join(sections) if sections else ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        return {
            "domain": self.domain,
            "policies": self.policies,
            "compliance_rules": self.compliance_rules,
            "vocabulary": self.vocabulary,
            "quality_criteria": self.quality_criteria,
            "failure_patterns": self.failure_patterns,
            "escalation_triggers": self.escalation_triggers,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DomainKnowledge":
        """Deserialize from dict."""
        import dataclasses
        valid = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in valid})

    @classmethod
    def from_file(cls, path: str) -> "DomainKnowledge":
        """Load from a JSON file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def save(self, path: str) -> None:
        """Save to a JSON file."""
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    def __repr__(self) -> str:
        return (f"DomainKnowledge(domain={self.domain!r}, "
                f"policies={len(self.policies)}, rules={len(self.compliance_rules)})")


# ═══════════════════════════════════════════════════════════
# Pre-built domain knowledge bases
# ═══════════════════════════════════════════════════════════

DOMAIN_KNOWLEDGE: dict[str, DomainKnowledge] = {
    "customer_support": DomainKnowledge(
        domain="customer_support",
        policies=[
            "First response within 5 minutes",
            "Resolution target: 24 hours",
            "Always acknowledge the customer's frustration before problem-solving",
            "Offer alternatives when the requested solution isn't possible",
            "Follow up after resolution to confirm satisfaction",
        ],
        compliance_rules=[
            "MUST: verify customer identity before making account changes",
            "MUST: log all interactions in the ticket system",
            "NEVER: share customer data with unauthorized parties",
            "NEVER: promise specific timelines without checking with relevant team",
            "NEVER: make up information — say 'I don't know' and escalate",
        ],
        vocabulary={
            "CSAT": "Customer Satisfaction Score (1-5 rating)",
            "NPS": "Net Promoter Score (-100 to +100)",
            "SLA": "Service Level Agreement — response/resolution time targets",
            "FCR": "First Contact Resolution — resolved in one interaction",
            "churn": "Customer cancellation / leaving the service",
        },
        quality_criteria=[
            "Response is empathetic and professional",
            "Issue is clearly understood and restated",
            "Solution is actionable and specific",
            "Follow-up steps are clearly communicated",
            "No information is fabricated or assumed",
        ],
        failure_patterns=[
            {"pattern": "Agent provides incorrect refund amount", "solution": "Always query the database for exact charges before quoting refund amounts"},
            {"pattern": "Agent shares internal system names with customer", "solution": "Use customer-facing terms only (e.g., 'our system' not 'the Postgres database')"},
            {"pattern": "Agent makes promises about feature timelines", "solution": "Say 'I'll check with our product team' instead of committing to dates"},
        ],
        escalation_triggers=[
            "Customer mentions legal action or regulatory complaint",
            "Issue involves data breach or security incident",
            "Customer requests refund over $500",
            "Issue unresolved after 3 interactions",
            "Customer explicitly asks for a manager/supervisor",
        ],
    ),

    "software_development": DomainKnowledge(
        domain="software_development",
        policies=[
            "All code must have tests before merging",
            "No secrets in source code — use environment variables",
            "Follow existing code style and patterns in the project",
            "Write clear commit messages explaining WHY, not just WHAT",
        ],
        compliance_rules=[
            "MUST: run tests before declaring code complete",
            "MUST: handle errors — never swallow exceptions silently",
            "NEVER: hardcode credentials, API keys, or passwords",
            "NEVER: use eval() or exec() with user input",
            "NEVER: delete production data without backup",
        ],
        vocabulary={
            "PR": "Pull Request — a code change submission for review",
            "CI/CD": "Continuous Integration / Continuous Deployment",
            "LGTM": "Looks Good To Me — approval for code merge",
            "WIP": "Work In Progress — not ready for review yet",
        },
        quality_criteria=[
            "Code compiles without errors",
            "All existing tests still pass",
            "New functionality has test coverage",
            "No security vulnerabilities introduced",
            "Code is readable and well-documented",
        ],
        failure_patterns=[
            {"pattern": "Agent writes code without checking existing patterns", "solution": "Always read existing files first to match style"},
            {"pattern": "Agent creates files but doesn't test them", "solution": "Always run tests after creating/modifying code"},
            {"pattern": "Agent uses deprecated APIs", "solution": "Check documentation for current API versions"},
        ],
        escalation_triggers=[
            "Build failures that persist after 3 retries",
            "Security vulnerability detected",
            "Database migration that could lose data",
            "Changes affecting more than 10 files",
        ],
    ),

    # E-commerce domain — these policies are examples for the ecommerce domain only.
    # For other domains, define your own DomainKnowledge or load from a file.
    "ecommerce": DomainKnowledge(
        domain="ecommerce",
        policies=[
            "Return policy: 30 days for unused items, 14 days for electronics",
            "Free shipping on orders over $50",
            "Price match guarantee within 7 days of purchase",
            "Customer loyalty program: 1 point per $1 spent",
        ],
        compliance_rules=[
            "MUST: verify order number before making changes",
            "MUST: confirm shipping address before processing",
            "NEVER: process refunds over $500 without human approval",
            "NEVER: share payment details (show only last 4 digits)",
        ],
        quality_criteria=[
            "Order details are accurate",
            "Customer gets clear delivery timeline",
            "Return/refund process is clearly explained",
            "Upsell suggestions are relevant and not pushy",
        ],
        escalation_triggers=[
            "Fraud suspected on an order",
            "Refund amount exceeds $500",
            "Shipping damage claim",
            "Customer threatens chargeback",
        ],
    ),
}


def get_domain_knowledge(domain: str) -> DomainKnowledge:
    """Get pre-built knowledge for a domain, or return empty knowledge."""
    # Normalize domain name
    domain_key = domain.lower().replace(" ", "_").replace("-", "_")
    
    # Try exact match
    if domain_key in DOMAIN_KNOWLEDGE:
        return DOMAIN_KNOWLEDGE[domain_key]
    
    # Try partial match
    for key, knowledge in DOMAIN_KNOWLEDGE.items():
        if key in domain_key or domain_key in key:
            return knowledge
    
    # Return empty knowledge
    return DomainKnowledge(domain=domain)


# ═══════════════════════════════════════════════════════════
# AgentKnowledgeBase — per-agent RAG store
# ═══════════════════════════════════════════════════════════

class AgentKnowledgeBase:
    """Per-agent knowledge store that retrieves context during execution.

    Usage::

        kb = AgentKnowledgeBase()
        kb.add_knowledge("Our return policy allows returns within 30 days.")
        kb.add_knowledge_file("docs/faq.txt")

        # During execution, retrieve relevant context for the prompt
        context = kb.retrieve("customer asking about refund")
    """

    def __init__(
        self,
        backend: str | None = None,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
        **backend_kwargs: Any,
    ) -> None:
        self._store = KnowledgeStore(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            backend=backend,
            **backend_kwargs,
        )

    def add_knowledge(self, text: str, metadata: dict[str, Any] | None = None) -> int:
        """Add free-form text knowledge. Returns chunk count."""
        return self._store.ingest(text, metadata)

    def add_knowledge_file(self, path: str | Path) -> int:
        """Ingest a text file. Returns chunk count."""
        return self._store.ingest_file(path)

    def add_knowledge_directory(self, path: str | Path, glob_pattern: str = "**/*.txt") -> int:
        """Recursively ingest text files from a directory."""
        return self._store.ingest_directory(path, glob_pattern)

    def retrieve(self, question: str, top_k: int = 5) -> str:
        """Retrieve relevant knowledge and return as prompt-ready text."""
        chunks = self._store.query(question, top_k=top_k)
        if not chunks:
            return ""
        return "## Agent Knowledge (retrieved)\n" + "\n\n---\n\n".join(chunks)

    @property
    def document_count(self) -> int:
        return self._store.document_count

    def clear(self) -> None:
        self._store.clear()
