# CHEETAH GPU 서버에 vLLM 올리기

로컬 LLM(Qwen2.5-7B-Instruct-AWQ)을 CHEETAH에 상시 서빙하고, 로컬 개발 머신에서 SSH 터널로 붙이는 절차.

## 구조

```
[CHEETAH  A100 MIG 1g.10gb]                 [로컬 Windows]
 vLLM (Qwen2.5-7B-AWQ)     ←── SSH 터널 ──→  Prova (S1·S2·S6)
 OpenAI 호환 :8000                           Playwright + Chromium (S3·S4)
                                             SUT (FastAPI :8100)
```

GPU 서버에는 브라우저를 설치하지 않는다. Playwright는 로컬에서 돌고, 코드 입장에서 GPU 모델은 그냥 `http://localhost:8000/v1`이다.

---

## 1. 왜 7B AWQ인가 (VRAM 10GiB 계산)

| 항목 | 크기 |
|---|---|
| Qwen2.5-7B-Instruct-AWQ 가중치 (4bit) | 약 5.6 GB |
| vLLM 오버헤드 (activation, CUDA graph) | 약 1.0 GB |
| **KV 캐시로 남는 양** | **약 2.4 GB** |

Qwen2.5-7B는 GQA(KV head 4개, 28 layer, head_dim 128)라 토큰당 KV가
`2 × 28 × 4 × 128 × 2 bytes ≈ 56 KB`다. 2.4GB면 **약 43,000 토큰** 분량이므로
8K 컨텍스트 요청 5개를 동시에 처리할 수 있다. 3B로 내려갈 필요가 없다.

**주의: VLM과 동시 적재는 불가능하다.** LocateAnything-3B(약 6.5GB)를 함께 올리면
10GiB를 넘는다. 1차 목표는 selector-only라 지금은 문제없지만, 2차에서 VLM을
도입하기 전에 MIG 추가 할당(`2g.20gb` 이상)을 요청하거나 시간 분할 서빙을
설계해야 한다. **9월 중에 GPU 담당자에게 미리 문의할 것.**

---

## 2. CHEETAH 접속 후 환경 준비

```bash
ssh <user>@<cheetah-host>

# MIG 인스턴스 확인 — UUID를 적어둔다
nvidia-smi -L
# 예: MIG 1g.10gb  Device 0: (UUID: MIG-xxxxxxxx-xxxx-...)

# uv 설치 (없으면)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# vLLM 전용 환경
mkdir -p ~/vllm && cd ~/vllm
uv venv --python 3.11
source .venv/bin/activate
uv pip install vllm
```

MIG 환경에서는 GPU를 UUID로 지정해야 할 수 있다:

```bash
export CUDA_VISIBLE_DEVICES=MIG-xxxxxxxx-xxxx-...
```

---

## 3. 모델 서빙

```bash
vllm serve Qwen/Qwen2.5-7B-Instruct-AWQ \
  --quantization awq_marlin \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90 \
  --port 8000
```

옵션별 이유:

| 옵션 | 이유 |
|---|---|
| `--quantization awq_marlin` | AWQ 4bit. Ampere(A100)에서 marlin 커널이 가장 빠르다 |
| `--max-model-len 8192` | 기획서 PDF 텍스트 + few-shot이 들어가는 크기. 늘리면 KV 캐시가 부족해진다 |
| `--gpu-memory-utilization 0.90` | 10GiB의 90%. 1.0으로 두면 OOM 위험이 있다 |

메모리가 부족하다는 오류가 나면 순서대로 시도한다:

1. `--max-model-len 4096` — KV 캐시 요구량을 절반으로
2. `--enforce-eager` — CUDA graph 메모리(수백 MB)를 포기하고 확보
3. `Qwen/Qwen2.5-3B-Instruct-AWQ`로 교체 — `configs/default.yaml`의 `llm.model`만 바꾸면 된다

### 상시 실행 (세션이 끊겨도 유지)

```bash
# tmux 안에서 띄우면 SSH 연결이 끊겨도 살아 있다
tmux new -s vllm
# (위 vllm serve 명령 실행)
# Ctrl+B, D 로 빠져나오기

# 다시 붙을 때
tmux attach -t vllm
```

---

## 4. 로컬에서 터널 열기

**로컬 Windows 터미널**(PowerShell)에서:

```powershell
ssh -N -L 8000:localhost:8000 <user>@<cheetah-host>
```

`-N`은 명령 실행 없이 터널만 유지한다는 뜻이다. 이 창은 열어둔 채로 둔다.

---

## 5. 연결 확인

```powershell
cd C:\dev\prova
uv run prova check
```

기대 출력:

```
엔드포인트: http://localhost:8000/v1
연결 정상 · 모델 Qwen/Qwen2.5-7B-Instruct-AWQ
guided_json 확인 중...
guided_json 정상 · 응답 {'ok': True, 'note': '정상'}
```

`prova check`는 연결만 보지 않고 **guided_json이 실제로 걸리는지**까지 확인한다.
연결은 되는데 구조화 출력이 동작하지 않으면 S1·S2가 조용히 불안정해지기 때문이다.

---

## 6. 실제 모델로 관통 실행

```powershell
# 터미널 1: SUT
uv run uvicorn sut.app:app --port 8100

# 터미널 2: 검증
uv run prova run --pdf fixtures/specs/login_spec.pdf --url http://localhost:8100/good
uv run prova run --pdf fixtures/specs/login_spec.pdf --url http://localhost:8100/bad
```

`--backend mock`을 빼면 설정의 기본값(`vllm`)이 쓰인다.

### 확인할 것

`good` 실행에서 실패가 나오면 **S1 추출 문제일 가능성이 높다.** 7B가 기획서에서
`constraints`를 놓치거나 에러 문구를 다르게 옮긴 경우다. 다음으로 원인을 좁힌다:

```powershell
# S1 출력을 골든과 비교
uv run pytest tests/test_s1_golden.py -v
```

`constraints` 키 이름이 흔들리면(`min_len` 등) `extractor.py`의 매핑 표를 프롬프트에서
더 강하게 못 박거나 few-shot 예시를 늘린다. 그래도 안 되면 계획서 R4의 대응대로,
Claude API로 gold 라벨을 소량 만들어 few-shot에 넣는다(추론은 계속 로컬).

---

## 문제 해결

| 증상 | 원인과 대응 |
|---|---|
| `prova check`에서 연결 실패 | 터널이 닫혔거나 vLLM이 죽었다. `tmux attach -t vllm`으로 로그 확인 |
| `guided_json 실패` | vLLM 버전이 낮아 `guided_json`을 무시했을 수 있다. `uv pip install -U vllm` |
| OOM | 위 3절의 순서대로 시도 |
| 추론이 매우 느림 | MIG `1g`는 A100 전체의 약 1/7 연산량이다. 개발에는 충분하나, 대량 평가는 야간 배치로 돌린다 |
| 터널이 방화벽에 막힘 | 계획서 R3 대응: GPU 서버에서 파이프라인 전체를 실행한다. `playwright install --with-deps chromium` 후 `configs/default.yaml`의 `base_url`을 `http://localhost:8000/v1`로 두고 그대로 실행 |
