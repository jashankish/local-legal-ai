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
    """List all documents in the vector store."""
    try:
        stats = chroma_manager.get_collection_stats()
        return {
            "total_documents": stats.get("count", 0),
            "collection_name": chroma_manager.collection_name,
            "status": "healthy"
        }
    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list documents"
        )

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
    """Delete a document (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    try:
        success = chroma_manager.delete_document(document_id)
        if success:
            return {"message": f"Document {document_id} deleted successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document"
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
                document_id = ids[0] if ids else None  # Use first chunk ID as document ID
                chunks_processed = len(chunks)
                logger.info(f"Successfully stored {chunks_processed} chunks in ChromaDB")
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

@app.post("/query/stream")
async def stream_query(
    request: RAGQueryRequest,
    current_user: User = Depends(get_current_active_user)
):
    """Stream RAG query response for real-time updates."""
    try:
        rag_pipeline = get_rag_pipeline()
        
        async def generate_stream():
            async for chunk in rag_pipeline.stream_query(
                question=request.question,
                num_documents=request.num_documents,
                filter_metadata=request.filter_metadata
            ):
                yield f"data: {json.dumps(chunk)}\n\n"
        
        return StreamingResponse(
            generate_stream(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
        
    except Exception as e:
        logger.error(f"Stream query error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stream query failed: {str(e)}"
        )

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )


