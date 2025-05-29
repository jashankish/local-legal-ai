# RAG Pipeline for Legal Document Q&A

import logging
from typing import List, Dict, Optional, Any, Tuple
import json
from datetime import datetime
import sys
import os
import httpx
import asyncio
from dataclasses import dataclass, asdict

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'vector_store'))

from config import settings
from chromadb_setup import chroma_manager
from embedder import get_embedder

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """Result from document retrieval."""
    document_id: str
    content: str
    metadata: Dict[str, Any]
    similarity_score: float
    chunk_index: int


@dataclass
class RAGResponse:
    """Response from RAG pipeline."""
    answer: str
    sources: List[RetrievalResult]
    query: str
    total_tokens_used: Optional[int] = None
    processing_time: Optional[float] = None
    confidence_score: Optional[float] = None


class LegalRAGPipeline:
    """RAG Pipeline specialized for legal document Q&A."""
    
    def __init__(self):
        """Initialize the RAG pipeline."""
        self.embedder = get_embedder()
        self.chroma_manager = chroma_manager
        self.model_endpoint = settings.model_endpoint
        self.max_tokens = settings.max_tokens
        self.temperature = settings.temperature
        
        # Legal-specific context templates
        self.system_prompt = """You are a specialized legal AI assistant. Your role is to provide accurate, 
helpful answers based on the provided legal documents. Follow these guidelines:

1. Only use information from the provided document context
2. Cite specific sections or clauses when possible
3. If the context doesn't contain enough information, say so explicitly
4. Use precise legal terminology
5. Provide clear, structured answers
6. Include relevant case law or statute citations if present in the context
7. Flag any potential legal risks or important considerations

Always preface your response with a confidence level (High/Medium/Low) based on the completeness 
of the information in the provided context."""

        self.context_template = """Based on the following legal document excerpts, please answer the question.

LEGAL DOCUMENT CONTEXT:
{context}

QUESTION: {question}

Please provide a comprehensive answer based on the context above, citing specific sections where relevant."""

    async def retrieve_documents(self, 
                                query: str, 
                                num_results: int = 5,
                                filter_metadata: Optional[Dict] = None) -> List[RetrievalResult]:
        """
        Retrieve relevant documents using semantic search.
        
        Args:
            query: User question
            num_results: Number of documents to retrieve
            filter_metadata: Optional metadata filters
            
        Returns:
            List of retrieval results
        """
        try:
            logger.info(f"Retrieving documents for query: {query[:100]}...")
            
            # Generate query embedding
            query_embedding = self.embedder.embed_query(query)
            
            # Search ChromaDB
            search_results = self.chroma_manager.search_documents(
                query=query,
                n_results=num_results,
                where=filter_metadata,
                include=["documents", "metadatas", "distances"]
            )
            
            # Process results
            retrieval_results = []
            documents = search_results.get('documents', [[]])[0]
            metadatas = search_results.get('metadatas', [[]])[0]
            distances = search_results.get('distances', [[]])[0]
            ids = search_results.get('ids', [[]])[0]
            
            for i, (doc, metadata, distance, doc_id) in enumerate(zip(documents, metadatas, distances, ids)):
                # Convert distance to similarity score (ChromaDB returns distances)
                similarity_score = 1.0 - distance if distance is not None else 0.0
                
                result = RetrievalResult(
                    document_id=doc_id,
                    content=doc,
                    metadata=metadata,
                    similarity_score=similarity_score,
                    chunk_index=metadata.get('chunk_index', i)
                )
                retrieval_results.append(result)
            
            logger.info(f"Retrieved {len(retrieval_results)} relevant documents")
            return retrieval_results
            
        except Exception as e:
            logger.error(f"Document retrieval failed: {e}")
            raise
    
    def _format_context(self, retrieval_results: List[RetrievalResult]) -> str:
        """Format retrieved documents into context for the LLM."""
        context_parts = []
        
        for i, result in enumerate(retrieval_results, 1):
            # Format each document with metadata
            source_info = result.metadata.get('source', f'Document {i}')
            section = result.metadata.get('section_num', '')
            chunk_info = f" (chunk {result.chunk_index})" if result.chunk_index else ""
            
            context_part = f"""
--- Document {i}: {source_info}{chunk_info} ---
Section: {section if section else 'General'}
Relevance Score: {result.similarity_score:.2f}

{result.content}
"""
            context_parts.append(context_part)
        
        return "\n".join(context_parts)
    
    async def _generate_response(self, query: str, context: str) -> Tuple[str, Optional[int]]:
        """
        Generate response using the LLM.
        
        Args:
            query: User question
            context: Formatted document context
            
        Returns:
            Tuple of (response, tokens_used)
        """
        try:
            # Format the prompt
            formatted_prompt = self.context_template.format(
                context=context,
                question=query
            )
            
            # Prepare the request for the model endpoint
            payload = {
                "model": settings.model_name,
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": formatted_prompt}
                ],
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "stream": False
            }
            
            # Make request to model endpoint
            async with httpx.AsyncClient(timeout=60.0) as client:
                logger.info(f"Sending request to model endpoint: {self.model_endpoint}")
                response = await client.post(
                    f"{self.model_endpoint}/v1/chat/completions",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code != 200:
                    logger.error(f"Model endpoint error: {response.status_code} - {response.text}")
                    # Fallback response
                    return self._generate_fallback_response(query, context), None
                
                result = response.json()
                
                # Extract response and token usage
                answer = result['choices'][0]['message']['content']
                tokens_used = result.get('usage', {}).get('total_tokens')
                
                logger.info(f"Generated response using {tokens_used} tokens")
                return answer, tokens_used
                
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            # Return fallback response
            return self._generate_fallback_response(query, context), None
    
    def _generate_fallback_response(self, query: str, context: str) -> str:
        """Generate a fallback response when LLM is unavailable."""
        logger.warning("Using fallback response generation")
        
        # Simple extractive response based on context
        context_snippets = context.split("---")[:3]  # Take first 3 documents
        
        response = f"""**Confidence Level: Medium**

Based on the available legal documents, here are the relevant sections for your query:

**Query:** {query}

**Relevant Information:**
"""
        
        for i, snippet in enumerate(context_snippets[1:], 1):  # Skip first empty element
            if snippet.strip():
                lines = snippet.strip().split('\n')
                doc_title = lines[0] if lines else f"Document {i}"
                content_lines = [line for line in lines if line.strip() and not line.startswith('Section:') and not line.startswith('Relevance')]
                content = '\n'.join(content_lines[:3])  # First 3 content lines
                
                response += f"\n{i}. {doc_title}\n{content}\n"
        
        response += "\n**Note:** This response was generated from document excerpts. For detailed legal advice, please consult with a qualified attorney."
        
        return response
    
    def _calculate_confidence(self, retrieval_results: List[RetrievalResult], query: str) -> float:
        """Calculate confidence score based on retrieval results."""
        if not retrieval_results:
            return 0.0
        
        # Factors for confidence calculation
        avg_similarity = sum(r.similarity_score for r in retrieval_results) / len(retrieval_results)
        num_results = min(len(retrieval_results), 5)  # Cap at 5 for confidence calc
        
        # Higher confidence if we have good similarity scores and multiple results
        confidence = (avg_similarity * 0.7) + (num_results / 5.0 * 0.3)
        
        return min(confidence, 1.0)
    
    async def query(self, 
                   question: str, 
                   num_documents: int = 5,
                   filter_metadata: Optional[Dict] = None) -> RAGResponse:
        """
        Process a legal question through the complete RAG pipeline.
        
        Args:
            question: User's legal question
            num_documents: Number of documents to retrieve
            filter_metadata: Optional metadata filters for document retrieval
            
        Returns:
            RAG response with answer and sources
        """
        start_time = datetime.now()
        
        try:
            logger.info(f"Processing RAG query: {question[:100]}...")
            
            # Step 1: Retrieve relevant documents
            retrieval_results = await self.retrieve_documents(
                query=question,
                num_results=num_documents,
                filter_metadata=filter_metadata
            )
            
            if not retrieval_results:
                return RAGResponse(
                    answer="I couldn't find any relevant legal documents to answer your question. Please ensure documents have been uploaded to the system.",
                    sources=[],
                    query=question,
                    confidence_score=0.0
                )
            
            # Step 2: Format context for generation
            context = self._format_context(retrieval_results)
            
            # Step 3: Generate response
            answer, tokens_used = await self._generate_response(question, context)
            
            # Step 4: Calculate confidence and processing time
            confidence = self._calculate_confidence(retrieval_results, question)
            processing_time = (datetime.now() - start_time).total_seconds()
            
            # Create response
            response = RAGResponse(
                answer=answer,
                sources=retrieval_results,
                query=question,
                total_tokens_used=tokens_used,
                processing_time=processing_time,
                confidence_score=confidence
            )
            
            logger.info(f"RAG query completed in {processing_time:.2f}s with confidence {confidence:.2f}")
            return response
            
        except Exception as e:
            logger.error(f"RAG pipeline failed: {e}")
            processing_time = (datetime.now() - start_time).total_seconds()
            
            return RAGResponse(
                answer=f"I encountered an error while processing your question: {str(e)}. Please try again or contact support.",
                sources=[],
                query=question,
                processing_time=processing_time,
                confidence_score=0.0
            )
    
    async def stream_query(self, 
                          question: str, 
                          num_documents: int = 5,
                          filter_metadata: Optional[Dict] = None):
        """
        Stream a RAG response for real-time UI updates.
        
        Args:
            question: User's legal question
            num_documents: Number of documents to retrieve
            filter_metadata: Optional metadata filters
            
        Yields:
            Streaming response chunks
        """
        try:
            # First yield: Retrieval status
            yield {"status": "retrieving", "message": "Searching legal documents..."}
            
            # Retrieve documents
            retrieval_results = await self.retrieve_documents(
                query=question,
                num_results=num_documents,
                filter_metadata=filter_metadata
            )
            
            yield {"status": "retrieved", "sources": [asdict(r) for r in retrieval_results]}
            
            if not retrieval_results:
                yield {"status": "complete", "answer": "No relevant documents found."}
                return
            
            # Generate response
            yield {"status": "generating", "message": "Generating response..."}
            
            context = self._format_context(retrieval_results)
            answer, tokens_used = await self._generate_response(question, context)
            
            # Final response
            confidence = self._calculate_confidence(retrieval_results, question)
            yield {
                "status": "complete",
                "answer": answer,
                "confidence": confidence,
                "tokens_used": tokens_used
            }
            
        except Exception as e:
            logger.error(f"Streaming RAG failed: {e}")
            yield {"status": "error", "message": str(e)}


# Global RAG pipeline instance
rag_pipeline = LegalRAGPipeline()


def get_rag_pipeline() -> LegalRAGPipeline:
    """Get the global RAG pipeline instance."""
    return rag_pipeline 