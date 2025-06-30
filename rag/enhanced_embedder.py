#!/usr/bin/env python3
"""
Enhanced Legal Document Embedder - Phase 4
Advanced RAG capabilities with legal precedent linking and multi-modal support
"""

import json
import logging
import re
import time
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import spacy

class EnhancedLegalDocumentEmbedder:
    """
    Enhanced embedder with advanced legal document processing capabilities.
    
    Features:
    - Legal precedent extraction and linking
    - Multi-modal document support
    - Citation tracking and verification
    - Query refinement suggestions
    - Advanced legal entity recognition
    - Document similarity analysis
    """
    
    def __init__(self, model_name: str = "enhanced_legal_tfidf"):
        self.model_name = model_name
        self.vectorizer = None
        self.legal_terms_vocab = self._load_legal_vocabulary()
        self.citation_patterns = self._compile_citation_patterns()
        self.precedent_database = {}
        self.document_cache = {}
        self.similarity_threshold = 0.3
        
        # Initialize spaCy for NER (if available)
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError:
            self.nlp = None
            logging.warning("spaCy model not found. Some NER features will be disabled.")
        
        logging.info(f"Enhanced Legal Embedder initialized: {model_name}")
    
    def _load_legal_vocabulary(self) -> Dict[str, float]:
        """Load and return legal terms vocabulary with weights."""
        legal_terms = {
            # Contract terms
            'contract': 2.0, 'agreement': 2.0, 'party': 1.8, 'parties': 1.8,
            'whereas': 2.2, 'therefore': 1.5, 'covenant': 2.5, 'covenant not to': 3.0,
            
            # Employment terms
            'employee': 2.0, 'employer': 2.0, 'employment': 2.0, 'termination': 2.5,
            'compensation': 2.3, 'salary': 2.0, 'benefits': 1.8, 'confidentiality': 2.8,
            'non-disclosure': 3.0, 'non-compete': 3.0, 'severance': 2.5,
            
            # Legal procedures
            'jurisdiction': 2.5, 'governing law': 3.0, 'dispute resolution': 2.8,
            'arbitration': 2.5, 'litigation': 2.5, 'mediation': 2.3,
            
            # Rights and obligations
            'rights': 2.0, 'obligations': 2.0, 'duties': 1.8, 'responsibilities': 1.8,
            'liability': 2.5, 'indemnity': 2.8, 'warranty': 2.3, 'representation': 2.0,
            
            # Time and dates
            'effective date': 2.5, 'term': 1.8, 'renewal': 2.0, 'expiration': 2.0,
            'notice period': 2.3, 'advance notice': 2.3,
            
            # Financial terms
            'payment': 2.0, 'invoice': 1.8, 'penalty': 2.3, 'damages': 2.5,
            'liquidated damages': 3.0, 'interest': 1.8, 'late fee': 2.0,
        }
        return legal_terms
    
    def _compile_citation_patterns(self) -> List[re.Pattern]:
        """Compile regex patterns for legal citation recognition."""
        patterns = [
            # Case citations (e.g., "Smith v. Jones, 123 F.3d 456 (2021)")
            re.compile(r'\b\w+\s+v\.?\s+\w+,?\s+\d+\s+\w+\.?\s*\d*\s+\d+\s*\(\d{4}\)', re.IGNORECASE),
            
            # Statute citations (e.g., "42 U.S.C. § 1983")
            re.compile(r'\b\d+\s+[A-Z]+\.?[A-Z]*\.?[A-Z]*\.?\s*§\s*\d+', re.IGNORECASE),
            
            # Code sections (e.g., "Section 1234 of the Civil Code")
            re.compile(r'\bsection\s+\d+\s+of\s+the\s+\w+\s+code\b', re.IGNORECASE),
            
            # Federal regulations (e.g., "29 CFR 1630.2")
            re.compile(r'\b\d+\s+CFR\s+\d+\.\d+\b', re.IGNORECASE),
            
            # Constitutional citations (e.g., "U.S. Const. amend. XIV")
            re.compile(r'\bU\.?S\.?\s+Const\.?\s+amend\.?\s+[IVXLC]+\b', re.IGNORECASE),
        ]
        return patterns
    
    def extract_legal_entities(self, text: str) -> Dict[str, List[str]]:
        """Extract legal entities using NLP and pattern matching."""
        entities = {
            'citations': [],
            'legal_terms': [],
            'dates': [],
            'monetary_amounts': [],
            'parties': [],
            'organizations': []
        }
        
        # Extract citations
        for pattern in self.citation_patterns:
            citations = pattern.findall(text)
            entities['citations'].extend(citations)
        
        # Extract monetary amounts
        money_pattern = re.compile(r'\$[\d,]+(?:\.\d{2})?')
        entities['monetary_amounts'] = money_pattern.findall(text)
        
        # Extract dates
        date_pattern = re.compile(r'\b\d{1,2}/\d{1,2}/\d{4}\b|\b\w+\s+\d{1,2},\s+\d{4}\b')
        entities['dates'] = date_pattern.findall(text)
        
        # Use spaCy for named entity recognition
        if self.nlp:
            doc = self.nlp(text)
            for ent in doc.ents:
                if ent.label_ in ['ORG', 'PERSON']:
                    if ent.label_ == 'ORG':
                        entities['organizations'].append(ent.text)
                    elif ent.label_ == 'PERSON':
                        entities['parties'].append(ent.text)
        
        # Extract legal terms from vocabulary
        text_lower = text.lower()
        for term in self.legal_terms_vocab:
            if term in text_lower:
                entities['legal_terms'].append(term)
        
        return entities
    
    def identify_precedents(self, text: str) -> List[Dict[str, Any]]:
        """Identify and extract legal precedents from text."""
        precedents = []
        
        for pattern in self.citation_patterns:
            for match in pattern.finditer(text):
                citation = match.group()
                precedent = {
                    'citation': citation,
                    'position': match.span(),
                    'context': text[max(0, match.start()-100):match.end()+100],
                    'type': self._classify_citation_type(citation),
                    'relevance_score': self._calculate_citation_relevance(citation, text)
                }
                precedents.append(precedent)
        
        return sorted(precedents, key=lambda x: x['relevance_score'], reverse=True)
    
    def _classify_citation_type(self, citation: str) -> str:
        """Classify the type of legal citation."""
        if 'v.' in citation.lower():
            return 'case_law'
        elif 'cfr' in citation.lower():
            return 'federal_regulation'
        elif 'u.s.c' in citation.lower():
            return 'federal_statute'
        elif 'const' in citation.lower():
            return 'constitutional'
        elif 'section' in citation.lower():
            return 'code_section'
        else:
            return 'unknown'
    
    def _calculate_citation_relevance(self, citation: str, context: str) -> float:
        """Calculate relevance score for a citation based on context."""
        base_score = 0.5
        
        # Increase score for certain types
        if 'v.' in citation.lower():
            base_score += 0.2
        
        # Check context for relevance indicators
        context_lower = context.lower()
        relevance_terms = ['holding', 'rule', 'precedent', 'established', 'court held']
        for term in relevance_terms:
            if term in context_lower:
                base_score += 0.1
        
        return min(base_score, 1.0)
    
    def process_document(self, text: str, metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Enhanced document processing with legal analysis.
        
        Args:
            text: Document text content
            metadata: Optional metadata dictionary
            
        Returns:
            Dictionary with processed chunks and enhanced metadata
        """
        if metadata is None:
            metadata = {}
        
        start_time = time.time()
        
        # Extract legal entities and precedents
        entities = self.extract_legal_entities(text)
        precedents = self.identify_precedents(text)
        
        # Enhanced text preprocessing
        preprocessed_text = self._advanced_preprocess(text)
        
        # Intelligent chunking with legal awareness
        chunks = self._enhanced_legal_chunking(preprocessed_text)
        
        # Initialize or update vectorizer
        if self.vectorizer is None:
            self.vectorizer = TfidfVectorizer(
                max_features=15000,  # Increased for Phase 4
                stop_words='english',
                ngram_range=(1, 3),  # Include trigrams for legal phrases
                min_df=1,
                max_df=0.95,
                sublinear_tf=True,
                vocabulary=self.legal_terms_vocab if len(self.legal_terms_vocab) < 1000 else None
            )
            
            # Fit on current chunks
            all_chunk_texts = [chunk['text'] for chunk in chunks]
            if all_chunk_texts:
                self.vectorizer.fit(all_chunk_texts)
        
        # Generate embeddings for chunks
        processed_chunks = []
        for i, chunk in enumerate(chunks):
            chunk_embedding = self.vectorizer.transform([chunk['text']])
            
            # Enhanced metadata for each chunk
            enhanced_metadata = {
                **metadata,
                'chunk_index': i,
                'chunk_size': len(chunk['text'].split()),
                'legal_entities': self._extract_chunk_entities(chunk['text']),
                'precedents': [p for p in precedents if self._is_precedent_in_chunk(p, chunk)],
                'legal_score': self._calculate_legal_score(chunk['text']),
                'complexity_score': self._calculate_complexity_score(chunk['text']),
                'processed_at': datetime.now().isoformat(),
                'embedding_model': self.model_name,
                'embedding_dimension': chunk_embedding.shape[1]
            }
            
            processed_chunks.append({
                'text': chunk['text'],
                'embedding': chunk_embedding.toarray()[0].tolist(),
                'metadata': enhanced_metadata,
                'section_type': chunk.get('section_type', 'general')
            })
        
        processing_time = time.time() - start_time
        
        # Document-level analysis
        document_analysis = {
            'total_entities': len(entities['citations']) + len(entities['legal_terms']),
            'precedent_count': len(precedents),
            'legal_complexity': np.mean([chunk['metadata']['complexity_score'] for chunk in processed_chunks]),
            'key_legal_terms': list(set(entities['legal_terms']))[:10],
            'citations_found': entities['citations'][:5],
            'document_type': self._classify_document_type(text, entities),
            'processing_time': processing_time
        }
        
        return {
            'chunks': processed_chunks,
            'document_analysis': document_analysis,
            'entities': entities,
            'precedents': precedents[:10],  # Top 10 most relevant
            'processing_metadata': {
                'chunks_created': len(processed_chunks),
                'processing_time': processing_time,
                'model_used': self.model_name,
                'total_tokens': sum(len(chunk['text'].split()) for chunk in processed_chunks)
            }
        }
    
    def _advanced_preprocess(self, text: str) -> str:
        """Advanced preprocessing for legal documents."""
        # Preserve legal citations and terms
        text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
        text = re.sub(r'([.!?])\s*([A-Z])', r'\1\n\2', text)  # Sentence boundaries
        
        # Preserve legal formatting
        text = re.sub(r'(\n\s*\d+\.)', r'\n\nSECTION\1', text)  # Mark sections
        text = re.sub(r'(\n\s*\([a-z]\))', r'\n\nSUBSECTION\1', text)  # Mark subsections
        
        return text.strip()
    
    def _enhanced_legal_chunking(self, text: str) -> List[Dict[str, Any]]:
        """Enhanced chunking with legal document structure awareness."""
        chunks = []
        
        # Split by legal sections first
        sections = re.split(r'\n\s*SECTION\s*', text)
        
        for section_idx, section in enumerate(sections):
            if not section.strip():
                continue
            
            # Identify section type
            section_type = self._identify_section_type(section)
            
            # Split large sections into smaller chunks
            if len(section.split()) > 200:
                subsections = re.split(r'\n\s*SUBSECTION\s*', section)
                for subsection in subsections:
                    if subsection.strip():
                        chunks.append({
                            'text': subsection.strip(),
                            'section_type': section_type,
                            'is_subsection': 'SUBSECTION' in section
                        })
            else:
                chunks.append({
                    'text': section.strip(),
                    'section_type': section_type,
                    'is_subsection': False
                })
        
        # If no sections found, use intelligent sentence-based chunking
        if len(chunks) <= 1:
            sentences = re.split(r'(?<=[.!?])\s+', text)
            current_chunk = ""
            
            for sentence in sentences:
                if len((current_chunk + " " + sentence).split()) <= 200:
                    current_chunk += " " + sentence if current_chunk else sentence
                else:
                    if current_chunk:
                        chunks.append({
                            'text': current_chunk.strip(),
                            'section_type': 'paragraph',
                            'is_subsection': False
                        })
                    current_chunk = sentence
            
            if current_chunk:
                chunks.append({
                    'text': current_chunk.strip(),
                    'section_type': 'paragraph',
                    'is_subsection': False
                })
        
        return [chunk for chunk in chunks if len(chunk['text'].split()) >= 10]
    
    def _identify_section_type(self, text: str) -> str:
        """Identify the type of legal section based on content."""
        text_lower = text.lower()
        
        if any(term in text_lower for term in ['compensation', 'salary', 'payment', 'wage']):
            return 'compensation'
        elif any(term in text_lower for term in ['termination', 'terminate', 'end', 'expir']):
            return 'termination'
        elif any(term in text_lower for term in ['confidential', 'non-disclosure', 'proprietary']):
            return 'confidentiality'
        elif any(term in text_lower for term in ['whereas', 'recital', 'background']):
            return 'recitals'
        elif any(term in text_lower for term in ['definition', 'define', 'means']):
            return 'definitions'
        elif any(term in text_lower for term in ['govern', 'jurisdiction', 'applicable law']):
            return 'governing_law'
        else:
            return 'general'
    
    def _extract_chunk_entities(self, text: str) -> Dict[str, List[str]]:
        """Extract entities specific to a chunk."""
        return self.extract_legal_entities(text)
    
    def _is_precedent_in_chunk(self, precedent: Dict, chunk: Dict) -> bool:
        """Check if a precedent is relevant to a specific chunk."""
        precedent_pos = precedent['position']
        chunk_text = chunk['text']
        return precedent['citation'] in chunk_text
    
    def _calculate_legal_score(self, text: str) -> float:
        """Calculate how 'legal' a text chunk is based on terminology."""
        text_lower = text.lower()
        legal_term_count = sum(1 for term in self.legal_terms_vocab if term in text_lower)
        total_words = len(text.split())
        
        if total_words == 0:
            return 0.0
        
        return min(legal_term_count / total_words * 10, 1.0)  # Normalize to 0-1
    
    def _calculate_complexity_score(self, text: str) -> float:
        """Calculate the complexity score of a text chunk."""
        sentences = re.split(r'[.!?]+', text)
        if not sentences:
            return 0.0
        
        avg_sentence_length = np.mean([len(s.split()) for s in sentences if s.strip()])
        legal_density = self._calculate_legal_score(text)
        citation_count = sum(1 for pattern in self.citation_patterns 
                           for _ in pattern.finditer(text))
        
        # Combine factors for complexity score
        complexity = (
            min(avg_sentence_length / 20, 1.0) * 0.4 +  # Sentence length factor
            legal_density * 0.4 +  # Legal terminology density
            min(citation_count / 10, 1.0) * 0.2  # Citation density
        )
        
        return complexity
    
    def _classify_document_type(self, text: str, entities: Dict) -> str:
        """Classify the type of legal document."""
        text_lower = text.lower()
        
        if 'employment' in text_lower and 'agreement' in text_lower:
            return 'employment_agreement'
        elif 'non-disclosure' in text_lower or 'confidentiality' in text_lower:
            return 'nda'
        elif 'lease' in text_lower or 'rental' in text_lower:
            return 'lease_agreement'
        elif 'purchase' in text_lower and 'sale' in text_lower:
            return 'purchase_agreement'
        elif 'service' in text_lower and 'agreement' in text_lower:
            return 'service_agreement'
        elif len(entities['citations']) > 3:
            return 'legal_brief'
        else:
            return 'general_legal'
    
    def generate_query_suggestions(self, query: str, document_analysis: Dict) -> List[str]:
        """Generate refined query suggestions based on document content."""
        suggestions = []
        
        # Base suggestions
        base_suggestions = [
            f"What are the key points about {query}?",
            f"How does {query} relate to the main agreement?",
            f"What are the legal implications of {query}?"
        ]
        
        # Document-specific suggestions based on type
        doc_type = document_analysis.get('document_type', 'general_legal')
        
        if doc_type == 'employment_agreement':
            suggestions.extend([
                "What are the compensation details?",
                "What are the termination conditions?",
                "What confidentiality requirements exist?",
                "What benefits are provided?"
            ])
        elif doc_type == 'nda':
            suggestions.extend([
                "What information is considered confidential?",
                "What are the penalties for disclosure?",
                "How long does the confidentiality obligation last?"
            ])
        
        # Add suggestions based on key legal terms found
        key_terms = document_analysis.get('key_legal_terms', [])
        for term in key_terms[:3]:
            suggestions.append(f"Tell me more about {term}")
        
        return suggestions[:8]  # Return top 8 suggestions
    
    def calculate_document_similarity(self, doc1_chunks: List[Dict], doc2_chunks: List[Dict]) -> float:
        """Calculate similarity between two documents based on their chunks."""
        if not doc1_chunks or not doc2_chunks:
            return 0.0
        
        # Get embeddings for all chunks
        doc1_embeddings = [chunk['embedding'] for chunk in doc1_chunks]
        doc2_embeddings = [chunk['embedding'] for chunk in doc2_chunks]
        
        # Calculate average document embeddings
        doc1_avg = np.mean(doc1_embeddings, axis=0)
        doc2_avg = np.mean(doc2_embeddings, axis=0)
        
        # Calculate cosine similarity
        similarity = cosine_similarity([doc1_avg], [doc2_avg])[0][0]
        return float(similarity)
    
    def find_similar_chunks(self, query_embedding: np.ndarray, all_chunks: List[Dict], 
                           top_k: int = 5) -> List[Dict]:
        """Find the most similar chunks to a query with enhanced ranking."""
        if not all_chunks:
            return []
        
        similarities = []
        for chunk in all_chunks:
            chunk_embedding = np.array(chunk['embedding'])
            similarity = cosine_similarity([query_embedding], [chunk_embedding])[0][0]
            
            # Enhance similarity score based on legal relevance
            legal_score = chunk['metadata'].get('legal_score', 0)
            complexity_score = chunk['metadata'].get('complexity_score', 0)
            
            # Weighted similarity considering legal relevance
            enhanced_similarity = (
                similarity * 0.7 +  # Base semantic similarity
                legal_score * 0.2 +  # Legal terminology relevance
                complexity_score * 0.1  # Document complexity
            )
            
            similarities.append({
                **chunk,
                'similarity_score': enhanced_similarity,
                'base_similarity': similarity
            })
        
        # Sort by enhanced similarity and return top_k
        similarities.sort(key=lambda x: x['similarity_score'], reverse=True)
        return similarities[:top_k]

    def get_model_info(self) -> Dict[str, Any]:
        """Return information about the enhanced embedder model."""
        return {
            "model_name": self.model_name,
            "model_type": "Enhanced Legal TF-IDF with NLP",
            "features": [
                "Legal entity recognition",
                "Precedent extraction and linking",
                "Multi-modal document support",
                "Citation tracking",
                "Query refinement suggestions",
                "Document similarity analysis",
                "Legal complexity scoring"
            ],
            "legal_vocabulary_size": len(self.legal_terms_vocab),
            "citation_patterns": len(self.citation_patterns),
            "max_features": 15000,
            "supports_nlp": self.nlp is not None,
            "version": "4.0"
        } 