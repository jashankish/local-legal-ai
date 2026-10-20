import os
import sys
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging
import json
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, status, File, UploadFile, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

# Add path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'vector_store'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'rag'))

# Configure logging early
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from backend.config import settings
from backend.auth import user_manager, create_access_token, User, get_current_user, get_current_active_user
from vector_store.chromadb_setup import chroma_manager

# Try to import the enhanced document processor for Phase 4
try:
    from rag.enhanced_document_processor import EnhancedDocumentProcessor
    enhanced_processor = EnhancedDocumentProcessor()
    logger.info("Enhanced document processor loaded (Phase 4)")
    USE_ENHANCED_PROCESSOR = True
except Exception as e:
    logger.warning(f"Enhanced document processor not available: {e}")
    USE_ENHANCED_PROCESSOR = False

# Try to import the sentence-transformers embedder, fallback to simple embedder
try:
    from rag.embedder import get_embedder
    logger.info("Using sentence-transformers embedder")
except Exception as e:
    logger.warning(f"Failed to import sentence-transformers embedder: {e}")
    logger.info("Falling back to simple TF-IDF embedder")
    from rag.simple_embedder import get_simple_embedder as get_embedder

try:
    from rag.rag_pipeline import get_rag_pipeline
    logger.info("RAG pipeline imported successfully")
except Exception as e:
    logger.warning(f"Failed to import RAG pipeline: {e}")
    get_rag_pipeline = None

# HTTPBearer for JWT tokens
security = HTTPBearer()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting Local Legal AI API...")
    
    # Initialize services here if needed
    try:
        # Test ChromaDB connection
        chroma_manager.get_collection_stats()
        logger.info("ChromaDB connection verified")
        
        # Initialize embedder
        embedder = get_embedder()
        logger.info("Embedder initialized")
        
        # Initialize RAG pipeline
        rag_pipeline = get_rag_pipeline()
        logger.info("RAG pipeline initialized")
        
    except Exception as e:
        logger.error(f"Startup error: {e}")
    
    yield
    
    logger.info("Shutting down Local Legal AI API...")

app = FastAPI(
    title="Local Legal AI",
    description="AI-powered legal document analysis and Q&A system",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    role: str = "user"

class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str
    services: Dict[str, str]

class DocumentUploadResponse(BaseModel):
    success: bool
    message: str
    document_id: Optional[str] = None
    chunks_processed: int = 0
    processing_time: float = 0.0

class RAGQueryRequest(BaseModel):
    question: str
    num_documents: int = 5
    filter_metadata: Optional[Dict[str, Any]] = None

class RAGQueryResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]]
    query: str
    total_tokens_used: Optional[int] = None
    processing_time: Optional[float] = None
    confidence_score: Optional[float] = None
    mode: str = "extractive"
    model: Optional[str] = None
    citations: List[int] = []

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Local Legal AI API",
        "version": "1.0.0",
        "status": "healthy"
    }

# Health check endpoint
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    services = {}
    
    # Check API
    services["api"] = "healthy"
    
    # Check ChromaDB
    try:
        chroma_manager.get_collection_stats()
        services["chromadb"] = "healthy"
    except Exception:
        services["chromadb"] = "unhealthy"
    
    # Check the local LLM server. "unreachable" is not fatal: queries fall back
    # to extractive answers until a model is started.
    if get_rag_pipeline is not None:
        llm_status = await get_rag_pipeline().llm.status()
        services["model"] = llm_status.get("state", "unknown")
    else:
        services["model"] = "not_configured"

    return HealthResponse(
        status="healthy",
        version="1.0.0",
        timestamp=datetime.now().isoformat(),
        services=services
    )

# Authentication endpoints
@app.post("/auth/login")
async def login(request: LoginRequest):
    """User login."""
    try:
        user = user_manager.authenticate_user(request.username, request.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        access_token = create_access_token(data={"sub": user["username"]})
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "username": user["username"],
                "email": user["email"],
                "role": user["role"],
                "is_active": user["is_active"]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )

@app.post("/auth/register")
async def register(request: RegisterRequest, current_user: User = Depends(get_current_active_user)):
    """User registration (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    try:
        from backend.auth import UserCreate
        user_data = UserCreate(
            username=request.username,
            password=request.password,
            email=request.email,
            role=request.role
        )
        user = user_manager.create_user(user_data)
        return {
            "message": "User created successfully",
            "user": {
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active
            }
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )

@app.get("/auth/me")
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """Get current user information."""
    return {
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role,
        "is_active": current_user.is_active
    }

# Document management endpoints
def _group_chunks_by_document() -> Dict[str, Dict[str, Any]]:
    """Collapse stored chunks into one record per uploaded document."""
    results = chroma_manager.collection.get(include=["metadatas"])
    grouped: Dict[str, Dict[str, Any]] = {}
    for chunk_id, metadata in zip(results.get("ids", []), results.get("metadatas", [])):
        metadata = metadata or {}
        # Chunks stored before document_id existed are grouped by their source name.
        doc_id = metadata.get("document_id") or metadata.get("source") or chunk_id
        entry = grouped.setdefault(doc_id, {
            "id": doc_id,
            "filename": metadata.get("filename") or metadata.get("source", "Unknown"),
            "source": metadata.get("source", "Unknown"),
            "category": metadata.get("category", "general"),
            "upload_date": metadata.get("upload_date", "Unknown"),
            "uploaded_by": metadata.get("uploaded_by", "Unknown"),
            "content_type": metadata.get("content_type", "text/plain"),
            "file_size": metadata.get("file_size", 0),
            "document_type": metadata.get("legal_document_type") or metadata.get("document_type", "general"),
            "page_count": metadata.get("page_count"),
            "word_count": metadata.get("word_count"),
            "chunk_count": 0,
            "chunk_ids": [],
        })
        entry["chunk_count"] += 1
        entry["chunk_ids"].append(chunk_id)
    return grouped


@app.get("/documents")
async def list_documents(current_user: User = Depends(get_current_active_user)):
    """List uploaded documents (one entry per file, not per chunk)."""
    try:
        grouped = _group_chunks_by_document()
        documents = sorted(grouped.values(), key=lambda d: str(d.get("upload_date", "")), reverse=True)
        for doc in documents:
            doc.pop("chunk_ids", None)
        return {
            "documents": documents,
            "total": len(documents),
            "total_chunks": sum(d["chunk_count"] for d in documents),
        }
    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve documents")

@app.get("/documents/stats")
async def get_document_stats(current_user: User = Depends(get_current_active_user)):
    """Get detailed document statistics."""
    try:
        stats = chroma_manager.get_collection_stats()
        return stats
    except Exception as e:
        logger.error(f"Error getting document stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get document statistics"
        )

@app.delete("/documents/{document_id}")
async def delete_document(document_id: str, current_user: User = Depends(get_current_active_user)):
    """Delete an uploaded document and all of its chunks."""
    grouped = _group_chunks_by_document()
    document = grouped.get(document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found"
        )
    if current_user.role != "admin" and document.get("uploaded_by") != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the uploader or an admin can delete this document"
        )
    try:
        chroma_manager.collection.delete(ids=document["chunk_ids"])
        logger.info(f"Deleted document {document_id} ({len(document['chunk_ids'])} chunks)")
        return {
            "success": True,
            "message": f"Document '{document['filename']}' deleted",
            "chunks_deleted": len(document["chunk_ids"]),
        }
    except Exception as e:
        logger.error(f"Delete document error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {str(e)}"
        )

# Document upload endpoint
@app.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    category: Optional[str] = Form("general"),
    current_user: User = Depends(get_current_active_user)
):
    """Upload and process a legal document with enhanced Phase 4 capabilities."""
    start_time = datetime.now()
    
    # Fix content type detection - browser might send wrong MIME type
    content_type = file.content_type
    filename = file.filename or ""
    
    # Override content type based on file extension if needed
    if filename.lower().endswith('.pdf'):
        content_type = 'application/pdf'
        logger.info(f"Corrected content type for {filename}: {content_type}")
    elif filename.lower().endswith('.docx'):
        content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        logger.info(f"Corrected content type for {filename}: {content_type}")
    elif filename.lower().endswith('.txt'):
        content_type = 'text/plain'
    
    logger.info(f"Processing file: {filename}, Content type: {content_type}")
    
    # Enhanced validation with Phase 4 processor
    if USE_ENHANCED_PROCESSOR:
        supported_formats = enhanced_processor.get_supported_formats()
        if content_type not in supported_formats:
            dependencies = enhanced_processor.check_dependencies()
            missing_deps = [k for k, v in dependencies.items() if not v]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type: {content_type}. "
                       f"Supported: {supported_formats}. "
                       f"Missing dependencies: {missing_deps}"
            )
    else:
        # Fallback validation
        allowed_types = ["text/plain"]
        if content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type: {content_type}. Enhanced processor not available."
            )
    
    try:
        # Read file content
        content = await file.read()
        max_bytes = settings.max_file_size_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds the {settings.max_file_size_mb} MB upload limit"
            )
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty")

        document_id = uuid.uuid4().hex[:16]
        logger.info(f"Read {len(content)} bytes from {filename}")
        
        # Process document with enhanced processor if available
        if USE_ENHANCED_PROCESSOR:
            # Use enhanced document processor
            document_metadata = {
                "document_id": document_id,
                "filename": file.filename,
                "source": title or file.filename,
                "category": category,
                "uploaded_by": current_user.username,
                "upload_date": datetime.now().isoformat(),
                "content_type": content_type,  # Use corrected content type
                "file_size": len(content)
            }
            
            logger.info(f"Processing with enhanced processor: {content_type}")
            
            # Process document with enhanced capabilities
            processed_result = enhanced_processor.process_document(
                file_content=content,
                filename=file.filename,
                content_type=content_type,  # Use corrected content type
                metadata=document_metadata
            )
            
            text_content = processed_result['text']
            enhanced_metadata = {**document_metadata, **processed_result}
            
            # Remove the text content from metadata to avoid duplication
            enhanced_metadata.pop('text', None)
            
            logger.info(f"Enhanced processing complete. Text length: {len(text_content)}, "
                       f"Extraction method: {enhanced_metadata.get('extraction_method', 'unknown')}")
            
        else:
            # Fallback to simple text processing
            if content_type == "text/plain":
                text_content = content.decode('utf-8')
            else:
                try:
                    text_content = content.decode('utf-8', errors='ignore')
                except Exception:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Could not process file content. Please ensure it's a valid text file."
                    )
            
            enhanced_metadata = {
                "document_id": document_id,
                "filename": file.filename,
                "source": title or file.filename,
                "category": category,
                "uploaded_by": current_user.username,
                "upload_date": datetime.now().isoformat(),
                "content_type": content_type,
                "file_size": len(content)
            }
        
        # Validate that we have actual text content, not binary data
        if text_content and text_content.startswith('%PDF'):
            logger.error(f"ERROR: Text content appears to be raw PDF binary data for {filename}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="PDF text extraction failed - raw binary data detected"
            )
        
        # Get embedder and process document
        embedder = get_embedder()
        
        # Process document using the embedder
        # Chunk only: ChromaDB computes vectors with the collection's embedding function.
        chunks, _ = embedder.process_document(
            text=text_content,
            metadata=enhanced_metadata,
            return_embeddings=False
        )
        
        # Store chunks in ChromaDB
        chunks_processed = 0
        
        if chunks:
            # Prepare data for ChromaDB
            texts = [chunk['text'] for chunk in chunks]
            # ChromaDB metadata values must be scalars
            metadatas = [
                {k: v for k, v in chunk['metadata'].items() if isinstance(v, (str, int, float, bool))}
                for chunk in chunks
            ]
            ids = [f"{document_id}-{i:04d}" for i in range(len(chunks))]
            
            # Store in ChromaDB
            success = chroma_manager.add_documents(
                texts=texts,
                metadatas=metadatas,
                ids=ids
            )
            
            if success:
                chunks_processed = len(chunks)
                logger.info(f"Successfully stored {chunks_processed} chunks in ChromaDB with document ID: {document_id}")
            else:
                logger.error("Failed to store documents in ChromaDB")
                raise RuntimeError("Vector store rejected the document chunks")
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # Enhanced response with processing details
        processor_info = "Enhanced Processor (Phase 4)" if USE_ENHANCED_PROCESSOR else "Basic Processor"
        success_message = f"Document '{title or file.filename}' processed successfully using {processor_info}"
        
        return DocumentUploadResponse(
            success=True,
            message=success_message,
            document_id=document_id,
            chunks_processed=chunks_processed,
            processing_time=processing_time
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document upload error: {e}")
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return DocumentUploadResponse(
            success=False,
            message=f"Failed to process document: {str(e)}",
            processing_time=processing_time
        )

# RAG Query endpoints
@app.post("/query", response_model=RAGQueryResponse)
async def query_documents(
    request: RAGQueryRequest,
    current_user: User = Depends(get_current_active_user)
):
    """Answer a question from the document corpus via the RAG pipeline."""
    if not request.question.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Question cannot be empty")
    if get_rag_pipeline is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="RAG pipeline unavailable")
    try:
        result = await get_rag_pipeline().query(
            question=request.question,
            num_documents=max(1, min(request.num_documents, 20)),
            filter_metadata=request.filter_metadata
        )
        sources = [
            {
                "document_id": src.metadata.get("document_id", src.document_id),
                "chunk_id": src.document_id,
                "content": src.content,
                "metadata": src.metadata,
                "similarity_score": src.similarity_score,
                "chunk_index": src.chunk_index,
            }
            for src in result.sources
        ]
        return RAGQueryResponse(
            answer=result.answer,
            sources=sources,
            query=request.question,
            total_tokens_used=result.total_tokens_used,
            processing_time=result.processing_time,
            confidence_score=result.confidence_score,
            mode=result.mode,
            model=result.model,
            citations=result.citations,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Query error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query processing failed: {str(e)}"
        )

# Alternative query endpoint for frontend compatibility
@app.post("/documents/query")
async def query_documents_alt(
    request: dict,
    current_user: User = Depends(get_current_active_user)
):
    """Alternative query endpoint for frontend compatibility."""
    try:
        # Convert request format
        rag_request = RAGQueryRequest(
            question=request.get("query", ""),
            num_documents=request.get("max_results", 5),
            filter_metadata=None
        )
        
        # Use the main query function
        response = await query_documents(rag_request, current_user)
        
        # Convert response to expected format
        return {
            "answer": response.answer,
            "sources": [
                {
                    "document_id": src.get("document_id"),
                    "source": src.get("metadata", {}).get("source", "Unknown"),
                    "text": src["content"],
                    "similarity": src["similarity_score"],
                    "chunk_index": src.get("chunk_index", 0),
                    "category": src.get("metadata", {}).get("category", "general")
                }
                for src in response.sources
            ],
            "confidence": response.confidence_score or 0.0,
            "processing_time": response.processing_time or 0.0,
            "mode": response.mode,
            "model": response.model,
            "citations": response.citations,
            "legal_entities": {},  # Placeholder for enhanced features
            "query_suggestions": []  # Placeholder for enhanced features
        }
        
    except Exception as e:
        logger.error(f"Alternative query error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query processing failed: {str(e)}"
        )

# Analytics endpoints
@app.get("/analytics/usage")
async def get_usage_analytics(
    days: int = 7,
    current_user: User = Depends(get_current_active_user)
):
    """Get usage analytics for the specified number of days."""
    try:
        # Check admin access
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required for analytics"
            )
        
        # Mock analytics data - in a real system, this would come from a database
        return {
            "data": {
                "query_analytics": {
                    "total_queries": 42,
                    "unique_users": 5,
                    "avg_similarity_score": 0.75,
                    "avg_processing_time": 1.2
                },
                "document_analytics": {
                    "total_documents": 3,
                    "total_chunks": 15,
                    "avg_chunks_per_doc": 5.0
                },
                "daily_trends": [
                    {"date": "2025-05-25", "queries": 8, "documents": 1},
                    {"date": "2025-05-26", "queries": 12, "documents": 0},
                    {"date": "2025-05-27", "queries": 15, "documents": 2},
                    {"date": "2025-05-28", "queries": 7, "documents": 0}
                ],
                "top_query_types": [
                    {"type": "Document Summary", "count": 18},
                    {"type": "Legal Analysis", "count": 15},
                    {"type": "Compliance Check", "count": 9}
                ]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Usage analytics error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch usage analytics: {str(e)}"
        )

@app.get("/analytics/performance")
async def get_performance_analytics(
    current_user: User = Depends(get_current_active_user)
):
    """Get performance analytics."""
    try:
        # Check admin access
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required for analytics"
            )
        
        # Mock performance data
        return {
            "data": {
                "response_times": {
                    "avg_query_time": 1.2,
                    "avg_upload_time": 3.1,
                    "avg_processing_time": 2.4
                },
                "system_metrics": {
                    "uptime": "7 days, 12 hours",
                    "total_requests": 234,
                    "error_rate": 0.02
                },
                "performance_trends": [
                    {"hour": "00:00", "avg_response_time": 1.1, "requests": 5},
                    {"hour": "06:00", "avg_response_time": 1.3, "requests": 12},
                    {"hour": "12:00", "avg_response_time": 1.8, "requests": 25},
                    {"hour": "18:00", "avg_response_time": 1.4, "requests": 18}
                ]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Performance analytics error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch performance analytics: {str(e)}"
        )

@app.get("/analytics/similarity")
async def get_similarity_analytics(
    document_id: Optional[str] = None,
    current_user: User = Depends(get_current_active_user)
):
    """Get document similarity analytics."""
    try:
        # Check admin access
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required for analytics"
            )
        
        # Mock similarity data
        return {
            "data": {
                "similarity_matrix": [
                    {"doc1": "contract_1.txt", "doc2": "contract_2.txt", "similarity": 0.85},
                    {"doc1": "contract_1.txt", "doc2": "policy_1.txt", "similarity": 0.62},
                    {"doc1": "contract_2.txt", "doc2": "policy_1.txt", "similarity": 0.71}
                ],
                "cluster_analysis": {
                    "num_clusters": 3,
                    "cluster_sizes": [5, 3, 2]
                }
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Similarity analytics error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch similarity analytics: {str(e)}"
        )

@app.get("/analytics/activity")
async def get_activity_analytics(
    days: int = 7,
    current_user: User = Depends(get_current_active_user)
):
    """Get user activity analytics."""
    try:
        # Check admin access
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required for analytics"
            )
        
        # Mock activity data
        return {
            "data": {
                "user_activity": [
                    {"user": "admin", "queries": 25, "documents_uploaded": 2, "last_active": "2025-05-31T10:30:00"},
                    {"user": "user1", "queries": 12, "documents_uploaded": 1, "last_active": "2025-05-30T14:15:00"},
                    {"user": "user2", "queries": 8, "documents_uploaded": 0, "last_active": "2025-05-29T09:45:00"}
                ],
                "activity_patterns": {
                    "peak_hours": ["09:00-11:00", "14:00-16:00"],
                    "active_days": ["Monday", "Tuesday", "Wednesday"]
                },
                "engagement_metrics": {
                    "avg_session_duration": 25.5,
                    "avg_queries_per_session": 4.2,
                    "return_rate": 0.78
                }
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Activity analytics error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch activity analytics: {str(e)}"
        )

@app.get("/analytics/report")
async def generate_analytics_report(
    format: str = "json",
    current_user: User = Depends(get_current_active_user)
):
    """Generate comprehensive analytics report."""
    try:
        # Check admin access
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required for analytics"
            )
        
        # Generate comprehensive report
        report = {
            "report_generated": datetime.now().isoformat(),
            "report_period": "Last 7 days",
            "usage_analytics": {
                "query_analytics": {
                    "total_queries": 42,
                    "unique_users": 5,
                    "avg_similarity_score": 0.75,
                    "avg_processing_time": 1.2
                },
                "document_analytics": {
                    "total_documents": 3,
                    "total_chunks": 15,
                    "avg_chunks_per_doc": 5.0
                }
            },
            "performance_analytics": {
                "response_times": {
                    "avg_query_time": 1.2,
                    "avg_upload_time": 3.1,
                    "avg_processing_time": 2.4
                },
                "system_metrics": {
                    "uptime": "7 days, 12 hours",
                    "total_requests": 234,
                    "error_rate": 0.02
                }
            },
            "user_activity": {
                "active_users": 5,
                "avg_session_duration": 25.5,
                "peak_usage_hours": ["09:00-11:00", "14:00-16:00"]
            }
        }
        
        return report
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Report generation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate report: {str(e)}"
        )

@app.get("/documents/list")
async def list_documents_alt(current_user: User = Depends(get_current_active_user)):
    """Alternative endpoint for listing documents - same as /documents"""
    return await list_documents(current_user)

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )


