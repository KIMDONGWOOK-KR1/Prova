#!/bin/bash
# CHEETAH vLLM 환경 구축 / 복구 스크립트
#
# 이 pod 은 저장소가 두 종류다.
#   /home/jovyan  10GB, CephFS 영구 볼륨 — 재시작에도 남는다
#   /tmp          1.5TB, 컨테이너 overlay — 재시작하면 사라진다
#
# vLLM + torch + CUDA 라이브러리는 약 10GB 라 홈에 들어가지 않는다. 그래서
# venv 는 /tmp 에 두고, 다운로드가 오래 걸리는 모델 가중치는 홈에 보존한다.
# pod 이 재시작되면 venv 만 날아가므로 이 스크립트를 다시 실행하면 된다
# (모델은 이미 홈에 있으므로 재다운로드하지 않는다).
#
#   bash ~/setup_vllm.sh
set -e

VENV=/tmp/vllm-venv
export PATH="$HOME/.local/bin:$PATH"

# uv 캐시를 /tmp 로 보낸다.
#
# 기본값은 ~/.cache/uv 인데, 홈은 10GB 쿼터라 CUDA 라이브러리를 풀다가
# "Disk quota exceeded (os error 122)" 로 설치가 죽는다. torch + CUDA wheel 은
# 압축 상태로도 수 GB 이고 캐시에 풀어 두므로 홈에 둘 수 없다.
export UV_CACHE_DIR=/tmp/uv-cache

# 모델 가중치는 영구 볼륨에. 재시작 후 5.6GB 를 다시 받지 않기 위해서다.
# 홈 10GB 중 모델이 약 5.6GB 를 쓰고 4GB 가 남는다 — 캐시를 /tmp 로 옮겼기에
# 성립하는 배치다.
export HF_HOME="$HOME/.cache/huggingface"

echo "[1/3] uv 설치 확인"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
uv --version

echo "[2/3] venv 생성 ($VENV)"
if [ ! -d "$VENV" ]; then
  uv venv --python 3.11 "$VENV"
fi

echo "[3/3] vLLM 설치 (CUDA 12.x 빌드)"
source "$VENV/bin/activate"

# CUDA 버전을 반드시 12.x 로 맞춰야 한다. 두 단계 모두 필요하다.
#
# 이 노드의 드라이버는 570.133.20 = CUDA 12.8 까지 지원한다.
#
# (1) torch: --torch-backend=cu128
#     기본 wheel 은 torch 2.13.0+cu130 을 끌어오는데 CUDA 13 은 드라이버 580+ 를
#     요구한다. 그대로 두면 torch.cuda.is_available() 이 False 가 된다
#     ("NVIDIA driver is too old (found version 12080)").
#
# (2) vllm 바이너리: GitHub 릴리스의 +cu129 wheel 을 직접 지정
#     PyPI 기본 wheel 은 CUDA 13 으로 빌드돼 있어 libcudart.so.13 을 요구하고,
#     경로를 잡아 import 를 통과시켜도 실제 커널 실행에서 죽는다
#     ("RuntimeError: gptq_marlin_repack ... marlin_repack.cu:344").
#     cu128 wheel 은 배포되지 않지만 cu129 는 있고, CUDA 는 같은 major 안에서
#     minor version compatibility 를 보장하므로 12.8 드라이버에서 동작한다.
#     (cu130 이 실패한 이유는 major 가 달라 이 보장이 적용되지 않기 때문이다)
VLLM_VER="${VLLM_VER:-0.24.0}"
WHEEL="https://github.com/vllm-project/vllm/releases/download/v${VLLM_VER}/vllm-${VLLM_VER}+cu129-cp38-abi3-manylinux_2_28_$(uname -m).whl"
echo "  wheel: $WHEEL"
uv pip install --quiet "$WHEEL" --torch-backend=cu128
python -c "
import torch, vllm
print('vllm       :', vllm.__version__)
print('torch      :', torch.__version__)
print('CUDA 사용가능:', torch.cuda.is_available())
assert torch.cuda.is_available(), 'GPU 를 쓸 수 없습니다 — torch CUDA 빌드와 드라이버 버전을 확인하세요'
print('GPU        :', torch.cuda.get_device_name(0))
"

echo ""
echo "완료. 서빙은 다음으로:"
echo "  bash ~/serve_vllm.sh"
