# 🧠 Local Legal AI

A private, self-hosted assistant for **law firms**: upload contracts, filings and
policies, then ask questions and get answers that cite the exact passages they
came from. Everything — documents, vectors, the language model — stays on your
machine. No third-party AI APIs are called.

## 🚀 Features

| Feature | Status |
|---|---|
| 🔐 Local login (JWT, bcrypt), admin and user roles | ✅ |
| 📄 PDF, DOCX and TXT ingestion with legal document-type detection | ✅ |
| 📚 Semantic search over an embedded ChromaDB store | ✅ |
| 🧾 Cited answers from a local LLM (vLLM or Ollama) | ✅ |
| 🪶 Extractive answer mode when no model is running (no GPU required) | ✅ |
| 🗂 Document library: per-document listing, search, delete | ✅ |
| 📊 Admin analytics: usage, query types, latency, document similarity, user activity | ✅ |
| 🛡 Tamper-evident audit log (hash-chained) with filters and CSV export | ✅ |
| 🌐 IP whitelisting (addresses or CIDR ranges) | ✅ |
| 🔁 n8n automation (folder ingestion, Slack alerts) | 🚧 planned |

Progress and the remaining roadmap live in [`phases.md`](phases.md).

## 🧱 Architecture

```
Browser ─▶ Streamlit UI :8501 ─▶ FastAPI :8000 ─▶ RAG pipeline ─▶ ChromaDB (data/chroma_db)
                                                       │
                                                       ▼
                                  Local LLM, OpenAI-compatible (vLLM :8001 / Ollama :11434)
```

Details, endpoint list and data flow: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## ⚡ Quick Start

Requires Python 3.10–3.12.

```bash
git clone https://github.com/jashankish/local-legal-ai.git
cd local-legal-ai
./start_system.sh
```

On first run the script creates `.venv`, installs dependencies, and writes `.env`
with a randomly generated `SECRET_KEY`. Then open **http://localhost:8501** and
sign in with `admin` / `admin123` — change this password before real use.

Stop everything with `./stop_system.sh`.

### Connecting a local language model (optional)

Without a model the assistant answers in **extractive mode**: the most relevant
sentences from your documents, each cited. To get generated answers, run any
OpenAI-compatible server and point `.env` at it:

```bash
# Option A — Ollama (Mac/Linux, CPU or Apple Silicon)
ollama pull llama3.1:8b
# .env: MODEL_ENDPOINT=http://localhost:11434  MODEL_NAME=llama3.1:8b

# Option B — vLLM on an NVIDIA GPU
bash model/vllm_launcher.sh
# .env: MODEL_ENDPOINT=http://localhost:8001   MODEL_NAME=legal-ai-model
```

Restart with `./start_system.sh`. `GET /health` reports the model as `healthy`
once it is reachable, and each answer is labelled with the mode that produced it.

## 💡 Example Use Cases

- 🔍 "What notice period is required to terminate the MSA?" — answer with clause citations
- 📄 Summarise obligations, fees and governing law across a set of agreements
- 🗂 Keep a searchable, private library of client documents

## 🛡 Security Notes

- Services bind to `127.0.0.1` by default; the login page is not exposed to the network.
- Secrets live only in `.env` (git-ignored). Runtime data (`data/`, `logs/`) is git-ignored.
- Uploads are size-limited (`MAX_FILE_SIZE_MB`); only the uploader or an admin can delete a document.
- Every sign-in, upload, question and deletion is written to a hash-chained audit log
  (`data/audit.db`). Admins can filter it, verify its integrity and export it as CSV
  from the 🛡️ Audit Log page.
- `ALLOWED_IPS` restricts which hosts may call the API (include `127.0.0.1` so the
  local UI keeps working).

## 🧪 Testing

```bash
.venv/bin/python -m pytest tests/
```

The suite drives the API end to end against a temporary data directory, with a
mocked LLM for the generative path.

## 🧩 Stack

| Layer | Tool |
|---|---|
| Model | Any OpenAI-compatible local server (vLLM, Ollama) |
| Vector store | ChromaDB (embedded) + all-MiniLM-L6-v2 |
| Backend | FastAPI |
| Frontend | Streamlit |
| Document parsing | PyMuPDF, PyPDF2, python-docx |
