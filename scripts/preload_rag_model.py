"""Download the pinned embedding model during a future demo-image build."""

from sentence_transformers import SentenceTransformer

from config import RAG_EMBEDDING_MODEL


def main() -> None:
    SentenceTransformer(RAG_EMBEDDING_MODEL)
    print(f"Cached embedding model: {RAG_EMBEDDING_MODEL}")


if __name__ == "__main__":
    main()
