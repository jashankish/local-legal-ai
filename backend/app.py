import os
import sys
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging
import json
import uuid
import re
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, status, File, UploadFile, Form, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, Response
import numpy as np
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
from backend.auth import (
    user_manager, User, get_current_user, get_current_active_user, get_current_user_pending_ok,
    require_admin, ip_whitelist, issue_token, validate_new_password, login_throttle,
)
from backend.analytics import AnalyticsManager, QueryMetrics, DocumentMetrics, classify_query
from rag.legal_insights import extract_legal_entities, suggest_follow_ups
from rag.ocr import ocr_available
from security.audit_log import get_audit_logger, request_context
from backend.integrations import EventNotifier
from backend.folder_watcher import FolderWatcher
from vector_store.chromadb_setup import chroma_manager

analytics_manager = AnalyticsManager()
audit = get_audit_logger()
notifier = EventNotifier(
    n8n_url=settings.n8n_webhook_url,
    slack_url=settings.slack_webhook_url,
    secret=settings.webhook_secret,
    events=settings.notify_events.split(","),
    instance_name=settings.app_name,
)
inbox_watcher: Optional[FolderWatcher] = None

USERNAME_PATTERN = re.compile(r"[A-Za-z0-9._-]{3,32}")

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

    global inbox_watcher
    if settings.inbox_enabled:
        try:
            inbox_watcher = FolderWatcher(
                settings.inbox_dir, ingest_document,
                interval_seconds=settings.inbox_poll_seconds,
                on_failure=lambda name, category, error: track(
                    "inbox", "document.upload", "failure",
                    details={"filename": name, "category": category, "error": error[:200], "channel": "inbox"}),
            )
            inbox_watcher.start()
        except OSError as e:
            # e.g. a bind-mounted folder the service user can't write to; the rest of the app still works
            logger.error(f"Inbox watcher disabled: cannot use {settings.inbox_dir}: {e}")
            inbox_watcher = None

    yield

    logger.info("Shutting down Local Legal AI API...")
    if inbox_watcher:
        inbox_watcher.stop()
    notifier.flush(timeout=5)
    notifier.stop()

app = FastAPI(
    title="Local Legal AI",
    description="AI-powered legal document analysis and Q&A system",
    version="1.0.0",
    lifespan=lifespan
)

# CORS: the Streamlit UI calls the API server-side, so only the local UI
# origins need browser access.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def access_control_middleware(request: Request, call_next):
    """Enforce ALLOWED_IPS and expose client details to the audit logger."""
    client_ip = request.client.host if request.client else "unknown"
    token = request_context.set({
        "ip": client_ip,
        "user_agent": request.headers.get("user-agent", ""),
    })
    try:
        if not ip_whitelist.is_allowed(client_ip):
            track(None, "access.ip_denied", "denied", resource=request.url.path)
            return JSONResponse(status_code=status.HTTP_403_FORBIDDEN,
                                content={"detail": "IP address not allowed"})
        return await call_next(request)
    finally:
        request_context.reset(token)


def track(user: Optional[str], action: str, status_: str = "success",
          resource: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
    """Record an event in the audit trail, the analytics activity feed and outbound notifications."""
    audit.record(action, username=user, status=status_, resource=resource, details=details)
    if user and status_ == "success":
        analytics_manager.log_user_activity(user, action, details)
    notifier.notify_action(action, status_, actor=user, resource=resource, details=details,
                           ip=request_context.get().get("ip"))

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    role: str = "user"
    must_change_password: bool = True  # new accounts pick their own password at first sign-in

class UserUpdateRequest(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

class PasswordResetRequest(BaseModel):
    new_password: str

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

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
    legal_entities: Dict[str, List[str]] = {}
    query_suggestions: List[str] = []

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
    services["ocr"] = "available" if ocr_available() else "not_installed"

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
    client_ip = request_context.get().get("ip")
    try:
        wait = login_throttle.retry_after(request.username, client_ip)
        if wait:
            track(request.username, "auth.login", "locked",
                  details={"reason": "too_many_failures", "retry_after_seconds": wait})
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed sign-in attempts. Try again in {max(1, round(wait / 60))} minute(s).",
                headers={"Retry-After": str(wait)},
            )

        user = user_manager.authenticate_user(request.username, request.password)
        if not user:
            remaining = login_throttle.record_failure(request.username, client_ip)
            track(request.username, "auth.login", "failure",
                  details={"reason": "bad_credentials", "attempts_remaining": remaining})
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        login_throttle.reset(request.username, client_ip)
        if not user.get("is_active", True):
            track(request.username, "auth.login", "denied", details={"reason": "account_disabled"})
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This account has been disabled. Contact an administrator."
            )

        previous_login = user.get("last_login")
        user = user_manager.update_user(user["username"], last_login=datetime.utcnow().isoformat())
        access_token = issue_token(user)
        track(user["username"], "auth.login")
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "username": user["username"],
                "email": user.get("email"),
                "role": user["role"],
                "is_active": user["is_active"],
                "must_change_password": user.get("must_change_password", False),
                "previous_login": previous_login,
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
    
    from backend.auth import UserCreate, VALID_ROLES
    if request.role not in VALID_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Role must be one of: {', '.join(VALID_ROLES)}")
    if not USERNAME_PATTERN.fullmatch(request.username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Username must be 3-32 characters: letters, digits, '.', '_' or '-'")
    problem = validate_new_password(request.password, request.username)
    if problem:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=problem)
    try:
        user_data = UserCreate(
            username=request.username,
            password=request.password,
            email=request.email,
            role=request.role
        )
        user = user_manager.create_user(user_data, must_change_password=request.must_change_password)
        track(current_user.username, "user.create", resource=user.username,
              details={"role": user.role, "must_change_password": request.must_change_password})
        return {
            "message": "User created successfully",
            "user": {
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active
            }
        }
    except HTTPException:
        raise
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
async def get_current_user_info(current_user: User = Depends(get_current_user_pending_ok)):
    """Get current user information (also available while a password change is pending)."""
    return {
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "must_change_password": current_user.must_change_password,
        "last_login": current_user.last_login,
    }


@app.post("/auth/change-password")
async def change_password(request: PasswordChangeRequest,
                          current_user: User = Depends(get_current_user_pending_ok)):
    """Change your own password. Returns a fresh token; all other sessions are signed out."""
    stored = user_manager.get_user(current_user.username)
    if not user_manager.verify_password(request.current_password, stored["hashed_password"]):
        track(current_user.username, "auth.password_change", "failure", details={"reason": "wrong_current_password"})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    if request.new_password == request.current_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="New password must be different from the current one")
    problem = validate_new_password(request.new_password, current_user.username)
    if problem:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=problem)
    user = user_manager.set_password(current_user.username, request.new_password, must_change=False)
    track(current_user.username, "auth.password_change")
    return {"message": "Password updated", "access_token": issue_token(user), "token_type": "bearer"}


# User administration (admin only)
@app.get("/users")
async def list_users(current_user: User = Depends(require_admin)):
    """All accounts with role, status and last sign-in."""
    users = user_manager.list_users()
    return {"users": users, "total": len(users)}


@app.patch("/users/{username}")
async def update_user(username: str, request: UserUpdateRequest,
                      current_user: User = Depends(require_admin)):
    """Change a user's role, email or active status."""
    from backend.auth import VALID_ROLES
    target = user_manager.get_user(username)
    if target is None:
        raise HTTPException(status_code=404, detail=f"User {username} not found")
    if request.role is not None and request.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(VALID_ROLES)}")
    if username == current_user.username and request.is_active is False:
        raise HTTPException(status_code=400, detail="You cannot disable your own account")

    removes_admin = target.get("role") == "admin" and target.get("is_active", True) and (
        request.is_active is False or (request.role is not None and request.role != "admin"))
    if removes_admin and user_manager.active_admin_count() <= 1:
        raise HTTPException(status_code=400, detail="At least one active administrator is required")

    changes = request.model_dump(exclude_none=True)
    if "role" in changes and changes["role"] == target.get("role"):
        changes.pop("role")  # unchanged role should not sign the user out
    if not changes:
        return {"user": user_manager.public_view(target), "message": "No changes"}
    updated = user_manager.update_user(username, **changes)
    track(current_user.username, "user.update", resource=username, details=changes)
    return {"user": user_manager.public_view(updated), "message": "User updated"}


@app.post("/users/{username}/reset-password")
async def reset_user_password(username: str, request: PasswordResetRequest,
                              current_user: User = Depends(require_admin)):
    """Set a temporary password; the user must choose a new one at next sign-in."""
    if user_manager.get_user(username) is None:
        raise HTTPException(status_code=404, detail=f"User {username} not found")
    problem = validate_new_password(request.new_password, username)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    user_manager.set_password(username, request.new_password, must_change=True)
    track(current_user.username, "user.password_reset", resource=username)
    return {"message": f"Temporary password set for {username}; they must change it at next sign-in"}

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
        # The collection counts chunks; report documents and passages separately.
        grouped = _group_chunks_by_document()
        stats["chunk_count"] = stats.get("document_count", 0)
        stats["document_count"] = len(grouped)
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
        track(current_user.username, "document.delete", resource=document_id,
              details={"filename": document["filename"], "chunks": len(document["chunk_ids"])})
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
CONTENT_TYPES_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    # Scanned images are converted to PDF and read with OCR.
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}
_index_lock = threading.Lock()  # uploads and the inbox watcher both write to ChromaDB


class IngestError(Exception):
    """A document was rejected before processing (unsupported, empty, too large)."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def ingest_document(content: bytes, filename: str, uploaded_by: str,
                    title: Optional[str] = None, category: Optional[str] = "general",
                    content_type: Optional[str] = None, channel: str = "upload") -> Dict[str, Any]:
    """Extract, chunk and index one document; shared by the upload API and the inbox watcher.

    Raises IngestError for rejected input and lets processing errors propagate.
    """
    start_time = datetime.now()
    filename = filename or ""
    # Browsers and file systems report MIME types inconsistently; trust the extension.
    content_type = CONTENT_TYPES_BY_EXTENSION.get(os.path.splitext(filename.lower())[1], content_type)
    category = category or "general"
    logger.info(f"Processing file: {filename}, Content type: {content_type}, channel: {channel}")

    if USE_ENHANCED_PROCESSOR:
        supported_formats = enhanced_processor.get_supported_formats()
        if content_type not in supported_formats:
            dependencies = enhanced_processor.check_dependencies()
            missing_deps = [k for k, v in dependencies.items() if not v]
            raise IngestError(status.HTTP_400_BAD_REQUEST,
                              f"Unsupported file type: {content_type or os.path.splitext(filename)[1] or 'unknown'}. "
                              f"Supported: PDF, DOCX, TXT, and scanned images (PNG, JPEG, TIFF)."
                              + (f" Missing dependencies: {missing_deps}" if missing_deps else ""))
    elif content_type != "text/plain":
        raise IngestError(status.HTTP_400_BAD_REQUEST,
                          f"Unsupported file type: {content_type}. Enhanced processor not available.")

    max_bytes = settings.max_file_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise IngestError(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                          f"File exceeds the {settings.max_file_size_mb} MB upload limit")
    if not content:
        raise IngestError(status.HTTP_400_BAD_REQUEST, "File is empty")

    document_id = uuid.uuid4().hex[:16]
    document_metadata = {
        "document_id": document_id,
        "filename": filename,
        "source": title or filename,
        "category": category,
        "uploaded_by": uploaded_by,
        "upload_date": datetime.now().isoformat(),
        "content_type": content_type,
        "file_size": len(content),
        "ingest_channel": channel,
    }

    if USE_ENHANCED_PROCESSOR:
        processed_result = enhanced_processor.process_document(
            file_content=content,
            filename=filename,
            content_type=content_type,
            metadata=document_metadata
        )
        text_content = processed_result['text']
        enhanced_metadata = {**document_metadata, **processed_result}
        enhanced_metadata.pop('text', None)
        logger.info(f"Enhanced processing complete. Text length: {len(text_content)}, "
                    f"Extraction method: {enhanced_metadata.get('extraction_method', 'unknown')}")
    else:
        text_content = content.decode('utf-8', errors='ignore')
        enhanced_metadata = dict(document_metadata)

    # Validate that we have actual text content, not binary data
    if text_content and text_content.startswith('%PDF'):
        raise RuntimeError("PDF text extraction failed - raw binary data detected")

    # Chunk only: ChromaDB computes vectors with the collection's embedding function.
    chunks, _ = get_embedder().process_document(
        text=text_content,
        metadata=enhanced_metadata,
        return_embeddings=False
    )

    chunks_processed = 0
    if chunks:
        texts = [chunk['text'] for chunk in chunks]
        # ChromaDB metadata values must be scalars
        metadatas = [
            {k: v for k, v in chunk['metadata'].items() if isinstance(v, (str, int, float, bool))}
            for chunk in chunks
        ]
        ids = [f"{document_id}-{i:04d}" for i in range(len(chunks))]
        with _index_lock:
            success = chroma_manager.add_documents(texts=texts, metadatas=metadatas, ids=ids)
        if not success:
            raise RuntimeError("Vector store rejected the document chunks")
        chunks_processed = len(chunks)
        logger.info(f"Stored {chunks_processed} chunks in ChromaDB with document ID: {document_id}")

    processing_time = (datetime.now() - start_time).total_seconds()
    analytics_manager.log_document_upload(DocumentMetrics(
        document_id=document_id,
        filename=filename,
        uploader_id=uploaded_by,
        upload_timestamp=datetime.now(),
        file_size=len(content),
        chunks_created=chunks_processed,
        processing_time=processing_time,
        document_type=str(enhanced_metadata.get("legal_document_type")
                          or enhanced_metadata.get("document_type", "general")),
    ))
    track(uploaded_by, "document.upload", resource=document_id, details={
        "filename": filename, "title": title or filename, "category": category,
        "size_bytes": len(content), "chunks": chunks_processed, "channel": channel,
        "document_type": str(enhanced_metadata.get("legal_document_type") or "general"),
    })
    return {
        "document_id": document_id,
        "chunks_processed": chunks_processed,
        "processing_time": processing_time,
        "message": f"Document '{title or filename}' indexed: {chunks_processed} passages in {processing_time:.1f}s",
    }


@app.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    category: Optional[str] = Form("general"),
    current_user: User = Depends(get_current_active_user)
):
    """Upload a PDF, DOCX or TXT file; it is extracted, split clause by clause and indexed."""
    start_time = datetime.now()
    content = await file.read()
    try:
        result = await run_in_threadpool(
            ingest_document, content, file.filename or "", current_user.username,
            title, category, file.content_type, "upload",
        )
        return DocumentUploadResponse(success=True, **result)
    except IngestError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        logger.error(f"Document upload error: {e}")
        track(current_user.username, "document.upload", "failure",
              details={"filename": file.filename, "error": str(e)[:200], "channel": "upload"})
        return DocumentUploadResponse(
            success=False,
            message=f"Failed to process document: {str(e)}",
            processing_time=(datetime.now() - start_time).total_seconds()
        )

# RAG Query endpoints
def _source_dicts(retrieval_results) -> List[Dict[str, Any]]:
    return [
        {
            "document_id": src.metadata.get("document_id", src.document_id),
            "chunk_id": src.document_id,
            "content": src.content,
            "metadata": src.metadata,
            "similarity_score": src.similarity_score,
            "chunk_index": src.chunk_index,
        }
        for src in retrieval_results
    ]


def _finalize_answer(question: str, username: str, result) -> RAGQueryResponse:
    """Shape a pipeline result for the API and record analytics and the audit event."""
    sources = _source_dicts(result.sources)

    # Entities come from the passages the answer cites (all sources if none are cited).
    cited = [sources[n - 1] for n in result.citations if 0 < n <= len(sources)] or sources
    legal_entities = extract_legal_entities("\n".join(s["content"] for s in cited))
    query_suggestions = suggest_follow_ups(
        question,
        dict.fromkeys(s["metadata"].get("legal_document_type") or s["metadata"].get("category", "")
                      for s in sources),
    )

    query_type = classify_query(question)
    analytics_manager.log_query(QueryMetrics(
        query_id=uuid.uuid4().hex,
        query_text=question,
        timestamp=datetime.now(),
        processing_time=result.processing_time or 0.0,
        similarity_scores=[s["similarity_score"] for s in sources],
        documents_retrieved=len({s["document_id"] for s in sources}),
        user_id=username,
        query_type=query_type,
        document_ids=[s["document_id"] for s in sources],
    ))
    track(username, "query.ask", details={
        "question": question[:300],
        "query_type": query_type,
        "mode": result.mode,
        "documents": sorted({s["document_id"] for s in sources}),
    })

    return RAGQueryResponse(
        answer=result.answer,
        sources=sources,
        query=question,
        total_tokens_used=result.total_tokens_used,
        processing_time=result.processing_time,
        confidence_score=result.confidence_score,
        mode=result.mode,
        model=result.model,
        citations=result.citations,
        legal_entities=legal_entities,
        query_suggestions=query_suggestions,
    )


def _validate_query(request: RAGQueryRequest):
    if not request.question.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Question cannot be empty")
    if get_rag_pipeline is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="RAG pipeline unavailable")


@app.post("/query", response_model=RAGQueryResponse)
async def query_documents(
    request: RAGQueryRequest,
    current_user: User = Depends(get_current_active_user)
):
    """Answer a question from the document corpus via the RAG pipeline."""
    _validate_query(request)
    try:
        result = await get_rag_pipeline().query(
            question=request.question,
            num_documents=max(1, min(request.num_documents, 20)),
            filter_metadata=request.filter_metadata
        )
        return _finalize_answer(request.question, current_user.username, result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Query error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query processing failed: {str(e)}"
        )


@app.post("/query/stream")
async def query_documents_stream(
    request: RAGQueryRequest,
    current_user: User = Depends(get_current_active_user)
):
    """Stream an answer as newline-delimited JSON events.

    {"type": "sources", "sources": [...]}   retrieved passages, sent first
    {"type": "token", "text": "..."}          answer fragments as they are generated
    {"type": "done", "result": {...}}         the complete /query response
    {"type": "error", "detail": "..."}        if processing fails part-way
    """
    _validate_query(request)
    username = current_user.username

    async def events():
        try:
            async for event in get_rag_pipeline().stream_query(
                question=request.question,
                num_documents=max(1, min(request.num_documents, 20)),
                filter_metadata=request.filter_metadata,
            ):
                if event["type"] == "sources":
                    payload = {"type": "sources", "sources": _source_dicts(event["sources"])}
                elif event["type"] == "token":
                    payload = event
                else:
                    final = _finalize_answer(request.question, username, event["response"])
                    payload = {"type": "done", "result": final.model_dump()}
                yield json.dumps(payload, default=str) + "\n"
        except Exception as e:
            logger.error(f"Streaming query error: {e}")
            yield json.dumps({"type": "error", "detail": f"Query processing failed: {e}"}) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

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
            "legal_entities": response.legal_entities,
            "query_suggestions": response.query_suggestions,
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
    days: int = 30,
    current_user: User = Depends(require_admin)
):
    """Query volume, document intake and query-type mix for the last `days` days."""
    data = analytics_manager.get_usage_analytics(days)
    if not data:
        raise HTTPException(status_code=500, detail="Failed to compute usage analytics")
    grouped = _group_chunks_by_document()
    data["document_analytics"]["library_documents"] = len(grouped)
    data["document_analytics"]["library_chunks"] = sum(d["chunk_count"] for d in grouped.values())
    return {"data": data}


@app.get("/analytics/performance")
async def get_performance_analytics(current_user: User = Depends(require_admin)):
    """Latency and retrieval-quality distributions with tuning suggestions."""
    return {"data": analytics_manager.get_query_performance_insights()}


def _document_centroids() -> Dict[str, Dict[str, Any]]:
    """Mean, L2-normalised chunk embedding per document."""
    results = chroma_manager.collection.get(include=["embeddings", "metadatas"])
    embeddings = results.get("embeddings")
    if embeddings is None or len(embeddings) == 0:
        return {}
    vectors: Dict[str, List[Any]] = {}
    names: Dict[str, str] = {}
    for chunk_id, embedding, metadata in zip(results["ids"], embeddings, results["metadatas"]):
        metadata = metadata or {}
        doc_id = metadata.get("document_id") or metadata.get("source") or chunk_id
        vectors.setdefault(doc_id, []).append(np.asarray(embedding, dtype=float))
        names[doc_id] = metadata.get("filename") or metadata.get("source") or doc_id
    centroids = {}
    for doc_id, chunk_vectors in vectors.items():
        mean = np.mean(chunk_vectors, axis=0)
        norm = np.linalg.norm(mean)
        if norm > 0:
            centroids[doc_id] = {"vector": mean / norm, "name": names[doc_id]}
    return centroids


@app.get("/analytics/similarity")
async def get_similarity_analytics(
    document_id: Optional[str] = None,
    current_user: User = Depends(require_admin)
):
    """Cosine similarity between documents, computed live from stored embeddings."""
    centroids = _document_centroids()
    if document_id:
        if document_id not in centroids:
            raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
        target = centroids[document_id]["vector"]
        similar = sorted(
            (
                {"document_id": other_id, "filename": info["name"],
                 "similarity": round(float(np.dot(target, info["vector"])), 3)}
                for other_id, info in centroids.items() if other_id != document_id
            ),
            key=lambda item: item["similarity"], reverse=True,
        )
        return {"data": {"document_id": document_id,
                         "filename": centroids[document_id]["name"],
                         "similar_documents": similar[:10]}}

    ids = list(centroids)
    pairs = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            score = float(np.dot(centroids[ids[i]]["vector"], centroids[ids[j]]["vector"]))
            pairs.append({"doc1": centroids[ids[i]]["name"], "doc2": centroids[ids[j]]["name"],
                          "doc1_id": ids[i], "doc2_id": ids[j], "similarity": round(score, 3)})
    pairs.sort(key=lambda item: item["similarity"], reverse=True)
    scores = [pair["similarity"] for pair in pairs]
    return {"data": {
        "overall_stats": {
            "avg_similarity": round(float(np.mean(scores)), 3) if scores else 0.0,
            "max_similarity": round(max(scores), 3) if scores else 0.0,
            "total_comparisons": len(scores),
            "documents_compared": len(ids),
        },
        "similar_document_pairs": pairs[:20],
    }}


@app.get("/analytics/activity")
async def get_activity_analytics(
    days: int = 30,
    current_user: User = Depends(require_admin)
):
    """Who used the system, for what, and when."""
    return {"data": analytics_manager.get_user_activity_summary(days)}


@app.get("/analytics/report")
async def generate_analytics_report(
    format: str = "json",
    current_user: User = Depends(require_admin)
):
    """Full analytics export, including an audit-trail summary and integrity check."""
    report = analytics_manager.export_analytics_report(format)
    report["audit_summary"] = audit.summary(30)
    report["audit_integrity"] = audit.verify_chain()
    track(current_user.username, "analytics.export", details={"format": format})
    return report


# Audit trail endpoints (admin only)
@app.get("/audit/logs")
async def get_audit_logs(
    limit: int = 100,
    offset: int = 0,
    username: Optional[str] = None,
    action: Optional[str] = None,
    status_filter: Optional[str] = None,
    days: Optional[int] = None,
    current_user: User = Depends(require_admin)
):
    """Newest-first audit events with optional filters."""
    return audit.query(limit=max(1, min(limit, 500)), offset=max(0, offset), username=username,
                       action=action, status=status_filter, since_days=days)


@app.get("/audit/summary")
async def get_audit_summary(days: int = 30, current_user: User = Depends(require_admin)):
    """Event counts by action and outcome."""
    return audit.summary(days)


@app.get("/audit/verify")
async def verify_audit_chain(current_user: User = Depends(require_admin)):
    """Recompute the hash chain to detect edited or deleted audit rows."""
    result = audit.verify_chain()
    track(current_user.username, "audit.verify", "success" if result["valid"] else "failure", details=result)
    return result


@app.get("/audit/export")
async def export_audit_log(
    username: Optional[str] = None,
    action: Optional[str] = None,
    status_filter: Optional[str] = None,
    days: Optional[int] = None,
    current_user: User = Depends(require_admin)
):
    """Download matching audit events as CSV."""
    track(current_user.username, "audit.export", details={"username": username, "action": action, "days": days})
    csv_text = audit.export_csv(username=username, action=action, status=status_filter, since_days=days)
    filename = f"audit_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(content=csv_text, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})

# Integrations (admin only)
@app.get("/integrations/status")
async def integrations_status(current_user: User = Depends(require_admin)):
    """Webhook targets, recent deliveries and inbox watcher state."""
    return {
        "notifications": notifier.status(),
        "inbox": inbox_watcher.status() if inbox_watcher else {"running": False, "enabled": False},
    }


@app.post("/integrations/test")
async def send_test_notification(current_user: User = Depends(require_admin)):
    """Send a test event to every configured target and report the outcome."""
    if not notifier.enabled:
        raise HTTPException(status_code=400,
                            detail="No webhook configured. Set N8N_WEBHOOK_URL and/or SLACK_WEBHOOK_URL in .env")
    event = notifier.build_event("integration.test", "success", current_user.username, None,
                                 {"message": "Test notification"}, request_context.get().get("ip"))
    if event is None:
        raise HTTPException(status_code=400, detail="integration.test is excluded by NOTIFY_EVENTS")
    deliveries = await run_in_threadpool(notifier.deliver, event)
    audit.record("integration.test", username=current_user.username,
                 status="success" if all(d["ok"] for d in deliveries) else "failure",
                 details={"deliveries": deliveries})
    return {"event": event, "deliveries": deliveries}


@app.post("/integrations/inbox/scan")
async def scan_inbox_now(current_user: User = Depends(require_admin)):
    """Process everything currently in the inbox immediately (skips the stability wait)."""
    if not inbox_watcher:
        raise HTTPException(status_code=400, detail="Inbox watcher is disabled (INBOX_ENABLED=false)")
    counts = await run_in_threadpool(inbox_watcher.scan_once, False)
    return {"counts": counts, "inbox": inbox_watcher.status()}


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


