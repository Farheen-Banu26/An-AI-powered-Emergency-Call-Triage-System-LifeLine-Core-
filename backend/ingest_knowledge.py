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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from langchain_core.documents import Document  # noqa: E402

KNOWLEDGE_FILE = os.path.join("app", "data", "knowledge", "protocols.md")


def ingest():
    if not os.path.exists(KNOWLEDGE_FILE):
        print(f"Error: {KNOWLEDGE_FILE} not found. Run from the backend/ directory.")
        sys.exit(1)

    # Late import so config/.env is loaded properly
    from app.services.rag_service import add_documents

    print(f"Reading {KNOWLEDGE_FILE} ...")
    with open(KNOWLEDGE_FILE, encoding="utf-8") as f:
        content = f.read()

    # Split by level-2/3/4 headers
    parts = re.split(r"^#{2,4}\s+", content, flags=re.MULTILINE)
    documents: list[Document] = []

    for part in parts[1:]:
        lines = part.strip().split("\n")
        if not lines:
            continue

        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()

        # Accept sections with meaningful content
        if len(body) > 30 and any(kw in body for kw in ("Role", "Trigger", "SOP", "Action")):
            documents.append(
                Document(
                    page_content=f"Title: {title}\n{body}",
                    metadata={"title": title, "source": "protocols.md"},
                )
            )

    if not documents:
        print("No valid protocol sections found. Check protocols.md format.")
        sys.exit(1)

    print(f"Ingesting {len(documents)} documents into ChromaDB ...")
    add_documents(documents)
    print(f"Done — {len(documents)} protocols ingested.")


if __name__ == "__main__":
    ingest()
