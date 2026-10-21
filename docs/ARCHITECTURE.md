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
| `POST /query/stream` | Same answer as NDJSON events: `sources`, `token`…, `done` (or `error`) |
| `POST /documents/query` | Same answer in a flattened shape (legacy clients) |
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
| `GET /integrations/status` | Inbox watcher state and webhook targets / recent deliveries (admin) |
| `POST /integrations/test` | Send a test event to every configured target (admin) |
| `POST /integrations/inbox/scan` | Process the inbox immediately (admin) |

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

Audited actions: `auth.login` (success / failure / denied / locked), `auth.password_change`, `user.create`, `user.update`, `user.password_reset`, `document.upload`,
`document.delete`, `query.ask` (question, query type, answer mode, documents
consulted), `analytics.export`, `audit.verify`, `audit.export`, `access.ip_denied`.

### Ingestion — `ingest_document()` in `backend/app.py`
One code path for every way a document arrives: validates type (by extension;
browsers and file systems report MIME types inconsistently), size and
emptiness (raising `IngestError` → 400/413), extracts, chunks, indexes under a
lock (uploads and the inbox watcher can run concurrently), then logs analytics
and the `document.upload` audit event with its `channel` (`upload` or `inbox`).
The upload endpoint runs it in a worker thread so large PDFs don't block the
event loop.

### Watched inbox — `backend/folder_watcher.py`
A polling thread (portable to network shares, where file-system events are
unreliable) started in the API lifespan when `INBOX_ENABLED=true`. Every
`INBOX_POLL_SECONDS` it walks `INBOX_DIR`; files in `INBOX_DIR/<category>/` get
that category. A file is processed only after its size and mtime are unchanged
across one full scan, so half-copied files are never read. Success → moved to
`processed/YYYY-MM-DD/`; failure → `failed/` plus `<name>.error.txt`, an audit
failure event and a `document.ingest_failed` notification. Documents are owned
by the pseudo-user `inbox` (deletable by admins).

### Notifications — `backend/integrations.py`
`track()` hands every audit action to `EventNotifier`, which maps a fixed set
of (action, outcome) pairs to public events (`document.indexed`,
`security.login_failed`, `user.created`, …; queries are never mapped) and
queues them for a daemon thread. Delivery: JSON to `N8N_WEBHOOK_URL`, signed
with `X-LegalAI-Signature: sha256=HMAC(WEBHOOK_SECRET, body)`; a formatted
message to `SLACK_WEBHOOK_URL`. Three attempts with backoff for network errors,
5xx and 429; the last 50 deliveries are kept for the Integrations page. Detail
keys that could hold privileged text (`question`, `answer`, `content`, `text`)
are stripped. `NOTIFY_EVENTS` restricts the set.

### n8n workflows — `workflows/n8n/flows/`
Event alerts (webhook → HMAC check → Slack), drop-zone ingestion (local file
trigger → sign in → multipart upload) and a daily digest (schedule → analytics
and audit summary → Slack). Verified end to end against n8n 1.123; see
`workflows/n8n/README.md`.

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

**OCR** (`rag/ocr.py`): pages whose text layer has fewer than 20 characters
are recognised with Tesseract through PyMuPDF (`get_textpage_ocr`, 300 dpi,
`OCR_LANGUAGE`, up to `OCR_MAX_PAGES` per document); normal pages keep their
native text. Chunks record `extraction_method = pymupdf+ocr` and `ocr_pages`.
Without Tesseract an image-only PDF is rejected with instructions to install
it; `/health` reports `ocr: available | not_installed`. The Docker image
includes `tesseract-ocr`. Scanned images (PNG, JPEG, multi-page TIFF) are
opened with PyMuPDF, converted to PDF and sent through the same path
(`extraction_method = image+ocr`); the upload page previews them. (RapidOCR was evaluated and rejected: it dropped
spaces between English words and missed lines.)

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
`stream_query()` is the single implementation; `query()` consumes it and returns
the final result. Events: `sources` → `token`* → `done`.

1. Retrieve the top-k chunks from ChromaDB (distance mapped to a 0–1 similarity).
2. **Grounding gate:** if none of the question's key terms occur in the top
   three passages, answer "None of your documents appear to address this
   question" (mode **no_match**) without calling the model, so it can't answer
   from general knowledge.
3. Format the passages as numbered excerpts `[1] … [k]`.
4. If the model server answers `GET /v1/models` (cached 30 s), stream from
   `/v1/chat/completions` (`stream: true`, OpenAI SSE format) → **generative**.
   Each fragment is forwarded as it arrives. A stream that closes without
   `[DONE]` or a `finish_reason` is treated as interrupted: the partial answer
   is kept with a notice.
5. Sentences the model left uncited are attributed to the excerpt sharing at
   least half (and ≥ 3) of their key terms; if nothing is cited afterwards, a
   caution to verify against the sources is appended.
6. With no model, or if generation fails before any text, build an
   **extractive** answer from the best-overlapping sentences (streamed one
   passage at a time).
7. Confidence blends retrieval similarity (60%) with question-term coverage (40%).

The response carries `mode` (`generative`, `extractive`, `no_match`), `model`,
`citations`, `legal_entities` and `query_suggestions`. `POST /query/stream`
returns the same events as newline-delimited JSON; the Ask page renders tokens
with `st.write_stream` and then shows the full result.

Verified with Qwen2.5-1.5B-Instruct under llama.cpp
(`model/llamacpp_launcher.sh`): first token ≈ 0.4–0.5 s and full answers in
≈ 1–2 s on Apple Silicon; the prompt ends with an explicit citation instruction
because small models otherwise omit `[n]` markers.

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
- Sign-in throttling (`LoginThrottle`): after `LOGIN_MAX_FAILURES` (5)
  failures for a username from one client address within
  `LOGIN_LOCKOUT_MINUTES` (15), further attempts — even with the right
  password — get 429 with `Retry-After`, an `auth.login`/`locked` audit event
  and a `security.login_locked` notification. Keying on username *and*
  address prevents an outsider from locking a user out of their own machine;
  a successful sign-in clears the count. State is in memory (reset on restart).
- `SECRET_KEY` is validated at start-up: published placeholders and values
  shorter than 16 characters are rejected, because a known key would let
  anyone forge tokens.

### Frontend — `frontend/streamlit_app.py`
Streamlit app: login, Dashboard (with a getting-started checklist while the library is empty), Upload Documents,
Ask Documents (streamed answers), Document Library (search, delete, CSV register), My Account, and the admin-only Analytics, Audit Log, Users and Integrations pages (hidden from other roles). A pending password change shows a blocking change-password screen instead of the app.
The Audit Log page offers filters (user, action, outcome, period), a one-click
chain verification and CSV export. Talks to the backend via
`BACKEND_URL` (default `http://localhost:8000`).

## Configuration
All settings live in `.env` (template: `.env.example`) and are read by
`backend/config.py`. `start_system.sh` creates `.env` on first run with a
randomly generated `SECRET_KEY`. The file must stay valid shell syntax because
the script sources it.

## Deployment
Two supported ways to run:

- **`start_system.sh`** — creates `.venv`, generates `.env` with a random
  `SECRET_KEY`, starts uvicorn (API) and Streamlit (UI) on 127.0.0.1.
- **Docker Compose** — `Dockerfile` at the repo root builds one image
  (Python 3.12, CPU-only PyTorch, `all-MiniLM-L6-v2` baked in under
  `HF_HOME=/opt/huggingface`, non-root user `legalai`). `docker-compose.yml`
  runs it twice: `api` (uvicorn, port 8000) and `ui` (Streamlit, port 8501,
  `BACKEND_URL=http://api:8000`, starts once the API is healthy). Ports are
  bound to 127.0.0.1. `SECRET_KEY` is required at compose time. State lives in
  the `legal_data` volume at `/app/data`; `./inbox` on the host is mounted as
  the watched inbox. Optional profiles: `llm` (llama.cpp server image,
  model pulled once into the `llm_models` volume, served as `legal-ai-model`;
  the API's default `MODEL_ENDPOINT` is `http://llm:8080`) and `automation`
  (n8n 1.123 with the workflows mounted read-only). `.dockerignore` keeps
  `.env`, token files, runtime data, virtualenvs and model weights out of the
  image. `ALLOWED_IPS` is left empty in containers because requests arrive
  from the Docker bridge; the 127.0.0.1 port binding provides locality.

  The API's model endpoint comes from `DOCKER_MODEL_ENDPOINT` (default
  `http://llm:8080`), deliberately not `MODEL_ENDPOINT`: compose interpolates
  `${...}` from `.env`, whose host value would point the container at itself.
  If the inbox folder isn't writable by uid 1000 the API starts without the
  watcher and logs why.

  Verification: CI (`.github/workflows/ci.yml`) builds the image on every push,
  starts `api` + `ui` with `docker compose up --wait`, seeds the samples, checks
  a cited extractive answer, drops a file in `./inbox` and waits for it to be
  indexed, then starts the `llm` profile and waits for a generated answer
  (`scripts/ci_check_answer.py`). First green run: 2026-10-21, generated answer
  in ≈ 6.5 s on a 2-core runner.

## Runtime data (git-ignored)
`data/users.json`, `data/chroma_db/`, `data/audit.db`, `data/analytics.db`, `data/inbox/`,
`logs/`, `.env`, `.venv/`.

## Testing
`pytest tests/` runs the API end to end against a throwaway data directory,
including a mocked LLM to cover generative mode, audit tamper detection, IP
whitelisting and analytics fed by real requests. `scripts/ui_smoke.py` renders
every Streamlit page as admin against a running backend and fails on any
exception. Superseded scripts from earlier phases live in `legacy/` and are excluded from the suite (`pytest.ini`) and the Docker image.

## Demo tooling
- `samples/` — four fictional agreements (TXT, DOCX, PDF); `scripts/build_samples.py`
  regenerates the DOCX/PDF from `samples/sources/`.
- `scripts/seed_demo.py` — uploads the samples, creates an `associate` user and
  asks typical questions against a running backend.
- `scripts/capture_screenshots.py` — Playwright tour that signs in through the UI
  and writes `docs/screenshots/*.png` (dev dependency: `requirements-dev.txt`).
- `.streamlit/config.toml` — UI theme and minimal toolbar.
