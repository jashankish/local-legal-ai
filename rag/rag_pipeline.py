# RAG Pipeline for Legal Document Q&A
#
# Retrieval runs against ChromaDB; generation is delegated to any
# OpenAI-compatible chat endpoint running locally (vLLM, Ollama, llama.cpp
# server, LM Studio). When no model is reachable the pipeline degrades to an
# extractive answer built from the highest-scoring sentences, so the product
# stays usable on machines without a GPU.

import logging
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
import re
import sys
import os
import time
import httpx
from dataclasses import dataclass, asdict, field

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'vector_store'))

from config import settings
from chromadb_setup import chroma_manager

logger = logging.getLogger(__name__)

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for",
    "from", "has", "have", "how", "i", "if", "in", "is", "it", "of", "on", "or",
    "shall", "that", "the", "this", "to", "under", "was", "what", "when", "where",
    "which", "who", "will", "with", "would", "any", "there", "their", "my", "our",
}


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
    mode: str = "extractive"            # "generative" when an LLM produced the answer
    model: Optional[str] = None
    citations: List[int] = field(default_factory=list)


class LLMClient:
    """Minimal client for an OpenAI-compatible /v1/chat/completions endpoint."""

    STATUS_TTL_SECONDS = 30

    def __init__(self, endpoint: str, model_name: str, timeout: float):
        self.endpoint = (endpoint or "").rstrip("/")
        self.model_name = model_name
        self.timeout = timeout
        self._status_cache: Tuple[float, Dict[str, Any]] = (0.0, {})

    @property
    def configured(self) -> bool:
        return bool(self.endpoint) and settings.llm_enabled

    async def status(self, force: bool = False) -> Dict[str, Any]:
        """Report whether the model server is reachable and which models it serves."""
        if not self.configured:
            return {"available": False, "state": "not_configured", "endpoint": self.endpoint}

        checked_at, cached = self._status_cache
        if not force and cached and time.time() - checked_at < self.STATUS_TTL_SECONDS:
            return cached

        result: Dict[str, Any] = {"endpoint": self.endpoint, "model": self.model_name}
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self.endpoint}/v1/models")
            if response.status_code == 200:
                served = [m.get("id") for m in response.json().get("data", [])]
                result.update(available=True, state="healthy", served_models=served)
            else:
                result.update(available=False, state=f"http_{response.status_code}")
        except Exception as e:
            result.update(available=False, state="unreachable", error=type(e).__name__)

        self._status_cache = (time.time(), result)
        return result

    async def chat(self, messages: List[Dict[str, str]]) -> Tuple[str, Optional[int], str]:
        """Return (content, total_tokens, served_model)."""
        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": settings.max_tokens,
            "temperature": settings.temperature,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.endpoint}/v1/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        tokens = (data.get("usage") or {}).get("total_tokens")
        return content.strip(), tokens, data.get("model", self.model_name)


class LegalRAGPipeline:
    """RAG Pipeline specialized for legal document Q&A."""

    def __init__(self):
        """Initialize the RAG pipeline."""
        self.chroma_manager = chroma_manager
        self.llm = LLMClient(
            endpoint=settings.model_endpoint,
            model_name=settings.model_name,
            timeout=settings.llm_timeout_seconds,
        )

        self.system_prompt = """You are a legal research assistant used inside a law firm. \
Answer strictly from the numbered document excerpts you are given.

Rules:
1. Cite every factual statement with the excerpt number in square brackets, e.g. [1] or [2][3].
2. If the excerpts do not contain the answer, say so plainly. Never invent facts, parties, dates, or citations.
3. Quote short operative language (dollar amounts, notice periods, defined terms) exactly.
4. Use precise legal terminology and keep the answer structured: a direct answer first, then supporting detail.
5. Flag material risks, ambiguities, or obligations a reviewing attorney should check.
6. You do not provide legal advice; you summarize what the documents say."""

        self.context_template = """DOCUMENT EXCERPTS:
{context}

QUESTION: {question}

Answer using only the excerpts above, citing them by number."""

    async def retrieve_documents(self,
                                 query: str,
                                 num_results: int = 5,
                                 filter_metadata: Optional[Dict] = None) -> List[RetrievalResult]:
        """Retrieve relevant chunks using semantic search."""
        logger.info(f"Retrieving documents for query: {query[:100]}...")

        search_results = self.chroma_manager.search_documents(
            query=query,
            n_results=num_results,
            where=filter_metadata or None,
            include=["documents", "metadatas", "distances"]
        ) or {}

        def first(key):
            values = search_results.get(key) or [[]]
            return values[0] if values and isinstance(values[0], list) else (values or [])

        documents, metadatas = first('documents'), first('metadatas')
        distances, ids = first('distances'), first('ids')

        retrieval_results = []
        for i, (doc, metadata, distance, doc_id) in enumerate(zip(documents, metadatas, distances, ids)):
            metadata = metadata or {}
            retrieval_results.append(RetrievalResult(
                document_id=doc_id,
                content=doc or "",
                metadata=metadata,
                similarity_score=self._distance_to_similarity(distance),
                chunk_index=metadata.get('chunk_index', i)
            ))

        logger.info(f"Retrieved {len(retrieval_results)} relevant chunks")
        return retrieval_results

    @staticmethod
    def _distance_to_similarity(distance: Optional[float]) -> float:
        """Map a ChromaDB L2/cosine distance onto a 0-1 similarity score."""
        if distance is None:
            return 0.0
        try:
            return max(0.0, min(1.0, 1.0 - float(distance) / 2.0))
        except (TypeError, ValueError):
            return 0.0

    def _format_context(self, retrieval_results: List[RetrievalResult]) -> str:
        """Format retrieved chunks into numbered excerpts for the LLM."""
        parts = []
        for i, result in enumerate(retrieval_results, 1):
            source = result.metadata.get('source', f'Document {i}')
            section = result.metadata.get('section_num')
            label = f"[{i}] {source}" + (f", section {section}" if section not in (None, "") else "")
            parts.append(f"{label}\n{result.content}")
        return "\n\n".join(parts)

    @staticmethod
    def _keywords(text: str) -> set:
        return {w for w in re.findall(r"[a-z0-9$%]+", text.lower()) if w not in STOPWORDS and len(w) > 2}

    def _generate_extractive_response(self, query: str,
                                      retrieval_results: List[RetrievalResult]) -> Tuple[str, List[int]]:
        """Build an answer from the most relevant sentences when no LLM is available."""
        query_terms = self._keywords(query)
        scored = []
        for source_num, result in enumerate(retrieval_results, 1):
            sentences = re.split(r'(?<=[.;:])\s+(?=[A-Z(\d])', result.content)
            for position, sentence in enumerate(sentences):
                sentence = sentence.strip()
                if len(sentence) < 25:
                    continue
                overlap = len(query_terms & self._keywords(sentence))
                # Prefer sentences that share terms with the question, then higher-ranked sources.
                score = overlap * 2 + result.similarity_score - position * 0.01
                scored.append((score, overlap, source_num, sentence))

        scored.sort(key=lambda item: item[0], reverse=True)
        # Keep supporting sentences only if they match at least half as many
        # question terms as the best sentence, so incidental hits are dropped.
        min_overlap = max(1, (scored[0][1] + 1) // 2) if scored else 1
        picked, seen = [], set()
        for score, overlap, source_num, sentence in scored:
            key = sentence[:80]
            if key in seen:
                continue
            if picked and overlap < min_overlap:
                continue
            seen.add(key)
            picked.append((source_num, sentence))
            if len(picked) == 4:
                break

        if not picked:
            return ("The retrieved documents do not appear to address this question directly. "
                    "Try rephrasing, or upload the relevant agreement."), []

        # The response's `mode` field tells clients this is an extractive answer.
        lines = ["**Most relevant passages from your documents:**", ""]
        for source_num, sentence in picked:
            if len(sentence) > 400:
                sentence = sentence[:400].rsplit(" ", 1)[0] + "…"
            lines.append(f"- {sentence} [{source_num}]")
        citations = sorted({num for num, _ in picked})
        return "\n".join(lines), citations

    @staticmethod
    def _extract_citations(answer: str, num_sources: int) -> List[int]:
        found = {int(n) for n in re.findall(r"\[(\d{1,2})\]", answer)}
        return sorted(n for n in found if 1 <= n <= num_sources)

    def _calculate_confidence(self, retrieval_results: List[RetrievalResult], query: str) -> float:
        """Blend retrieval similarity with lexical coverage of the question."""
        if not retrieval_results:
            return 0.0
        top = retrieval_results[:3]
        avg_similarity = sum(r.similarity_score for r in top) / len(top)
        query_terms = self._keywords(query)
        if query_terms:
            covered = set()
            for r in top:
                covered |= query_terms & self._keywords(r.content)
            coverage = len(covered) / len(query_terms)
        else:
            coverage = 0.0
        return round(min(1.0, avg_similarity * 0.6 + coverage * 0.4), 3)

    async def query(self,
                    question: str,
                    num_documents: int = 5,
                    filter_metadata: Optional[Dict] = None) -> RAGResponse:
        """Process a legal question through retrieval and generation."""
        start_time = datetime.now()
        logger.info(f"Processing RAG query: {question[:100]}...")

        retrieval_results = await self.retrieve_documents(
            query=question,
            num_results=num_documents,
            filter_metadata=filter_metadata
        )

        if not retrieval_results:
            return RAGResponse(
                answer="I couldn't find any documents to answer this question. "
                       "Upload agreements, filings, or policies on the Documents page first.",
                sources=[],
                query=question,
                confidence_score=0.0,
                processing_time=(datetime.now() - start_time).total_seconds(),
            )

        answer, tokens_used, mode, model, citations = None, None, "extractive", None, []
        llm_status = await self.llm.status()
        if llm_status.get("available"):
            try:
                answer, tokens_used, model = await self.llm.chat([
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": self.context_template.format(
                        context=self._format_context(retrieval_results), question=question)},
                ])
                mode = "generative"
                citations = self._extract_citations(answer, len(retrieval_results))
            except Exception as e:
                logger.error(f"LLM generation failed, falling back to extractive answer: {e}")
                answer = None

        if answer is None:
            answer, citations = self._generate_extractive_response(question, retrieval_results)

        processing_time = (datetime.now() - start_time).total_seconds()
        confidence = self._calculate_confidence(retrieval_results, question)
        logger.info(f"RAG query completed in {processing_time:.2f}s ({mode}) with confidence {confidence:.2f}")

        return RAGResponse(
            answer=answer,
            sources=retrieval_results,
            query=question,
            total_tokens_used=tokens_used,
            processing_time=processing_time,
            confidence_score=confidence,
            mode=mode,
            model=model,
            citations=citations,
        )

    async def stream_query(self,
                           question: str,
                           num_documents: int = 5,
                           filter_metadata: Optional[Dict] = None):
        """Yield progress events followed by the final answer."""
        try:
            yield {"status": "retrieving", "message": "Searching legal documents..."}
            response = await self.query(question, num_documents, filter_metadata)
            yield {"status": "retrieved", "sources": [asdict(r) for r in response.sources]}
            yield {
                "status": "complete",
                "answer": response.answer,
                "confidence": response.confidence_score,
                "tokens_used": response.total_tokens_used,
                "mode": response.mode,
            }
        except Exception as e:
            logger.error(f"Streaming RAG failed: {e}")
            yield {"status": "error", "message": str(e)}


# Global RAG pipeline instance
rag_pipeline = LegalRAGPipeline()


def get_rag_pipeline() -> LegalRAGPipeline:
    """Get the global RAG pipeline instance."""
    return rag_pipeline
