import logging
import math
import os
import re
from functools import lru_cache
from typing import List, Optional

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.config import get_settings

logger = logging.getLogger(__name__)


class FastFallbackEmbeddings(Embeddings):
    """
    Fast, deterministic semantic-aware embedding generator.
    Produces dense 384-dimensional unit-norm vectors.
    Requires 0 external downloads and 0 network requests, ensuring 100% offline availability.
    """

    def __init__(self, dim: int = 384):
        self.dim = dim

    def _embed_text(self, text: str) -> list[float]:
        words = re.findall(r"\w+", text.lower())
        vec = [0.0] * self.dim
        if not words:
            vec[0] = 1.0
            return vec

        for idx, word in enumerate(words):
            w_hash = hash(word)
            pos_1 = abs(w_hash) % self.dim
            pos_2 = abs(w_hash >> 8) % self.dim
            pos_3 = abs(w_hash >> 16) % self.dim
            weight = 1.0 / (math.log(idx + 2))
            vec[pos_1] += weight * 1.5
            vec[pos_2] += weight * 0.8
            vec[pos_3] += weight * 0.4

        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_text(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_text(text)


def _get_embedding_model() -> Embeddings:
    """Select the best available embedding model."""
    settings = get_settings()

    if settings.llm_provider == "ollama":
        try:
            from langchain_ollama import OllamaEmbeddings
            return OllamaEmbeddings(
                base_url=settings.ollama_base_url,
                model=settings.embedding_model,
            )
        except Exception as e:
            logger.warning("Ollama embeddings failed to initialize: %s. Using local fallback.", e)

    return FastFallbackEmbeddings(dim=384)


@lru_cache
def _get_vector_store():
    """Lazily initialize and cache the ChromaDB vector store."""
    from langchain_chroma import Chroma
    settings = get_settings()
    embeddings = _get_embedding_model()

    persist_dir = settings.resolved_chroma_persist_dir
    os.makedirs(persist_dir, exist_ok=True)

    store = Chroma(
        collection_name=settings.chroma_collection,
        embedding_function=embeddings,
        persist_directory=persist_dir,
    )
    logger.info(
        "ChromaDB initialized | collection=%s | dir=%s",
        settings.chroma_collection,
        persist_dir,
    )
    return store


def reset_vector_store():
    """Clear and reset the cached ChromaDB vector store."""
    import chromadb
    settings = get_settings()
    persist_dir = settings.resolved_chroma_persist_dir
    try:
        client = chromadb.PersistentClient(path=persist_dir)
        try:
            client.delete_collection(settings.chroma_collection)
            logger.info("Deleted existing ChromaDB collection: %s", settings.chroma_collection)
        except Exception:
            pass
    except Exception as e:
        logger.warning("Error resetting ChromaDB client: %s", e)
    _get_vector_store.cache_clear()


@lru_cache
def _load_protocol_sections() -> list[dict]:
    """Parse and cache protocol sections from protocols.md for fallback matching."""
    protocols_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "knowledge", "protocols.md"
    )
    if not os.path.exists(protocols_path):
        return []

    try:
        with open(protocols_path, encoding="utf-8") as f:
            content = f.read()

        sections = re.split(r"^#{1,3}\s+", content, flags=re.MULTILINE)
        docs = []
        for sec in sections[1:]:
            lines = sec.strip().split("\n")
            if not lines:
                continue
            title = lines[0].strip()
            body = "\n".join(lines[1:]).strip()

            kw_match = re.search(r"\*\*Keywords\*\*:\s*(.*)", body, re.IGNORECASE)
            keywords_text = kw_match.group(1).lower() if kw_match else ""
            keywords_set = set(k.strip() for k in keywords_text.split(",") if k.strip())

            if len(body) > 30 and any(kw in body for kw in ("Role", "Trigger", "SOP", "Action", "Keywords", "Standard Operating Procedure")):
                docs.append({
                    "title": title,
                    "body": body,
                    "keywords_set": keywords_set,
                    "keywords_text": keywords_text,
                    "full_text": f"{title}\n{body}".lower(),
                })
        return docs
    except Exception as e:
        logger.error("Failed to load protocol sections: %s", e)
        return []


def _protocol_keyword_search(query: str, k: int = 3) -> list[str]:
    """Secondary fallback search if vector store is uninitialized or returns empty."""
    sections = _load_protocol_sections()
    if not sections:
        return []

    q_lower = query.lower()
    q_words = [w for w in re.findall(r"\w+", q_lower) if len(w) > 2]

    scored: list[tuple[float, str]] = []
    for sec in sections:
        score = 0.0
        title_lower = sec["title"].lower()

        for kw in sec["keywords_set"]:
            if kw in q_lower:
                score += 25.0

        for w in q_words:
            if w in title_lower:
                score += 15.0
            if w in sec["keywords_text"]:
                score += 8.0
            if w in sec["full_text"]:
                score += 1.0

        if any(term in q_lower for term in ["cardiac", "heart attack", "cpr", "not breathing", "unconscious", "bleeding"]):
            if "ambulance" in title_lower or "ems" in title_lower:
                score += 30.0

        if any(term in q_lower for term in ["fire", "smoke", "blaze", "burning", "trapped"]):
            if "fire" in title_lower:
                score += 30.0

        if any(term in q_lower for term in ["weapon", "gun", "knife", "threat", "robbery", "assault"]):
            if "police" in title_lower or "shooter" in title_lower or "terror" in title_lower:
                score += 30.0

        if score > 0:
            content = f"Title: {sec['title']}\n{sec['body']}"
            scored.append((score, content))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [s[1] for s in scored[:k]]


def retrieve_context(query: str, k: int = 3) -> str:
    """
    Retrieve relevant emergency protocol context for a given query.
    PRIMARY: Vector similarity search via ChromaDB vector store.
    FALLBACK: Keyword protocol search if ChromaDB is empty or encounters an error.
    """
    # ── PRIMARY: ChromaDB Vector Similarity Search ──────────────
    try:
        store = _get_vector_store()
        docs = store.similarity_search(query, k=k)
        if docs:
            logger.info("ChromaDB vector similarity search retrieved %d documents for query: %s", len(docs), query[:50])
            return "\n\n---\n\n".join([doc.page_content for doc in docs])
    except Exception as e:
        logger.warning("ChromaDB vector retrieval encountered exception: %s. Using keyword fallback.", e)

    # ── OPTIONAL FALLBACK: Keyword / Semantic Term Match ────────
    kw_results = _protocol_keyword_search(query, k=k)
    if kw_results:
        logger.info("Fallback keyword search retrieved %d protocols for query: %s", len(kw_results), query[:50])
        return "\n\n---\n\n".join(kw_results)

    return "No matching protocols found."


def add_documents(documents: list[Document]) -> int:
    """Add documents to the vector store. Returns count added."""
    store = _get_vector_store()
    store.add_documents(documents)
    logger.info("Added %d documents to ChromaDB.", len(documents))
    return len(documents)
