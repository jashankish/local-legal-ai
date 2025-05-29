# Document embedding and text processing for legal documents

import logging
from typing import List, Dict, Optional, Tuple, Any
from sentence_transformers import SentenceTransformer
import numpy as np
from datetime import datetime
import hashlib
import re
import sys
import os

# Add backend to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))
from config import settings

logger = logging.getLogger(__name__)


class LegalDocumentEmbedder:
    """Specialized embedder for legal documents with legal-specific preprocessing."""
    
    def __init__(self, model_name: str = None):
        """Initialize the embedder with a sentence transformer model."""
        self.model_name = model_name or settings.embedding_model
        self.model = None
        self.chunk_size = settings.chunk_size
        self.chunk_overlap = settings.chunk_overlap
        self._load_model()
        
        # Legal-specific patterns for better chunking
        self.section_patterns = [
            r'\n\s*(?:Section|Article|Chapter|Part)\s+\d+',
            r'\n\s*\d+\.\s+',  # Numbered sections
            r'\n\s*[A-Z]\.\s+',  # Lettered subsections
            r'\n\s*\([a-z]\)\s+',  # Lettered paragraphs
            r'\n\s*\(\d+\)\s+',  # Numbered paragraphs
            r'\nWHEREAS,',  # Contract clauses
            r'\nNOW THEREFORE,',
            r'\nIN WITNESS WHEREOF,',
        ]
        
    def _load_model(self):
        """Load the sentence transformer model."""
        try:
            logger.info(f"Loading embedding model: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)
            logger.info(f"Model loaded successfully. Embedding dimension: {self.model.get_sentence_embedding_dimension()}")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise
    
    def preprocess_legal_text(self, text: str) -> str:
        """Preprocess legal text for better embedding quality."""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Normalize legal citations
        text = re.sub(r'\b(\d+)\s+U\.?S\.?\s+(\d+)', r'\1 U.S. \2', text)
        text = re.sub(r'\b(\d+)\s+F\.?\s*(\d+)d?\s+(\d+)', r'\1 F.\2d \3', text)
        
        # Normalize contract language
        text = re.sub(r'\bWHEREAS,?\s+', 'WHEREAS ', text)
        text = re.sub(r'\bNOW\s+THEREFORE,?\s+', 'NOW THEREFORE ', text)
        
        # Remove page numbers and headers/footers
        text = re.sub(r'\n\s*Page\s+\d+\s*\n', '\n', text)
        text = re.sub(r'\n\s*-\s*\d+\s*-\s*\n', '\n', text)
        
        return text.strip()
    
    def chunk_legal_document(self, text: str, metadata: Dict = None) -> List[Dict]:
        """
        Chunk legal documents intelligently based on structure.
        
        Args:
            text: Document text
            metadata: Document metadata
            
        Returns:
            List of chunks with metadata
        """
        text = self.preprocess_legal_text(text)
        chunks = []
        
        # Try to split by legal sections first
        section_splits = self._split_by_legal_sections(text)
        
        if len(section_splits) > 1:
            # We found legal sections, process each
            for i, section in enumerate(section_splits):
                section_chunks = self._chunk_by_size(section, metadata, section_num=i)
                chunks.extend(section_chunks)
        else:
            # No clear sections, use size-based chunking
            chunks = self._chunk_by_size(text, metadata)
        
        return chunks
    
    def _split_by_legal_sections(self, text: str) -> List[str]:
        """Split text by legal section patterns."""
        # Try each pattern and use the one that gives best results
        for pattern in self.section_patterns:
            splits = re.split(pattern, text)
            if len(splits) > 2:  # Found meaningful splits
                # Rejoin the split markers with content
                sections = []
                matches = re.finditer(pattern, text)
                match_positions = [(m.start(), m.group()) for m in matches]
                
                if match_positions:
                    # Add first section (before first match)
                    first_split = text[:match_positions[0][0]]
                    if first_split.strip():
                        sections.append(first_split.strip())
                    
                    # Add sections with their headers
                    for i, (pos, header) in enumerate(match_positions):
                        next_pos = match_positions[i + 1][0] if i + 1 < len(match_positions) else len(text)
                        section_text = header + text[pos + len(header):next_pos]
                        sections.append(section_text.strip())
                    
                    return sections
        
        return [text]  # No meaningful sections found
    
    def _chunk_by_size(self, text: str, metadata: Dict = None, section_num: int = None) -> List[Dict]:
        """Chunk text by size with overlap."""
        chunks = []
        words = text.split()
        
        for i in range(0, len(words), self.chunk_size - self.chunk_overlap):
            chunk_words = words[i:i + self.chunk_size]
            chunk_text = ' '.join(chunk_words)
            
            # Create chunk metadata
            chunk_metadata = (metadata or {}).copy()
            chunk_metadata.update({
                'chunk_index': len(chunks),
                'chunk_size': len(chunk_words),
                'char_count': len(chunk_text),
                'created_at': datetime.utcnow().isoformat(),
            })
            
            if section_num is not None:
                chunk_metadata['section_num'] = section_num
            
            # Generate chunk ID
            chunk_id = self._generate_chunk_id(chunk_text, chunk_metadata)
            
            chunks.append({
                'id': chunk_id,
                'text': chunk_text,
                'metadata': chunk_metadata
            })
        
        return chunks
    
    def _generate_chunk_id(self, text: str, metadata: Dict) -> str:
        """Generate a unique ID for a chunk."""
        # Create hash from text and key metadata
        content = text[:100] + str(metadata.get('source', '')) + str(metadata.get('chunk_index', ''))
        return hashlib.md5(content.encode()).hexdigest()
    
    def embed_chunks(self, chunks: List[Dict]) -> List[Dict]:
        """Generate embeddings for text chunks."""
        try:
            # Extract texts for batch embedding
            texts = [chunk['text'] for chunk in chunks]
            
            logger.info(f"Generating embeddings for {len(texts)} chunks")
            embeddings = self.model.encode(
                texts,
                batch_size=32,
                show_progress_bar=True,
                convert_to_numpy=True
            )
            
            # Add embeddings to chunks
            enriched_chunks = []
            for chunk, embedding in zip(chunks, embeddings):
                enriched_chunk = chunk.copy()
                enriched_chunk['embedding'] = embedding.tolist()
                enriched_chunk['metadata']['embedding_model'] = self.model_name
                enriched_chunk['metadata']['embedding_dimension'] = len(embedding)
                enriched_chunks.append(enriched_chunk)
            
            logger.info(f"Successfully generated embeddings for {len(enriched_chunks)} chunks")
            return enriched_chunks
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise
    
    def embed_query(self, query: str) -> np.ndarray:
        """Generate embedding for a query."""
        try:
            # Preprocess query
            query = self.preprocess_legal_text(query)
            
            # Generate embedding
            embedding = self.model.encode([query], convert_to_numpy=True)
            return embedding[0]
            
        except Exception as e:
            logger.error(f"Failed to embed query: {e}")
            raise
    
    def process_document(self, 
                        text: str, 
                        metadata: Dict,
                        return_embeddings: bool = True) -> Tuple[List[Dict], Optional[List[np.ndarray]]]:
        """
        Complete document processing pipeline.
        
        Args:
            text: Document text
            metadata: Document metadata
            return_embeddings: Whether to return embeddings
            
        Returns:
            Tuple of (chunks, embeddings)
        """
        try:
            # Validate input
            if not text or not text.strip():
                raise ValueError("Document text cannot be empty")
            
            # Add processing metadata
            processing_metadata = metadata.copy()
            processing_metadata.update({
                'processed_at': datetime.utcnow().isoformat(),
                'embedding_model': self.model_name,
                'chunk_size': self.chunk_size,
                'chunk_overlap': self.chunk_overlap,
                'original_length': len(text),
                'word_count': len(text.split())
            })
            
            # Chunk the document
            logger.info(f"Processing document: {metadata.get('source', 'unknown')}")
            chunks = self.chunk_legal_document(text, processing_metadata)
            logger.info(f"Created {len(chunks)} chunks")
            
            # Generate embeddings if requested
            embeddings = None
            if return_embeddings:
                enriched_chunks = self.embed_chunks(chunks)
                embeddings = [chunk['embedding'] for chunk in enriched_chunks]
                chunks = enriched_chunks
            
            return chunks, embeddings
            
        except Exception as e:
            logger.error(f"Failed to process document: {e}")
            raise
    
    def similarity_search(self, 
                         query_embedding: np.ndarray, 
                         embeddings: List[np.ndarray], 
                         top_k: int = 5) -> List[Tuple[int, float]]:
        """
        Find most similar embeddings using cosine similarity.
        
        Args:
            query_embedding: Query embedding vector
            embeddings: List of document embeddings
            top_k: Number of top results to return
            
        Returns:
            List of (index, similarity_score) tuples
        """
        try:
            # Convert to numpy arrays
            query_vec = np.array(query_embedding)
            doc_vecs = np.array(embeddings)
            
            # Calculate cosine similarities
            similarities = np.dot(doc_vecs, query_vec) / (
                np.linalg.norm(doc_vecs, axis=1) * np.linalg.norm(query_vec)
            )
            
            # Get top k indices
            top_indices = np.argsort(similarities)[::-1][:top_k]
            
            # Return index and similarity pairs
            results = [(int(idx), float(similarities[idx])) for idx in top_indices]
            
            return results
            
        except Exception as e:
            logger.error(f"Similarity search failed: {e}")
            raise


# Global embedder instance
embedder = LegalDocumentEmbedder()


def get_embedder() -> LegalDocumentEmbedder:
    """Get the global embedder instance."""
    return embedder 