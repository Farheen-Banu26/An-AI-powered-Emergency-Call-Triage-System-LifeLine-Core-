import logging
from functools import lru_cache

from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

from app.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def _get_vector_store() -> Chroma:
    """Lazily initialize and cache the ChromaDB vector store."""
    settings = get_settings()
    embeddings = OllamaEmbeddings(
        base_url=settings.ollama_base_url,
        model=settings.embedding_model,
    )
    store = Chroma(
        collection_name=settings.chroma_collection,
        embedding_function=embeddings,
        persist_directory=settings.chroma_persist_dir,
    )
    logger.info(
        "ChromaDB initialized | collection=%s | dir=%s",
        settings.chroma_collection,
        settings.chroma_persist_dir,
    )
    return store


def retrieve_context(query: str, k: int = 3) -> str:
    """Retrieve relevant protocol context for a given query."""
    try:
        store = _get_vector_store()
        docs = store.similarity_search(query, k=k)
        if not docs:
            return "No matching protocols found."
        return "\n\n".join([doc.page_content for doc in docs])
    except Exception as e:
        logger.error("RAG retrieval failed: %s", e)
        return "Protocol retrieval unavailable."


def add_documents(documents) -> int:
    """Add documents to the vector store. Returns count added."""
    store = _get_vector_store()
    store.add_documents(documents)
    logger.info("Added %d documents to ChromaDB.", len(documents))
    return len(documents)
