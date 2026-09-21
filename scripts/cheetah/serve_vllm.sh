#!/bin/bash
# Qwen2.5-7B-Instruct-AWQ 서빙 (A100 MIG 1g.10gb, VRAM 10GiB)
#
#   bash ~/serve_vllm.sh            포그라운드 (로그 보면서)
#   tmux new -d -s vllm 'bash ~/serve_vllm.sh > /tmp/vllm.log 2>&1'   상시 실행
#
# VRAM 계산 근거:
#   AWQ 4bit 가중치      약 5.6 GB
#   vLLM 오버헤드        약 1.0 GB
#   -> KV 캐시           약 2.4 GB
#   Qwen2.5-7B 는 GQA(KV head 4, layer 28, head_dim 128)라 토큰당 KV 가 약 56KB.
#   2.4GB / 56KB = 약 43,000 토큰 -> 8K 컨텍스트 요청 5개 동시 처리 가능.
#
# OOM 이 나면 순서대로 시도한다.
#   1) MAX_LEN=4096          KV 캐시 요구량을 절반으로
#   2) EXTRA="--enforce-eager"  CUDA graph 메모리(수백 MB) 포기
#   3) MODEL=Qwen/Qwen2.5-3B-Instruct-AWQ  로 교체
set -e

VENV=/tmp/vllm-venv
MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct-AWQ}"
MAX_LEN="${MAX_LEN:-8192}"
PORT="${PORT:-8000}"
UTIL="${UTIL:-0.90}"
EXTRA="${EXTRA:-}"

if [ ! -d "$VENV" ]; then
  echo "venv 가 없습니다 (/tmp 는 pod 재시작 시 사라집니다)."
  echo "먼저 실행하세요:  bash ~/setup_vllm.sh"
  exit 1
fi

# 모델 가중치는 영구 볼륨에 둔다. 재시작 후 재다운로드를 피하기 위해서다.
export HF_HOME="$HOME/.cache/huggingface"

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
  --quantization awq_marlin \
  --max-model-len "$MAX_LEN" \
  --gpu-memory-utilization "$UTIL" \
  --port "$PORT" \
  --host 0.0.0.0 \
  $EXTRA
