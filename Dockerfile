# Local Legal AI — one image for both the API and the web UI (see docker-compose.yml).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/huggingface \
    HF_HUB_DISABLE_TELEMETRY=1

WORKDIR /app

# Tesseract OCR (English) so scanned, image-only PDFs can be indexed.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# CPU-only PyTorch keeps the image ~2 GB smaller than the default CUDA build;
# embeddings for legal documents run comfortably on CPU.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch

COPY requirements.txt .
RUN pip install -r requirements.txt

# Bake the embedding model into the image so the running containers never
# need internet access (documents and questions stay on this machine).
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY . .

RUN useradd --create-home --uid 1000 legalai \
    && mkdir -p /app/data /app/logs \
    && chown -R legalai:legalai /app/data /app/logs
USER legalai

# Runtime data (users, vector store, audit and analytics databases, inbox) lives in /app/data.
VOLUME ["/app/data"]
EXPOSE 8000 8501

# The API by default; the ui service overrides the command.
CMD ["python", "-m", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
