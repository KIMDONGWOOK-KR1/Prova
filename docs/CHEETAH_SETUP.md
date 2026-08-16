# CHEETAH GPU 서버에 vLLM 올리기

로컬 LLM(Qwen2.5-7B-Instruct-AWQ)을 CHEETAH에 서빙하고, 로컬 개발 머신에서 SSH 터널로 붙이는 절차.
**2026-08-15 실제로 구축해 동작을 확인한 내용이다.**

## 접속 정보

```
ssh <user>@<cheetah-host> -p <port> -i private.pem
```

**실제 주소·포트·계정은 이 저장소에 두지 않는다.** 저장소가 public 이라 학교 인프라 주소를
공개하면 불필요한 공격 표면이 된다. `.env.example` 을 `.env` 로 복사해 채워 쓰고, 실제 값은
팀 채널에서 공유한다.

PEM 키(`private.pem`)도 `.gitignore` 로 제외돼 있다.
**이 키가 저장소에 함께 올라가면 GPU 서버 접근권이 그대로 유출된다.**

## 구조

```
[CHEETAH  A100 MIG 1g.10gb]              [로컬 Windows]
 vLLM (Qwen2.5-7B-AWQ)   ←── SSH 터널 ──→  Prova (S1·S2·S6)
 OpenAI 호환 :8000                        Playwright + Chromium (S3·S4)
                                          SUT (FastAPI :8100)
```

GPU 서버에는 브라우저를 설치하지 않는다. 코드 입장에서 GPU 모델은 그냥 `http://localhost:8000/v1`이다.

---

## 빠른 시작 (환경이 이미 구축된 경우)

```powershell
# 1. 터널 (이 창은 열어둔다)
ssh -N -L 8000:localhost:8000 -i private.pem -p <port> <user>@<cheetah-host>

# 2. 서버가 살아 있는지
uv run prova check
```

`prova check`가 실패하면 서버가 죽었거나 pod이 재시작된 것이다. 아래 "pod 재시작 후 복구"로 간다.

---

## 이 환경의 함정 세 가지

구축하면서 실제로 막혔던 지점들이다. 순서대로 겪게 된다.

### 1. 홈 디렉터리가 10GB뿐이다

| 위치 | 용량 | 성질 |
|---|---|---|
| `/home/jovyan` | **10GB** | CephFS 영구 볼륨 — pod 재시작에도 남는다 |
| `/tmp` (overlay) | 1.5TB | 컨테이너 레이어 — **재시작하면 사라진다** |

vLLM은 torch·CUDA 라이브러리까지 **약 12GB**라 홈에 들어가지 않는다. uv 캐시를 기본값
(`~/.cache/uv`)으로 두면 설치 중 `Disk quota exceeded (os error 122)`로 죽는다.

→ **venv와 uv 캐시는 `/tmp`, 모델 가중치는 홈**에 둔다. 다운로드가 가장 오래 걸리는
자원(모델 5.2GB)을 영구 볼륨에 보존하고, 재설치가 빠른 쪽을 휘발성 저장소에 두는 배치다.
`setup_vllm.sh`가 `UV_CACHE_DIR=/tmp/uv-cache`, `HF_HOME=$HOME/.cache/huggingface`로 이를 처리한다.

CephFS는 삭제가 매우 느리다. 홈 캐시를 지울 일이 생기면 `nohup rm -rf ... &`로 백그라운드에서 돌려라
(9GB 삭제에 몇 분 걸린다).

### 2. CUDA 버전이 세 갈래로 갈린다

이 노드의 드라이버는 **570.133.20 = CUDA 12.8까지** 지원한다. 그런데 기본 설치는 CUDA 13을 끌어온다.

```
uv pip install vllm                     -> torch 2.13.0+cu130
   ImportError 없이 torch.cuda.is_available() = False
   "NVIDIA driver is too old (found version 12080)"

uv pip install vllm --torch-backend=cu128   -> torch 2.11.0+cu128 (OK)
                                            + vllm 바이너리는 여전히 CUDA 13
   ImportError: libcudart.so.13: cannot open shared object file
   (경로를 잡아 import를 통과시켜도 커널 실행에서 죽는다:
    RuntimeError: gptq_marlin_repack ... marlin_repack.cu:344)
```

→ **torch와 vLLM 바이너리를 모두 CUDA 12.x로 맞춰야 한다.**
cu128 wheel은 배포되지 않지만 **cu129는 있고**, CUDA는 같은 major 안에서
minor version compatibility를 보장하므로 12.8 드라이버에서 동작한다.
(cu130이 실패한 이유는 major가 달라 이 보장이 적용되지 않기 때문이다.)

```bash
WHEEL="https://github.com/vllm-project/vllm/releases/download/v0.24.0/vllm-0.24.0+cu129-cp38-abi3-manylinux_2_28_x86_64.whl"
uv pip install "$WHEEL" --torch-backend=cu128
```

`setup_vllm.sh`가 이 조합을 쓴다. 확인된 동작 조합:

| | 버전 |
|---|---|
| vLLM | 0.24.0 **+cu129** |
| torch | 2.11.0+cu128 |
| 드라이버 | 570.133.20 (CUDA 12.8) |

### 3. `guided_json`이 제거됐다 — 오류 없이 조용히 무시된다

vLLM 0.24에서 `guided_json`이 사라졌다. 문제는 **에러가 나지 않는다는 것이다.**

```
요청: extra_body={"guided_json": {"properties": {"screen_name":..., "url_path":...}}}
응답: ```json
      { "screenName": "로그인", "path": "/login" }
      ```
```

필드명이 모델이 지어낸 것으로 바뀌고 마크다운 코드펜스가 붙는다. QA 도구에서 이런
무성 실패는 위험하다 — 스키마가 강제되지 않으면 S1이 `constraints` 키를 흔들고,
그러면 `rule_expander`가 규칙을 인식하지 못해 **검증이 조용히 무력해진다.**

→ OpenAI 표준 **`response_format={"type": "json_schema", ...}`**를 쓴다. `vllm_backend.py`가
이 방식이고, `prova check`는 연결뿐 아니라 **필드명을 대조해 스키마가 실제로 걸렸는지**까지 검증한다.

---

## 처음부터 구축 / pod 재시작 후 복구

pod이 재시작되면 `/tmp`가 비어 venv가 사라진다. 모델은 홈에 남아 있으므로 재다운로드하지 않는다.

```bash
ssh <user>@<cheetah-host> -p <port> -i private.pem

# 1) 환경 구축 (약 2분. 모델이 이미 있으면 재다운로드 없음)
tmux new -d -s setup 'bash ~/setup_vllm.sh > /tmp/setup.log 2>&1'
tail -f /tmp/setup.log     # "CUDA 사용가능: True" 가 나와야 한다

# 2) 서빙 (모델 적재·CUDA graph 캡처까지 약 3분)
tmux new -d -s vllm 'bash ~/serve_vllm.sh > /tmp/vllm.log 2>&1'
tail -f /tmp/vllm.log      # "Application startup complete." 를 기다린다

# 3) 서버에서 직접 확인
curl -s localhost:8000/v1/models
```

두 스크립트(`~/setup_vllm.sh`, `~/serve_vllm.sh`)는 홈에 있어 재시작 후에도 남는다.
안에 왜 그런 옵션을 쓰는지 주석으로 적어 두었다.

**MIG UUID는 pod을 다시 받으면 바뀐다.** `serve_vllm.sh`가 `nvidia-smi -L`로 매번 조회하므로
따로 손댈 필요는 없다.

---

## 실측 메모리 (VRAM 10.2GiB)

| 항목 | 실측 |
|---|---|
| 전체 VRAM | 10.2 GiB |
| 모델 적재 (AWQ 4bit) | 5.29 GiB |
| CUDA graph | 0.51 GiB |
| **KV 캐시** | **1.56 GiB = 29,120 토큰** |

29K 토큰이면 8K 컨텍스트 요청 3~4개를 동시 처리하는 양이다. S1 추출은 요청당 3K 토큰 정도라 충분하다.

계획 단계 계산(KV 2.4GB, 43K 토큰)보다 작은데, CUDA graph 메모리를 계산에 넣지 않았기 때문이다.
KV 캐시를 늘리려면 로그가 안내하는 대로 `UTIL=0.9625 bash ~/serve_vllm.sh`로 올리거나
`EXTRA="--enforce-eager"`로 CUDA graph를 포기한다.

### 2차 VLM 도입 시 경고

**LLM(5.29GiB) + LocateAnything-3B(약 6.5GiB)는 10.2GiB에 동시 적재할 수 없다.**
1차는 selector-only라 문제없지만, 2차 착수 전에 MIG 추가 할당(`2g.20gb` 이상)을 요청하거나
시간 분할 서빙을 설계해야 한다. 할당 신청에 시간이 걸릴 수 있으니 **9월 중 GPU 담당자에게 미리 문의할 것.**

---

## 검증 절차

```powershell
# 연결 + 정형 출력
uv run prova check
#   연결 정상 · 모델 Qwen/Qwen2.5-7B-Instruct-AWQ
#   정형 출력 정상 · 응답 {'ok': True, 'note_text': '정상'}

# 7B 의 실제 추출 정확도 (골든 비교)
uv run pytest tests/test_s1_golden.py -v

# 전체 관통
uv run uvicorn sut.app:app --port 8100        # 별 터미널
uv run prova run --pdf fixtures/specs/login_spec.pdf --url http://localhost:8100/good
uv run prova run --pdf fixtures/specs/login_spec.pdf --url http://localhost:8100/bad
```

2026-08-17 실측 결과: **S1 골든 45/45 통과**(로그인·회원가입·검색 세 화면), 로그인 good **7/7** / bad **3 PASS · 4 FAIL**, 회원가입 good **14/14** / bad **11 PASS · 3 FAIL**, 검색 good **8/8** / bad **4 PASS · 4 FAIL**. 오탐 0건.
로컬 7B가 기획서에서 `constraints`를 정확히 추출했으므로 Claude API 없이 진행할 수 있다.

---

## 문제 해결

| 증상 | 원인과 대응 |
|---|---|
| `prova check` 연결 실패 | 터널이 닫혔거나 pod이 재시작됐다. `tmux attach -t vllm`으로 로그 확인, 없으면 위 복구 절차 |
| `Disk quota exceeded` | uv 캐시가 홈을 쓰고 있다. `UV_CACHE_DIR=/tmp/uv-cache` 확인 |
| `libcudart.so.13` / `driver is too old` | CUDA 버전 불일치. 위 함정 2번 참고 — cu129 wheel + `--torch-backend=cu128` |
| `gptq_marlin_repack ... marlin_repack.cu` | 같은 원인(CUDA 13 커널). 위와 동일 |
| 응답이 코드펜스로 감싸짐 / 필드명이 다름 | 정형 출력이 무시됐다. `response_format` 사용 여부 확인 (함정 3번) |
| OOM | `MAX_LEN=4096` → `EXTRA="--enforce-eager"` → `MODEL=Qwen/Qwen2.5-3B-Instruct-AWQ` 순서로 시도 |
| 추론이 느림 | MIG `1g`는 A100 전체의 약 1/7 연산량이다. 개발에는 충분하나 대량 평가는 야간 배치로 |
| 터널이 방화벽에 막힘 | GPU 서버에서 파이프라인 전체 실행. `playwright install --with-deps chromium` 후 `base_url`을 그대로 두고 실행 |
