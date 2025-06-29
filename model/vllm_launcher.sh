#!/bin/bash
# Script to launch LLaMA 3 using vLLM for Legal AI

set -e

# Configuration
MODEL_NAME=${MODEL_NAME:-"meta-llama/Llama-2-70b-chat-hf"}
MODEL_PATH=${MODEL_PATH:-""}  # Local path to model if downloaded
HOST=${VLLM_HOST:-"0.0.0.0"}
PORT=${VLLM_PORT:-8001}
GPU_MEMORY_UTILIZATION=${GPU_MEMORY_UTILIZATION:-0.95}
MAX_MODEL_LEN=${MAX_MODEL_LEN:-4096}
TENSOR_PARALLEL_SIZE=${TENSOR_PARALLEL_SIZE:-1}
TRUST_REMOTE_CODE=${TRUST_REMOTE_CODE:-false}

# Logging
echo "Starting vLLM server..."
echo "Model: $MODEL_NAME"
echo "Host: $HOST"
echo "Port: $PORT"
echo "GPU Memory Utilization: $GPU_MEMORY_UTILIZATION"
echo "Max Model Length: $MAX_MODEL_LEN"
echo "Tensor Parallel Size: $TENSOR_PARALLEL_SIZE"

# Check if model path is provided (local model)
if [ -n "$MODEL_PATH" ] && [ -d "$MODEL_PATH" ]; then
    echo "Using local model at: $MODEL_PATH"
    MODEL_ARG="$MODEL_PATH"
else
    echo "Using Hugging Face model: $MODEL_NAME"
    MODEL_ARG="$MODEL_NAME"
fi

# Launch vLLM with OpenAI-compatible API
python -m vllm.entrypoints.openai.api_server \
    --model "$MODEL_ARG" \
    --host "$HOST" \
    --port "$PORT" \
    --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
    --max-model-len "$MAX_MODEL_LEN" \
    --tensor-parallel-size "$TENSOR_PARALLEL_SIZE" \
    --trust-remote-code "$TRUST_REMOTE_CODE" \
    --served-model-name "legal-ai-model" \
    --disable-log-requests \
    --enable-prefix-caching \
    --max-num-seqs 64 \
    --max-paddings 256

# Note: Adjust tensor-parallel-size based on your GPU setup:
# - 1 for single GPU
# - 2 for 2 GPUs  
# - 4 for 4 GPUs
# - 8 for 8 GPUs

# Example usage:
# For local deployment with downloaded model:
# MODEL_PATH="/path/to/llama-2-70b-chat" ./vllm_launcher.sh

# For cloud deployment with Hugging Face model:
# MODEL_NAME="meta-llama/Llama-2-70b-chat-hf" TENSOR_PARALLEL_SIZE=4 ./vllm_launcher.sh

# For development with smaller model:
# MODEL_NAME="meta-llama/Llama-2-7b-chat-hf" MAX_MODEL_LEN=2048 ./vllm_launcher.sh
