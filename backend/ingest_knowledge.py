#!/usr/bin/env python3
"""
Ingest emergency protocols from protocols.md into ChromaDB.

Usage:
    cd backend
    python ingest_knowledge.py
"""

import os
import re
import sys

# Ensure backend/ is on the path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from langchain_core.documents import Document  # noqa: E402

KNOWLEDGE_FILE = os.path.join(backend_dir, "app", "data", "knowledge", "protocols.md")


def ingest():
    if not os.path.exists(KNOWLEDGE_FILE):
        print(f"Error: {KNOWLEDGE_FILE} not found.")
        sys.exit(1)

    # Late import so config/.env is loaded properly
    from app.services.rag_service import add_documents

    print(f"Reading protocols from {KNOWLEDGE_FILE} ...")
    with open(KNOWLEDGE_FILE, encoding="utf-8") as f:
        content = f.read()

    # Split by level-2/3/4 headers
    parts = re.split(r"^#{1,3}\s+", content, flags=re.MULTILINE)
    documents: list[Document] = []

    for part in parts[1:]:
        lines = part.strip().split("\n")
        if not lines:
            continue

        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()

        # Accept sections with meaningful content
        if len(body) > 30 and any(kw in body for kw in ("Role", "Trigger", "SOP", "Action", "Keywords", "Standard Operating Procedure")):
            documents.append(
                Document(
                    page_content=f"Title: {title}\n{body}",
                    metadata={"title": title, "source": "protocols.md"},
                )
            )

    if not documents:
        print("No valid protocol sections found. Check protocols.md format.")
        sys.exit(1)

    # Reset vector store to ensure clean single-copy indexing
    from app.services.rag_service import reset_vector_store, add_documents
    reset_vector_store()

    print(f"Ingesting {len(documents)} emergency protocols into ChromaDB ...")
    count = add_documents(documents)
    print(f"Done — {count} protocols successfully ingested into ChromaDB.")


if __name__ == "__main__":
    ingest()
