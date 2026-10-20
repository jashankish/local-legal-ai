# Compatibility shim: the embedding implementation lives in rag/embedder.py.
from rag.embedder import LegalDocumentEmbedder, get_embedder  # noqa: F401
