import os
import sys
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging
import json
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
    
    # Check model endpoint (if configured)
    if settings.model_endpoint:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{settings.model_endpoint}/health")
                if response.status_code == 200:
                    services["model"] = "healthy"
                else:
                    services["model"] = "unhealthy"
        except Exception:
            services["model"] = "checking..."
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
@app.get("/documents")
async def list_documents(current_user: User = Depends(get_current_active_user)):
    """List all documents for the current user."""
    try:
        collection = chroma_manager.collection
        results = collection.get()
        
        if not results["ids"]:
            return {"documents": [], "total": 0}
        
        # Extract document metadata
        documents = []
        for i, doc_id in enumerate(results["ids"]):
            metadata = results["metadatas"][i] if i < len(results["metadatas"]) else {}
            documents.append({
                "id": doc_id,
                "filename": metadata.get("filename", "Unknown"),
                "upload_date": metadata.get("upload_date", "Unknown"),
                "category": metadata.get("category", "general"),
                "source": metadata.get("source", "Unknown")
            })
        
        return {"documents": documents, "total": len(documents)}
    
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
    """Delete a document from ChromaDB."""
    try:
        success = chroma_manager.delete_document(document_id)
        if success:
            return {"success": True, "message": f"Document {document_id} deleted successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found"
            )
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
    
    # Enhanced validation with Phase 4 processor
    if USE_ENHANCED_PROCESSOR:
        supported_formats = enhanced_processor.get_supported_formats()
        if file.content_type not in supported_formats:
            dependencies = enhanced_processor.check_dependencies()
            missing_deps = [k for k, v in dependencies.items() if not v]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type: {file.content_type}. "
                       f"Supported: {supported_formats}. "
                       f"Missing dependencies: {missing_deps}"
            )
    else:
        # Fallback validation
        allowed_types = ["text/plain"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type: {file.content_type}. Enhanced processor not available."
            )
    
    try:
        # Read file content
        content = await file.read()
        
        # Process document with enhanced processor if available
        if USE_ENHANCED_PROCESSOR:
            # Use enhanced document processor
            document_metadata = {
                "source": title or file.filename,
                "category": category,
                "uploaded_by": current_user.username,
                "upload_date": datetime.now().isoformat(),
                "content_type": file.content_type,
                "file_size": len(content)
            }
            
            # Process document with enhanced capabilities
            processed_result = enhanced_processor.process_document(
                file_content=content,
                filename=file.filename,
                content_type=file.content_type,
                metadata=document_metadata
            )
            
            text_content = processed_result['text']
            enhanced_metadata = {**document_metadata, **processed_result}
            
            # Remove the text content from metadata to avoid duplication
            enhanced_metadata.pop('text', None)
            
        else:
            # Fallback to simple text processing
            if file.content_type == "text/plain":
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
                "source": title or file.filename,
                "category": category,
                "uploaded_by": current_user.username,
                "upload_date": datetime.now().isoformat(),
                "content_type": file.content_type,
                "file_size": len(content)
            }
        
        # Get embedder and process document
        embedder = get_embedder()
        
        # Process document using the embedder
        chunks, embeddings = embedder.process_document(
            text=text_content,
            metadata=enhanced_metadata
        )
        
        # Store chunks in ChromaDB
        document_id = None
        chunks_processed = 0
        
        if chunks:
            # Prepare data for ChromaDB
            texts = [chunk['text'] for chunk in chunks]
            metadatas = [chunk['metadata'] for chunk in chunks]
            ids = [chunk['id'] for chunk in chunks]
            
            # Store in ChromaDB
            success = chroma_manager.add_documents(
                texts=texts,
                metadatas=metadatas,
                ids=ids
            )
            
            if success:
                # Use a proper document ID - generate one based on filename and timestamp
                document_base_id = f"{title or file.filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                document_id = document_base_id
                chunks_processed = len(chunks)
                logger.info(f"Successfully stored {chunks_processed} chunks in ChromaDB with document ID: {document_id}")
            else:
                logger.error("Failed to store documents in ChromaDB")
        
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
    """Query legal documents using simple embedder and ChromaDB."""
    try:
        start_time = datetime.now()
        
        # Get embedder for query processing
        embedder = get_embedder()
        
        # Generate query embedding
        query_embedding = embedder.embed_query(request.question)
        
        # Search documents in ChromaDB
        search_results = chroma_manager.search_documents(
            query=request.question,
            n_results=request.num_documents,
            where=request.filter_metadata
        )
        
        # Extract search results
        sources = []
        if search_results and 'documents' in search_results:
            documents = search_results['documents']
            metadatas = search_results.get('metadatas', [])
            distances = search_results.get('distances', [])
            ids = search_results.get('ids', [])
            
            # Flatten nested lists if needed
            if documents and isinstance(documents[0], list):
                documents = documents[0]
            if metadatas and isinstance(metadatas[0], list):
                metadatas = metadatas[0]
            if distances and isinstance(distances[0], list):
                distances = distances[0]
            if ids and isinstance(ids[0], list):
                ids = ids[0]
            
            for i, (doc, meta, distance, doc_id) in enumerate(zip(documents, metadatas, distances, ids)):
                # Safely calculate similarity score
                similarity_score = 0.0
                if distance is not None:
                    try:
                        similarity_score = 1.0 - float(distance)
                    except (TypeError, ValueError):
                        similarity_score = 0.0
                
                sources.append({
                    "document_id": doc_id,
                    "content": doc,
                    "metadata": meta or {},
                    "similarity_score": similarity_score,
                    "chunk_index": i
                })
        
        # Generate a simple answer based on retrieved documents
        if sources:
            # Combine relevant content
            relevant_content = "\n".join([src["content"][:500] for src in sources[:3]])
            answer = f"Based on the retrieved documents: {relevant_content[:1000]}..."
            confidence_score = sources[0]["similarity_score"] if sources else 0.0
        else:
            answer = "I couldn't find any relevant documents to answer your question."
            confidence_score = 0.0
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return RAGQueryResponse(
            answer=answer,
            sources=sources,
            query=request.question,
            total_tokens_used=None,  # Not applicable for TF-IDF
            processing_time=processing_time,
            confidence_score=confidence_score
        )
        
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


