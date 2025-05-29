from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from datetime import timedelta
import logging

from .config import settings
from .auth import (
    user_manager, create_access_token, get_current_active_user, 
    require_admin, check_ip_whitelist, UserLogin, UserCreate, Token, User
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(settings.log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="A fully private, self-hosted LLM-powered assistant for law firms"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

@app.get("/")
def read_root():
    """Root endpoint with basic information."""
    return {
        "message": "Local Legal AI API",
        "version": settings.app_version,
        "status": "healthy"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        # Check ChromaDB connection
        from vector_store.chromadb_setup import chroma_manager
        chromadb_healthy = chroma_manager.health_check()
        
        return {
            "status": "healthy",
            "version": settings.app_version,
            "services": {
                "api": "healthy",
                "chromadb": "healthy" if chromadb_healthy else "unhealthy",
                "model": "checking..."  # Will be updated when model is integrated
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unhealthy"
        )

# Authentication endpoints
@app.post("/auth/login", response_model=Token)
async def login(request: Request, user_credentials: UserLogin):
    """Authenticate user and return JWT token."""
    # Check IP whitelist
    check_ip_whitelist(request)
    
    user = user_manager.authenticate_user(
        user_credentials.username, 
        user_credentials.password
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user["username"], "role": user["role"]},
        expires_delta=access_token_expires
    )
    
    # Convert user dict to User model (excluding password)
    user_model = User(**{k: v for k, v in user.items() if k != "hashed_password"})
    
    logger.info(f"User {user['username']} logged in successfully")
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
        user=user_model
    )

@app.post("/auth/register", response_model=User)
async def register(request: Request, user_data: UserCreate, current_user: User = Depends(require_admin)):
    """Register a new user (admin only)."""
    check_ip_whitelist(request)
    
    try:
        new_user = user_manager.create_user(user_data)
        logger.info(f"New user {new_user.username} created by {current_user.username}")
        return new_user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"User registration failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )

@app.get("/auth/me", response_model=User)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """Get current user information."""
    return current_user

@app.get("/auth/users")
async def list_users(current_user: User = Depends(require_admin)):
    """List all users (admin only)."""
    users = user_manager._load_users()
    return [
        {k: v for k, v in user.items() if k != "hashed_password"}
        for user in users.values()
    ]

# Document management endpoints (placeholders for Phase 2)
@app.get("/documents")
async def list_documents(
    limit: int = 10,
    offset: int = 0,
    current_user: User = Depends(get_current_active_user)
):
    """List documents in the vector store."""
    try:
        from vector_store.chromadb_setup import chroma_manager
        documents = chroma_manager.list_documents(limit=limit, offset=offset)
        return {
            "documents": documents,
            "total": len(documents),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve documents"
        )

@app.get("/documents/stats")
async def get_document_stats(current_user: User = Depends(get_current_active_user)):
    """Get document collection statistics."""
    try:
        from vector_store.chromadb_setup import chroma_manager
        stats = chroma_manager.get_collection_stats()
        return stats
    except Exception as e:
        logger.error(f"Failed to get document stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve statistics"
        )

@app.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    current_user: User = Depends(require_admin)
):
    """Delete a document (admin only)."""
    try:
        from vector_store.chromadb_setup import chroma_manager
        success = chroma_manager.delete_document(doc_id)
        
        if success:
            logger.info(f"Document {doc_id} deleted by {current_user.username}")
            return {"message": "Document deleted successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete document {doc_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document"
        )

# Configuration endpoint
@app.get("/config")
async def get_config(current_user: User = Depends(require_admin)):
    """Get application configuration (admin only)."""
    return {
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "chromadb_collection": settings.chromadb_collection_name,
        "model_endpoint": settings.model_endpoint,
        "max_file_size_mb": settings.max_file_size_mb,
        "supported_file_types": settings.supported_file_types,
        "embedding_model": settings.embedding_model
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )


