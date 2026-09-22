import os

# Ordinary unit/API tests use the deterministic lexical backend. The real
# MiniLM/Chroma benchmark is a separate, versioned evaluation command.
os.environ.setdefault("RAG_RETRIEVAL_BACKEND", "tfidf")
os.environ.setdefault("RAG_RELEVANCE_THRESHOLD", "0.12")
