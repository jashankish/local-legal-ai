# 🧠 Local Legal AI

A fully private, self-hosted LLM-powered assistant tailored for **law firms**. This platform enables secure, high-performance legal document Q&A using **open-source models**, **vector search**, and **automation workflows**—all without sending a single byte to third-party APIs.

## 🚀 Features

- 🔐 **Private Deployment** — No OpenAI/Anthropic dependencies
- 🧾 **Legal Document Q&A** — Use RAG (Retrieval-Augmented Generation) with case files, contracts, and statutes
- ⚡️ **Fast Inference** — Powered by [LLaMA 3](https://ai.meta.com/llama/) via [vLLM](https://github.com/vllm-project/vllm)
- 📚 **Vector Search** — Efficient and scalable storage of embeddings using [ChromaDB](https://www.trychroma.com/)
- 💬 **Modern Chat UI** — Streamlit-based frontend for lawyers and staff to ask natural language questions
- 🔁 **Automation** — Built-in [n8n](https://n8n.io/) to handle file drops, Slack alerts, and data flows
- 🛡 **Audit Logging & Access Control** — Secure everything with JWT, IP whitelisting, and activity logs

## 🧱 Architecture

```
User ↔ Streamlit UI ↔ FastAPI Backend ↔ RAG Pipeline ↔ ChromaDB ↔ Embedded Legal Docs
                                          ↕
                                    vLLM (LLaMA 3)
                                          ↕
                              Secure GPU Host (CoreWeave / On-Prem)
```

## 📂 Project Structure

```
local-legal-ai/
├── backend/                  # FastAPI backend and RAG logic
│   ├── app.py
│   ├── auth.py
│   ├── config.py
│   ├── embedder.py
│   └── rag_pipeline.py
├── frontend/                 # Streamlit-based UI
│   └── streamlit_app.py
├── vector_store/             # ChromaDB setup
│   └── chromadb_setup.py
├── model/                    # LLaMA 3 launcher via vLLM
│   └── vllm_launcher.sh
├── workflows/n8n/           # Automation flows
│   ├── docker-compose.yml
│   └── workflows.json
├── security/                # Access logging and controls
│   └── audit_log.py
├── docker-compose.yml       # Orchestration file
├── requirements.txt         # Python dependencies
├── .env                     # Secrets and config
└── README.md                # This file
```

## 🧪 Setup Instructions

### 1. Clone and Prepare

```bash
git clone https://github.com/your-org/local-legal-ai.git
cd local-legal-ai
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

Fill in `.env` with your secrets:

```env
SECRET_KEY=your-secret-key
MODEL_ENDPOINT=http://localhost:8001
```

### 3. Launch LLaMA 3 with vLLM

```bash
bash model/vllm_launcher.sh
```

You'll need access to A100-class GPUs or rent from a provider like [CoreWeave](https://www.coreweave.com/).

### 4. Start Services

```bash
docker-compose up --build
```

This runs:
- FastAPI backend
- ChromaDB vector store
- n8n automation engine
- Streamlit frontend

## 💡 Example Use Cases

- 🔍 **Ask questions** about litigation filings and get citations
- 📄 **Summarize** long legal contracts or court rulings
- 📥 **Upload** new PDFs to a folder and trigger ingestion automatically via n8n
- 🔐 **Keep** all client and case data 100% private

## 🛡 Security Best Practices

- **JWT authentication** (configurable in `auth.py`)
- **IP whitelisting** and role-based access controls
- **Full audit logs** of queries in `security/audit_log.py`
- **No outbound API calls** to third-party LLMs

## 🧩 Stack Highlights

| Layer        | Tool/Library          |
|-------------|-----------------------|
| Model        | LLaMA 3 (70B) + vLLM  |
| Vector Store | ChromaDB              |
| RAG Engine   | LlamaIndex            |
| Backend      | FastAPI (JWT-secured) |
| Frontend     | Streamlit             |
| Automation   | n8n                   |
| Security     | Audit logging, JWT    |

## 📌 Roadmap

- [ ] Add document classification before embedding
- [ ] Multi-user roles & access management
- [ ] UI for document browsing & retrieval
- [ ] Dockerized GPU inference node
