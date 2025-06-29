# Initialize ChromaDB and manage persistent vector storage

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils import embedding_functions
import logging
from typing import List, Dict, Optional, Any
import hashlib
import json
from datetime import datetime
import sys
import os

# Add the backend directory to the path so we can import config
backend_path = os.path.join(os.path.dirname(__file__), '..', 'backend')
sys.path.append(backend_path)

try:
    from config import settings
except ImportError:
    # Fallback configuration if config module is not available
    class FallbackSettings:
        chromadb_collection_name = "legal_documents"
    
    settings = FallbackSettings()
    logging.warning("Using fallback settings - config module not found")


logger = logging.getLogger(__name__)


class ChromaDBManager:
    """ChromaDB manager for legal document storage and retrieval."""
    
    def __init__(self):
        self.client = None
        self.collection = None
        self.collection_name = settings.chromadb_collection_name
        self.db_path = "./data/chroma_db"
        self._connect()
    
    def _connect(self):
        """Connect to ChromaDB."""
        try:
            # Initialize ChromaDB client
            self.client = chromadb.PersistentClient(path=self.db_path)
            
            # Get embedding function with fallbacks
            embedding_function = self._get_embedding_function()
            if embedding_function is None:
                raise Exception("No working embedding function available")
            
            # Get or create collection with the embedding function
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=embedding_function,
                metadata={"description": "Legal documents collection"}
            )
            
            logger.info(f"Connected to ChromaDB collection: {self.collection_name}")
            
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            # Create a minimal fallback collection without embedding function
            try:
                self.client = chromadb.PersistentClient(path=self.db_path)
                self.collection = self.client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"description": "Legal documents collection"}
                )
                logger.warning("Using ChromaDB without custom embedding function")
            except Exception as fallback_error:
                logger.error(f"Complete ChromaDB initialization failed: {fallback_error}")
                raise
    
    def add_documents(
        self,
        texts: List[str],
        metadatas: List[Dict[str, Any]],
        ids: Optional[List[str]] = None
    ) -> bool:
        """Add documents to the collection."""
        try:
            if not ids:
                # Generate IDs based on content hash
                ids = [self._generate_doc_id(text, metadata) 
                      for text, metadata in zip(texts, metadatas)]
            
            # Add timestamps to metadata
            for metadata in metadatas:
                metadata['indexed_at'] = datetime.utcnow().isoformat()
            
            self.collection.add(
                documents=texts,
                metadatas=metadatas,
                ids=ids
            )
            
            logger.info(f"Added {len(texts)} documents to collection")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add documents: {e}")
            return False
    
    def search_documents(
        self,
        query: str,
        n_results: int = 5,
        where: Optional[Dict] = None,
        include: List[str] = ["documents", "metadatas", "distances"]
    ) -> Dict:
        """Search for similar documents."""
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where,
                include=include
            )
            
            logger.info(f"Search completed: {len(results.get('documents', [[]])[0])} results")
            return results
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}
    
    def get_document_by_id(self, doc_id: str) -> Optional[Dict]:
        """Get a specific document by ID."""
        try:
            result = self.collection.get(
                ids=[doc_id],
                include=["documents", "metadatas"]
            )
            
            if result['documents']:
                return {
                    'id': doc_id,
                    'document': result['documents'][0],
                    'metadata': result['metadatas'][0]
                }
            return None
            
        except Exception as e:
            logger.error(f"Failed to get document {doc_id}: {e}")
            return None
    
    def delete_document(self, doc_id: str) -> bool:
        """Delete a document by ID."""
        try:
            self.collection.delete(ids=[doc_id])
            logger.info(f"Deleted document: {doc_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {e}")
            return False
    
    def delete_documents_by_metadata(self, where: Dict) -> bool:
        """Delete documents matching metadata criteria."""
        try:
            self.collection.delete(where=where)
            logger.info(f"Deleted documents matching: {where}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete documents: {e}")
            return False
    
    def get_collection_stats(self) -> Dict:
        """Get collection statistics."""
        try:
            count = self.collection.count()
            return {
                "name": self.collection_name,
                "document_count": count,
                "status": "healthy"
            }
            
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {
                "name": self.collection_name,
                "document_count": 0,
                "status": "error",
                "error": str(e)
            }
    
    def list_documents(
        self,
        limit: int = 100,
        offset: int = 0,
        where: Optional[Dict] = None
    ) -> List[Dict]:
        """List documents in the collection."""
        try:
            # Get all documents (ChromaDB doesn't support limit/offset directly)
            result = self.collection.get(
                where=where,
                include=["documents", "metadatas"]
            )
            
            documents = []
            ids = result.get('ids', [])
            docs = result.get('documents', [])
            metas = result.get('metadatas', [])
            
            for i, (doc_id, doc, meta) in enumerate(zip(ids, docs, metas)):
                if i >= offset and len(documents) < limit:
                    documents.append({
                        'id': doc_id,
                        'document': doc[:200] + "..." if len(doc) > 200 else doc,  # Preview
                        'metadata': meta
                    })
            
            return documents
            
        except Exception as e:
            logger.error(f"Failed to list documents: {e}")
            return []
    
    def update_document_metadata(self, doc_id: str, metadata: Dict) -> bool:
        """Update document metadata."""
        try:
            # ChromaDB doesn't support direct metadata updates, so we need to:
            # 1. Get the document
            # 2. Delete it
            # 3. Re-add with updated metadata
            
            existing = self.get_document_by_id(doc_id)
            if not existing:
                return False
            
            # Update metadata
            updated_metadata = existing['metadata'].copy()
            updated_metadata.update(metadata)
            updated_metadata['updated_at'] = datetime.utcnow().isoformat()
            
            # Delete and re-add
            self.delete_document(doc_id)
            return self.add_documents(
                texts=[existing['document']],
                metadatas=[updated_metadata],
                ids=[doc_id]
            )
            
        except Exception as e:
            logger.error(f"Failed to update document metadata: {e}")
            return False
    
    def search_by_metadata(self, where: Dict, limit: int = 10) -> List[Dict]:
        """Search documents by metadata only."""
        try:
            result = self.collection.get(
                where=where,
                include=["documents", "metadatas"]
            )
            
            documents = []
            ids = result.get('ids', [])
            docs = result.get('documents', [])
            metas = result.get('metadatas', [])
            
            for doc_id, doc, meta in zip(ids[:limit], docs[:limit], metas[:limit]):
                documents.append({
                    'id': doc_id,
                    'document': doc,
                    'metadata': meta
                })
            
            return documents
            
        except Exception as e:
            logger.error(f"Failed to search by metadata: {e}")
            return []
    
    def _generate_doc_id(self, text: str, metadata: Dict) -> str:
        """Generate a unique ID for a document."""
        # Create hash from text and key metadata
        content = text + json.dumps(metadata.get('source', ''), sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()
    
    def health_check(self) -> bool:
        """Check if ChromaDB is healthy."""
        try:
            self.collection.count()
            return True
        except Exception:
            return False
    
    def reset_collection(self) -> bool:
        """Reset the collection (delete all documents)."""
        try:
            self.client.delete_collection(self.collection_name)
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "Legal documents collection"}
            )
            logger.warning(f"Reset collection: {self.collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to reset collection: {e}")
            return False

    def _get_embedding_function(self):
        """Get the appropriate embedding function with fallbacks."""
        try:
            # Try SentenceTransformersEmbeddingFunction first (more reliable)
            try:
                from chromadb.utils import embedding_functions
                sentence_transformer_ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name="all-MiniLM-L6-v2"
                )
                logger.info("Using SentenceTransformerEmbeddingFunction for ChromaDB")
                return sentence_transformer_ef
            except Exception as e:
                logger.warning(f"SentenceTransformerEmbeddingFunction failed: {e}")
            
            # Fallback to a simple embedding function that doesn't use ONNX
            try:
                # Use a custom simple embedding function
                class SimpleEmbeddingFunction:
                    def __call__(self, input):
                        # Simple hash-based embedding to avoid ONNX issues
                        import hashlib
                        import numpy as np
                        
                        if isinstance(input, str):
                            input = [input]
                        
                        embeddings = []
                        for text in input:
                            # Create a simple deterministic embedding
                            hash_obj = hashlib.md5(text.encode())
                            hash_bytes = hash_obj.digest()
                            # Convert to float array
                            embedding = np.frombuffer(hash_bytes, dtype=np.uint8).astype(np.float32)
                            # Normalize to create a proper embedding vector
                            embedding = embedding / np.linalg.norm(embedding)
                            # Pad or truncate to standard size (384 dimensions)
                            if len(embedding) < 384:
                                embedding = np.pad(embedding, (0, 384 - len(embedding)))
                            else:
                                embedding = embedding[:384]
                            embeddings.append(embedding.tolist())
                        
                        return embeddings
                
                simple_ef = SimpleEmbeddingFunction()
                logger.info("Using SimpleEmbeddingFunction for ChromaDB (ONNX fallback)")
                return simple_ef
            except Exception as e:
                logger.warning(f"SimpleEmbeddingFunction failed: {e}")
            
            # Last resort: Try DefaultEmbeddingFunction
            try:
                default_ef = embedding_functions.DefaultEmbeddingFunction()
                logger.info("Using DefaultEmbeddingFunction for ChromaDB")
                return default_ef
            except Exception as e:
                logger.warning(f"DefaultEmbeddingFunction failed: {e}")
            
        except Exception as e:
            logger.error(f"Failed to get any embedding function: {e}")
            
        # If all else fails, return None and handle gracefully
        logger.error("No working embedding function found")
        return None


# Global ChromaDB manager instance
chroma_manager = ChromaDBManager()
