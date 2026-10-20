# Local Legal AI — Architecture

This document describes the system **as implemented**. Planned work is listed
in [`phases.md`](../phases.md) under *Remaining Work*. Keep this file in sync
whenever a component's behaviour changes.

## Overview

```
 Browser ──▶ Streamlit UI (127.0.0.1:8501)
                │  REST + JWT bearer token
                ▼
           FastAPI backend (127.0.0.1:8000)
           ├── auth.py ............ bcrypt users in data/users.json, HS256 JWTs
           ├── enhanced_document_processor ... PDF (PyMuPDF/PyPDF2), DOCX, TXT → text + legal metadata
           ├── rag/embedder ....... legal-aware chunking (sections → size windows)
           ├── vector_store ....... embedded ChromaDB, persisted in data/chroma_db
           └── rag/rag_pipeline ... retrieve → prompt → local LLM → cited answer
                                      │
                                      ▼  OpenAI-compatible /v1/chat/completions
                         Local model server (optional)
                         vLLM :8001 (model/vllm_launcher.sh) or Ollama :11434
```

Everything runs on the host machine; no request leaves it. Both services bind to
`127.0.0.1` by default so the login page is only reachable locally.

## Components

### Backend — `backend/app.py`
FastAPI application. Key endpoints:

| Endpoint | Purpose |
|---|---|
| `POST /auth/login` | Username/password → JWT (401 on bad credentials) |
| `POST /auth/register` | Admin-only user creation |
| `GET /auth/me` | Current user profile |
| `POST /documents/upload` | Extract, chunk and index a file (size-limited by `MAX_FILE_SIZE_MB`) |
| `GET /documents`, `/documents/list` | One record per uploaded document with chunk count and metadata |
| `DELETE /documents/{id}` | Remove a document and all its chunks (uploader or admin) |
| `GET /documents/stats` | Collection statistics |
| `POST /query` | RAG answer with sources, citations, confidence and generation mode |
| `POST /documents/query` | Same answer in the shape the Enhanced Chat page expects |
| `GET /health` | API, ChromaDB and model-server status |
| `GET /analytics/*` | Admin analytics (currently sample data — see Remaining Work) |

### Document identity
Each upload is assigned a 16-hex-character `document_id`. Every chunk stores it in
metadata and uses the id `"{document_id}-{chunk:04d}"`. Listing groups chunks by
`document_id`; chunks indexed before this scheme existed are grouped by `source`.

### Document processing — `rag/enhanced_document_processor.py`
Extracts text (PyMuPDF first, PyPDF2 fallback, garbled-text detection), cleans it,
classifies the legal document type by keyword scoring (contract, NDA, lease,
employment, will, …) and extracts legal terms and section headings. Metadata is
flattened to scalars because ChromaDB rejects nested values.

### Chunking — `rag/embedder.py` (fallback `rag/simple_embedder.py`)
Splits on legal structure first (`Section N`, numbered clauses, `WHEREAS`, …),
then windows by `CHUNK_SIZE` words with `CHUNK_OVERLAP`. Upload uses it for
chunking only; vectors are computed by the ChromaDB collection.

### Vector store — `vector_store/chromadb_setup.py`
Embedded `chromadb.PersistentClient` at `data/chroma_db`, collection
`legal_documents`, embedding function `all-MiniLM-L6-v2` via sentence-transformers.
If that model cannot load, a hash-based function keeps the service up but search
quality degrades sharply — check backend logs for
`Using SimpleEmbeddingFunction` if results look random.

### RAG pipeline — `rag/rag_pipeline.py`
1. Retrieve the top-k chunks from ChromaDB (distance mapped to a 0–1 similarity).
2. Format them as numbered excerpts `[1] … [k]`.
3. If the model server answers `GET /v1/models` (cached 30 s), send a
   citation-enforcing system prompt to `/v1/chat/completions` → **generative** mode.
4. Otherwise, or if generation fails, build an **extractive** answer from the
   sentences that best overlap the question, each tagged with its source number.
5. Confidence blends retrieval similarity (60%) with question-term coverage (40%).

The response carries `mode`, `model` and `citations` so the UI can label how an
answer was produced.

### Authentication — `backend/auth.py`
bcrypt password hashes (used directly; passlib is incompatible with bcrypt ≥ 4.1),
HS256 JWTs signed with `SECRET_KEY` from `.env`. A default `admin`/`admin123`
account is created on first start — change it before any real use.

### Frontend — `frontend/streamlit_app.py`
Streamlit app: login, Dashboard, Upload, Chat, Enhanced Chat, Document
Management, Files Management and admin Analytics pages. Talks to the backend via
`BACKEND_URL` (default `http://localhost:8000`).

## Configuration
All settings live in `.env` (template: `.env.example`) and are read by
`backend/config.py`. `start_system.sh` creates `.env` on first run with a
randomly generated `SECRET_KEY`. The file must stay valid shell syntax because
the script sources it.

## Runtime data (git-ignored)
`data/users.json`, `data/chroma_db/`, `logs/`, `analytics.db`, `.env`, `.venv/`.

## Testing
`pytest tests/` runs the API end to end against a throwaway data directory,
including a mocked LLM to cover generative mode. The legacy `test_phase*.py`
scripts require a running server.
