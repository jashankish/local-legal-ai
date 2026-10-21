#!/bin/bash
# Run a small instruction model locally with llama.cpp's OpenAI-compatible server.
# Works on CPU and Apple Silicon (Metal); no GPU or Ollama required.
#
#   bash model/llamacpp_launcher.sh
#
# First run creates model/.venv, builds llama-cpp-python and downloads the
# model (~1 GB). The server listens on 127.0.0.1:8001 and serves the model as
# "legal-ai-model" — the defaults in .env.example — so no configuration is needed.

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
LLAMA_VENV=${LLAMA_VENV:-"$ROOT/.venv"}
MODEL_DIR=${MODEL_DIR:-"$ROOT/models"}
MODEL_REPO=${MODEL_REPO:-"Qwen/Qwen2.5-1.5B-Instruct-GGUF"}
MODEL_FILE=${MODEL_FILE:-"qwen2.5-1.5b-instruct-q4_k_m.gguf"}
HOST=${LLM_HOST:-"127.0.0.1"}
PORT=${LLM_PORT:-8001}
CONTEXT=${LLM_CONTEXT:-8192}

if [ ! -x "$LLAMA_VENV/bin/python" ]; then
    PYTHON_BIN=""
    for candidate in python3.12 python3.11 python3.10 python3; do
        if command -v "$candidate" &> /dev/null; then PYTHON_BIN="$candidate"; break; fi
    done
    echo "Creating $LLAMA_VENV with $PYTHON_BIN and building llama-cpp-python (several minutes)..."
    "$PYTHON_BIN" -m venv "$LLAMA_VENV"
    "$LLAMA_VENV/bin/pip" install --quiet --upgrade pip
    if [ "$(uname -s)" = "Darwin" ]; then export CMAKE_ARGS="-DGGML_METAL=on"; fi
    "$LLAMA_VENV/bin/pip" install --quiet "llama-cpp-python[server]" huggingface_hub
fi

if [ ! -f "$MODEL_DIR/$MODEL_FILE" ]; then
    echo "Downloading $MODEL_REPO/$MODEL_FILE..."
    "$LLAMA_VENV/bin/python" -c "from huggingface_hub import hf_hub_download; hf_hub_download('$MODEL_REPO', '$MODEL_FILE', local_dir='$MODEL_DIR')"
fi

echo "Serving $MODEL_FILE as legal-ai-model on http://$HOST:$PORT (OpenAI-compatible API)"
exec "$LLAMA_VENV/bin/python" -m llama_cpp.server \
    --model "$MODEL_DIR/$MODEL_FILE" \
    --model_alias legal-ai-model \
    --host "$HOST" \
    --port "$PORT" \
    --n_ctx "$CONTEXT" \
    --n_gpu_layers -1
