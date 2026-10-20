# Compatibility shim: the RAG pipeline implementation lives in rag/rag_pipeline.py.
from rag.rag_pipeline import LegalRAGPipeline, RAGResponse, RetrievalResult, get_rag_pipeline  # noqa: F401
