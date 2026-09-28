#!/bin/bash
# Qwen3.5-4B (4bit, compressed-tensors) 서빙 — 추출(S1)과 요소 탐지(S3)를 한 모델이 맡는다
# (A100 MIG 1g.10gb, VRAM 9.5GiB)
#
#   bash ~/serve_vllm.sh            포그라운드 (로그 보면서)
#   tmux new -d -s vllm 'bash ~/serve_vllm.sh > /tmp/vllm.log 2>&1'   상시 실행
#
# 가중치는 홈(영구 볼륨)의 $HOME/models/qwen35-4b 에 둔다. 없으면 받는다 — huggingface_hub
# 는 이 노드에서 큰 파일을 받다 멈추므로 curl 로 받는다:
#   mkdir -p ~/models/qwen35-4b && cd ~/models/qwen35-4b && for f in chat_template.jinja \
#     config.json generation_config.json merges.txt model.safetensors.index.json \
#     preprocessor_config.json tokenizer.json tokenizer_config.json \
#     video_preprocessor_config.json vocab.json model-00001-of-00001.safetensors; do
#     curl -sL -C - -o $f https://huggingface.co/cyankiwi/Qwen3.5-4B-AWQ-4bit/resolve/main/$f; done
#
# 실측 (2026-09-28): 적재 3.91GiB, KV 캐시 2.8GiB(약 7.5만 토큰), 기동 시 컴파일 약 7분.
# 선형 어텐션 층이 섞인 구조라 동시 요청 수(--max-num-seqs)를 작게 둔다.
#
# 옛 구성(Qwen2.5-7B-AWQ)으로 되돌리기 — 가중치를 다시 받는다(약 3분):
#   MODEL=Qwen/Qwen2.5-7B-Instruct-AWQ QUANT=awq_marlin SERVED= NUM_SEQS= bash ~/serve_vllm.sh
#   그리고 configs/default.yaml 의 llm.model 을 그 이름으로.
#
# OOM 이 나면 순서대로 시도한다.
#   1) MAX_LEN=4096          KV 캐시 요구량을 절반으로
#   2) EXTRA="--enforce-eager"  CUDA graph 메모리(수백 MB) 포기
set -e

VENV=/tmp/vllm-venv
MODEL="${MODEL:-$HOME/models/qwen35-4b}"
# 클라이언트가 이 이름으로 부른다 (llm.vllm_backend.DEFAULT_MODEL, configs/default.yaml).
# 비우면(SERVED=) vLLM 이 MODEL 을 그대로 이름으로 쓴다.
SERVED="${SERVED-qwen3.5-4b-awq}"
NUM_SEQS="${NUM_SEQS-8}"
MAX_LEN="${MAX_LEN:-8192}"
PORT="${PORT:-8000}"
UTIL="${UTIL:-0.90}"
EXTRA="${EXTRA:-}"
# 양자화 방식. 비우면(QUANT=) vLLM 이 모델 config 를 보고 고른다 — compressed-tensors
# 형식(llm-compressor 로 만든 4bit, 예: cyankiwi/Qwen3.5-4B-AWQ-4bit)에 awq_marlin 을
# 강제하면 기동이 실패한다.
QUANT="${QUANT-}"

if [ ! -d "$VENV" ]; then
  echo "venv 가 없습니다 (/tmp 는 pod 재시작 시 사라집니다)."
  echo "먼저 실행하세요:  bash ~/setup_vllm.sh"
  exit 1
fi

# 모델 가중치는 영구 볼륨에 둔다. 재시작 후 재다운로드를 피하기 위해서다.
export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"

# CUDA 런타임 경로. setup 이 +cu129 wheel 을 넣었으므로 cu12 런타임을 쓴다.
# (cu13 경로를 넣으면 안 된다 — 그 조합은 커널 실행에서 죽는다. setup 주석 참고)
SP="$VENV/lib/python3.11/site-packages"
export LD_LIBRARY_PATH="$SP/nvidia/cuda_runtime/lib:$SP/torch/lib:$LD_LIBRARY_PATH"

# MIG 인스턴스를 UUID 로 지정한다. MIG 환경에서는 인덱스 지정이 동작하지 않는
# 경우가 있어 UUID 를 쓰는 편이 안전하다. pod 을 다시 받으면 UUID 가 바뀌므로
# nvidia-smi -L 로 확인해 갱신할 것.
MIG_UUID=$(nvidia-smi -L | grep -oP 'MIG-[0-9a-f-]+' | head -1)
if [ -n "$MIG_UUID" ]; then
  export CUDA_VISIBLE_DEVICES="$MIG_UUID"
  echo "MIG: $MIG_UUID"
fi

source "$VENV/bin/activate"

echo "모델   : $MODEL"
echo "컨텍스트: $MAX_LEN"
echo "포트   : $PORT"
echo ""

exec vllm serve "$MODEL" \
  ${QUANT:+--quantization "$QUANT"} \
  ${SERVED:+--served-model-name "$SERVED"} \
  ${NUM_SEQS:+--max-num-seqs "$NUM_SEQS"} \
  --max-model-len "$MAX_LEN" \
  --gpu-memory-utilization "$UTIL" \
  --port "$PORT" \
  --host 0.0.0.0 \
  $EXTRA
