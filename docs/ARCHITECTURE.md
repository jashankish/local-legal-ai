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
| `POST /auth/login` | Username/password → JWT (401 bad credentials, 403 disabled); returns `must_change_password` |
| `POST /auth/register` | Admin-only user creation (temporary password, `must_change_password` default true) |
| `GET /auth/me` | Current user profile (allowed while a password change is pending) |
| `POST /auth/change-password` | Change own password; returns a new token, revokes other sessions |
| `GET /users` | All accounts with role, status, last sign-in (admin) |
| `PATCH /users/{username}` | Change role, email or active status (admin) |
| `POST /users/{username}/reset-password` | Set a temporary password that must be changed (admin) |
| `POST /documents/upload` | Extract, chunk and index a file (size-limited by `MAX_FILE_SIZE_MB`) |
| `GET /documents`, `/documents/list` | One record per uploaded document with chunk count and metadata |
| `DELETE /documents/{id}` | Remove a document and all its chunks (uploader or admin) |
| `GET /documents/stats` | Collection statistics |
| `POST /query` | RAG answer with sources, citations, confidence and generation mode |
| `POST /documents/query` | Same answer in the shape the Enhanced Chat page expects |
| `GET /health` | API, ChromaDB and model-server status |
| `GET /analytics/usage` | Query volume, query-type mix, document intake (admin) |
| `GET /analytics/performance` | Latency / retrieval-quality distributions, tuning suggestions (admin) |
| `GET /analytics/similarity` | Live document-to-document cosine similarity (admin) |
| `GET /analytics/activity` | Active users, activity types, hourly pattern (admin) |
| `GET /analytics/report` | Full JSON export incl. audit summary and integrity result (admin) |
| `GET /audit/logs` | Filterable audit events, newest first (admin) |
| `GET /audit/summary` | Event counts by action and outcome (admin) |
| `GET /audit/verify` | Recompute the audit hash chain (admin) |
| `GET /audit/export` | Audit events as CSV (admin) |

### Request pipeline
Every request passes `access_control_middleware`, which (1) rejects clients not in
`ALLOWED_IPS` (single IPs or CIDR ranges; empty = allow all) with 403 and an
`access.ip_denied` audit event, and (2) stores the client IP and user agent in a
context variable that the audit logger reads. Admin-only routes use the
`require_admin` dependency. CORS is limited to `CORS_ORIGINS` (the local UI).

Note that the Streamlit server calls the API from `127.0.0.1`; if `ALLOWED_IPS`
is set it must include `127.0.0.1` for the UI to keep working.

### Audit trail — `security/audit_log.py`
Append-only SQLite table `audit_events` in `data/audit.db`. Each row stores
timestamp (UTC), username, action, resource, status (`success` / `failure` /
`denied`), IP, user agent, JSON details, `prev_hash` and `hash`, where
`hash = SHA-256(prev_hash ‖ canonical JSON of the row)`. `verify_chain()`
recomputes the chain and returns the first altered row. Writes are serialised by
a lock and never raise into the request path. Disable with `ENABLE_AUDIT_LOGGING=false`.

Audited actions: `auth.login`, `auth.password_change`, `user.create`, `user.update`, `user.password_reset`, `document.upload`,
`document.delete`, `query.ask` (question, query type, answer mode, documents
consulted), `analytics.export`, `audit.verify`, `audit.export`, `access.ip_denied`.

### Analytics — `backend/analytics.py`
SQLite at `data/analytics.db`. The API logs every query (latency, per-document
best similarity, keyword-classified query type such as *Termination* or
*Payment & Fees*), every upload (size, chunks, detected document type,
uploader) and every successful audited action as user activity. Document
similarity is computed on request from the mean chunk embedding of each
document in ChromaDB, so it is always current.

### Document identity
Each upload is assigned a 16-hex-character `document_id`. Every chunk stores it in
metadata and uses the id `"{document_id}-{chunk:04d}"`. Listing groups chunks by
`document_id`; chunks indexed before this scheme existed are grouped by `source`.

### Document processing — `rag/enhanced_document_processor.py`
Extracts text (PyMuPDF first, PyPDF2 fallback, garbled-text detection), cleans it,
classifies the legal document type by keyword scoring (contract, NDA, lease,
employment, will, …) and extracts legal terms and section headings. Metadata is
flattened to scalars because ChromaDB rejects nested values.

Text cleaning collapses spaces but **preserves line breaks**, which the chunker
relies on. The garbled-text heuristic flags extractions dominated by a single
character or lacking word boundaries; when PyMuPDF output looks garbled the
PyPDF2 extraction is tried instead.

### Chunking — `rag/embedder.py` (fallback `rag/simple_embedder.py`)
Splits on legal structure first (`Section N`, numbered clauses, `WHEREAS`, …),
so each clause normally becomes its own passage, then windows any long section
by `CHUNK_SIZE` words (default 220, which fits MiniLM's 256-token input) with
`CHUNK_OVERLAP` (default 40). Upload uses it for chunking only; vectors are
computed by the ChromaDB collection.

### Key terms and follow-ups — `rag/legal_insights.py`
Pattern-based (no model download) extraction over the passages an answer cites:
organisations with corporate suffixes, defined terms (`("Tenant")`), monetary
amounts, periods (`sixty (60) days`), percentages, dates, governing law and
statute/case citations. `suggest_follow_ups()` proposes next questions for the
document types behind the answer, skipping ones that repeat the question.
`/query` and `/documents/query` return them as `legal_entities` and
`query_suggestions`.

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
HS256 JWTs signed with `SECRET_KEY` from `.env`. Roles: `admin`, `lawyer`,
`user`. Users live in `data/users.json`, written atomically with mode 0600.

Session lifecycle:
- Each user record has a `token_version`; tokens carry it as the `tv` claim.
  Changing a password, disabling the account or changing its role increments
  it, so every previously issued token fails with 401 on its next request.
- `must_change_password` is set for the first-run `admin`/`admin123` account
  (and detected for older installs still using that password), for accounts
  created by an admin (by default) and after an admin password reset. While it
  is set, every endpoint except `/auth/me` and `/auth/change-password` returns
  403 — enforcement is server-side, not just in the UI.
- Dependencies: `get_current_user` (valid, current token) →
  `get_current_user_pending_ok` (account active) → `get_current_active_user`
  (no pending password change) → `require_admin`.
- Passwords: ≥ 8 characters, not the username, not the default. Usernames:
  3–32 of letters, digits, `.`, `_`, `-`. The last active admin cannot be
  disabled or demoted, and admins cannot disable themselves.

### Frontend — `frontend/streamlit_app.py`
Streamlit app: login, Dashboard, Upload, Chat, Enhanced Chat, Document
Management, Files Management, My Account, and the admin-only Analytics, Audit Log and Users pages (hidden from other roles). A pending password change shows a blocking change-password screen instead of the app.
The Audit Log page offers filters (user, action, outcome, period), a one-click
chain verification and CSV export. Talks to the backend via
`BACKEND_URL` (default `http://localhost:8000`).

## Configuration
All settings live in `.env` (template: `.env.example`) and are read by
`backend/config.py`. `start_system.sh` creates `.env` on first run with a
randomly generated `SECRET_KEY`. The file must stay valid shell syntax because
the script sources it.

## Runtime data (git-ignored)
`data/users.json`, `data/chroma_db/`, `data/audit.db`, `data/analytics.db`,
`logs/`, `.env`, `.venv/`.

## Testing
`pytest tests/` runs the API end to end against a throwaway data directory,
including a mocked LLM to cover generative mode, audit tamper detection, IP
whitelisting and analytics fed by real requests. `scripts/ui_smoke.py` renders
every Streamlit page as admin against a running backend and fails on any
exception. The legacy `test_phase*.py` scripts require a running server.

## Demo tooling
- `samples/` — four fictional agreements (TXT, DOCX, PDF); `scripts/build_samples.py`
  regenerates the DOCX/PDF from `samples/sources/`.
- `scripts/seed_demo.py` — uploads the samples, creates an `associate` user and
  asks typical questions against a running backend.
- `scripts/capture_screenshots.py` — Playwright tour that signs in through the UI
  and writes `docs/screenshots/*.png` (dev dependency: `requirements-dev.txt`).
- `.streamlit/config.toml` — UI theme and minimal toolbar.
