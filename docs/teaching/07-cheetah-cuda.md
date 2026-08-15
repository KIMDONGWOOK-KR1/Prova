# 07. CHEETAH GPU 서버 — 실제로 막힌 세 지점

> 관련 문서: `docs/CHEETAH_SETUP.md` (실행 절차), `src/prova/llm/vllm_backend.py`

---

## 배경: 왜 로컬 모델인가

두 가지 이유입니다.

**1. WE-Meet의 취지** — 학생이 AI 기술을 직접 내재화하는 것이 목적입니다. API를 호출만 하면
모델을 다루는 경험이 남지 않습니다.

**2. 데이터 프라이버시** — QA 도구는 고객사의 기획서와 화면을 다룹니다. 그걸 외부 API로
보내는 것을 꺼리는 기업이 많습니다. 온프레미스(자체 서버) 실행이 B2B 도구의 요건입니다.

그래서 CHEETAH의 GPU에 모델을 직접 올렸습니다.

---

## 우리가 받은 환경

```
GPU     : NVIDIA A100 80GB PCIe 의 MIG 1g.10gb 조각
VRAM    : 10.2 GiB
vCPU    : 3 코어
RAM     : 23 GiB
드라이버 : 570.133.20 (CUDA 12.8 지원)
```

### MIG란

**Multi-Instance GPU.** A100 하나를 여러 조각으로 나눠 여러 사람이 동시에 쓰는 기술입니다.
우리는 `1g.10gb` 조각을 받았습니다 — GPU를 7등분한 것 중 하나이고 메모리는 10GB입니다.

연산 능력도 약 7분의 1입니다. 개발과 디버깅에는 충분하지만, 대량 평가는 야간 배치로 돌려야
합니다.

### 왜 7B 모델이 들어가는가

일반적으로 7B(70억 파라미터) 모델은 메모리를 이만큼 씁니다.

```
FP16 (16비트) : 7B × 2바이트 = 약 14 GB    → 10.2GiB 에 안 들어감
AWQ  (4비트)  : 7B × 0.5바이트 = 약 5.3 GB → 들어감
```

**AWQ 양자화**란 모델의 숫자들을 16비트에서 4비트로 압축하는 기술입니다. 정확도가 조금
떨어지지만 메모리가 4분의 1이 됩니다.

실측 결과:

| 항목 | 실측 |
|---|---|
| 전체 VRAM | 10.2 GiB |
| 모델 적재 (AWQ 4bit) | 5.29 GiB |
| CUDA graph | 0.51 GiB |
| **KV 캐시** | **1.56 GiB = 29,120 토큰** |

**KV 캐시**란 AI가 긴 글을 처리할 때 앞부분 계산 결과를 기억해두는 공간입니다. 이게 없으면
매 단어마다 처음부터 다시 계산해야 해서 매우 느려집니다.

29,120 토큰이면 8,000 토큰 요청 3~4개를 동시에 처리하는 양입니다. S1 추출은 요청당 3,000
토큰 정도이므로 충분합니다.

---

## 함정 1: 홈 디렉터리가 10GB뿐이다

```
/home/jovyan   10GB    CephFS 영구 볼륨 — pod 재시작에도 남는다
/tmp           1.5TB   컨테이너 레이어 — 재시작하면 사라진다
```

이 서버는 Kubernetes pod입니다. 컨테이너가 다시 시작되면 `/tmp`가 초기화됩니다.

문제: vLLM은 torch와 CUDA 라이브러리까지 합쳐 **약 12GB**입니다. 홈에 들어가지 않습니다.
게다가 uv(패키지 관리자)의 캐시가 기본적으로 `~/.cache/uv`라, 설치 중 이런 에러가 났습니다.

```
× Failed to download `nvidia-cusolver-cu12==11.7.3.90`
╰─▶ failed to flush file ...: Disk quota exceeded (os error 122)
```

### 해결: 무엇을 어디에 둘지 나눈다

| 무엇 | 어디 | 이유 |
|---|---|---|
| venv + 라이브러리 (12GB) | `/tmp` | 재설치가 2분이면 된다 |
| uv 캐시 | `/tmp` | 크고, 없어도 재다운로드하면 된다 |
| **모델 가중치 (5.2GB)** | **홈** | 다운로드가 가장 오래 걸린다. 영구 보존 가치가 있다 |

**판단 기준: 다시 만드는 데 오래 걸리는 것을 영구 저장소에 둔다.**

```bash
# setup_vllm.sh
export UV_CACHE_DIR=/tmp/uv-cache
export HF_HOME="$HOME/.cache/huggingface"    # 모델은 홈
```

### 부수적으로 배운 것: CephFS는 삭제가 느리다

잘못 쌓인 홈 캐시 9.3GB를 지우는 데 몇 분이 걸렸습니다. 네트워크 파일 시스템이라 파일
하나하나 삭제 요청을 보내기 때문입니다. 대용량 삭제는 백그라운드로 돌려야 합니다.

```bash
nohup rm -rf ~/.cache/uv > /tmp/rm.log 2>&1 &
```

---

## 함정 2: CUDA 버전이 세 갈래로 갈렸다

**이게 가장 오래 붙잡은 문제입니다.**

### CUDA 버전 호환 규칙

GPU 프로그램은 세 층으로 되어 있습니다.

```
[내 코드]  →  [CUDA 툴킷으로 빌드된 바이너리]  →  [드라이버]  →  [GPU 하드웨어]
```

바이너리를 빌드할 때 쓴 CUDA 버전이 드라이버가 지원하는 버전보다 **높으면** 동작하지
않습니다. 우리 드라이버는 CUDA 12.8까지 지원합니다.

**중요한 예외: minor version compatibility.** 같은 major 버전(12.x) 안에서는 새 버전으로
빌드한 것이 오래된 드라이버에서도 동작합니다. 12.9로 빌드해도 12.8 드라이버에서 됩니다.
하지만 **13.x는 안 됩니다** — major가 다르면 이 보장이 없습니다.

### 실제로 겪은 순서

**1차 시도: 그냥 설치**

```bash
uv pip install vllm
```

```
torch 2.13.0+cu130 이 설치됨
UserWarning: CUDA initialization: The NVIDIA driver on your system is too old (found version 12080)
torch.cuda.is_available() = False       ← GPU 를 전혀 못 쓴다
```

**2차 시도: torch를 cu128로 고정**

```bash
uv pip install vllm --torch-backend=cu128
```

```
torch 2.11.0+cu128        ← torch 는 해결
ImportError: libcudart.so.13: cannot open shared object file
```

torch는 고쳐졌는데 **vLLM 자체 바이너리가 CUDA 13**이었습니다. `--torch-backend`는 torch만
다루기 때문입니다.

**3차 시도: 라이브러리 경로를 잡아 import 통과**

`libcudart.so.13`이 실제로 설치돼 있어서(`nvidia/cu13/lib/`) 경로를 넣으니 import는 됐습니다.
그런데 실제로 모델을 올리자 이렇게 죽었습니다.

```
RuntimeError: gptq_marlin_repack, /workspace/csrc/.../gptq_marlin_repack.cu:344,
```

`marlin`은 AWQ 양자화 모델을 빠르게 계산하는 커널 이름입니다. **CUDA 13으로 빌드된 커널이
12.8 드라이버에서 실행되지 못한 것**입니다. 에러 메시지 본문이 비어 있는 것이 그 증거입니다.

### 최종 해결: vLLM의 cu129 wheel

vLLM은 GitHub 릴리스에 CUDA 버전별 wheel을 올려둡니다. 확인해보니 이랬습니다.

```
vllm-0.24.0+cpu-...whl        (CPU)
vllm-0.24.0+cu129-...whl      ← 있다!
vllm-0.24.0-...whl            (기본 = CUDA 13)
```

cu128은 없지만 **cu129가 있고, minor version compatibility 덕에 12.8 드라이버에서
동작합니다.**

```bash
WHEEL="https://github.com/vllm-project/vllm/releases/download/v0.24.0/vllm-0.24.0+cu129-cp38-abi3-manylinux_2_28_x86_64.whl"
uv pip install "$WHEEL" --torch-backend=cu128
```

동작 확인된 조합:

| | 버전 | CUDA |
|---|---|---|
| vLLM | 0.24.0 **+cu129** | 12.9 |
| torch | 2.11.0+cu128 | 12.8 |
| 드라이버 | 570.133.20 | 12.8 지원 |

### 여기서 배울 것

**에러 메시지를 끝까지 읽고 원인 층을 정확히 짚어야 합니다.** "CUDA 문제"라고 뭉뚱그리면
`--torch-backend=cu128`에서 멈춰서 "왜 아직 안 되지?"를 반복합니다. torch와 vLLM 바이너리가
**별개의 층**이라는 것을 알아야 다음 수를 찾습니다.

---

## 함정 3: `guided_json`이 오류 없이 조용히 무시된다

**세 함정 중 가장 위험한 것입니다.**

### 정형 출력(structured output)이란

AI에게 "이 JSON 형식으로만 답해"라고 강제하는 기능입니다. 기술적으로는 스키마를 벗어나는
토큰이 **생성 단계에서 차단**됩니다. 그래서 7B 급 모델도 JSON을 깨뜨리지 않습니다.

이게 없으면 AI가 이렇게 답합니다.

```
알겠습니다! 요청하신 JSON은 다음과 같습니다:
```json
{ "screen_name": ... }
```
추가로 궁금한 점이 있으면 말씀해 주세요.
```

파싱이 불가능하고, 재요청 루프를 만들어야 하고, 그 디버깅에 개발 시간을 다 씁니다.

### 무슨 일이 있었나

처음에 vLLM의 확장 파라미터 `guided_json`을 썼습니다. 그런데 이런 응답이 왔습니다.

```
요청한 스키마: { "screen_name": ..., "url_path": ... }

실제 응답:
```json
{
  "screenName": "로그인",
  "path": "/login"
}
```
```

**필드명이 다릅니다.** `screen_name` → `screenName`, `url_path` → `path`. 그리고 마크다운
코드펜스로 감싸져 있습니다.

vLLM 0.24에서 `guided_json`이 제거됐는데, **에러가 나지 않았습니다.** 알 수 없는 파라미터를
그냥 버린 것입니다.

### 왜 이게 가장 위험한가

만약 필드명이 우연히 맞았다면 어떻게 됐을까요? 프로그램은 정상 동작하는 것처럼 보입니다.
하지만 스키마가 강제되지 않은 상태라 **AI가 언제든 다른 형식을 낼 수 있습니다.**

그리고 그 영향이 이렇게 번집니다.

```
스키마 미적용 → S1 이 constraints 키를 min_len 으로 씀
             → rule_expander 가 그 규칙을 알아보지 못함
             → 위반 케이스가 생성되지 않음
             → 개발자가 그 검증을 빼먹었어도 리포트는 초록불
```

**아무 경고 없이 검증이 무력해집니다.** QA 도구에서 이보다 나쁜 실패는 없습니다.

### 해결: OpenAI 표준 `response_format`

```python
# vllm_backend.py 의 complete_json()
response_format={
    "type": "json_schema",
    "json_schema": {
        "name": schema.get("title") or "Output",
        "schema": schema,
    },
}
```

표준을 쓴 이유:
- vLLM 버전이 올라가도 유지될 가능성이 높다 (`guided_json`처럼 사라지지 않는다)
- Claude API 백엔드를 붙일 때도 같은 개념이다

### 코드펜스를 벗기지 않는 이유

파싱이 실패했을 때, 코드펜스를 제거하고 다시 시도하면 살릴 수 있습니다. 그런데 **일부러
그렇게 하지 않았습니다.**

```python
# vllm_backend.py
fenced = content.lstrip().startswith("```")
hint = (" 응답이 마크다운 코드펜스로 감싸져 있습니다 — 서버가 "
        "response_format 을 적용하지 않았다는 신호입니다." if fenced else "")
raise LLMError(f"JSON 파싱 실패 — 정형 출력이 적용되지 않은 것 같습니다.{hint}...")
```

**파싱이 성공해도 스키마가 강제되지 않은 상태**이기 때문입니다. 조용히 복구하면 검증이
약해진 것을 모르고 넘어갑니다. 여기서 멈추고 원인을 고치는 편이 옳습니다.

### `prova check`가 필드명을 대조한다

```python
if set(result) != {"ok", "note_text"}:
    typer.secho("정형 출력이 무시된 것 같습니다 — 기대 필드 {ok, note_text}, "
                f"실제 {set(result)}", fg=typer.colors.RED)
    raise typer.Exit(1)
```

**연결만 확인하면 부족합니다.** JSON이 유효해도 필드명이 다를 수 있으니, 필드명까지
대조해야 정형 출력이 실제로 걸렸는지 알 수 있습니다.

스모크 테스트의 필드명을 `note_text`로 정한 것도 의도적입니다 — AI가 자연스럽게 지어낼
이름(`note`)과 다르게 잡아야 무시 여부를 판별할 수 있습니다.

---

## 실전 교훈

| 교훈 | 왜 |
|---|---|
| **조용한 실패를 찾아내는 장치를 만들어라** | 에러는 고치면 되지만, 조용한 실패는 존재를 모른다 |
| **에러 메시지를 끝까지 읽어라** | "CUDA 문제"로 뭉뚱그리면 원인 층을 놓친다 |
| **환경 제약을 코드가 아니라 문서에 남겨라** | pod을 다시 받으면 같은 벽에 또 부딪힌다 |
| **저장소 성질을 먼저 파악하라** | 영구/휘발성을 모르고 배치하면 재시작 후 다시 만든다 |

세 함정 모두 **계획 단계에서 예측하지 못한 것들**입니다. 그래서 walking skeleton으로 먼저
끝까지 연결해보는 전략이 유효했습니다 — 문서상 완벽한 계획도 실제로 돌려보면 막힙니다.

---

## 확인해보기

```powershell
# 터널 (이 창은 열어둔다)
ssh -N -L 8000:localhost:8000 -i private.pem -p 32067 jovyan@168.131.30.102

# 연결 + 정형 출력 확인
uv run prova check

# 7B 의 실제 추출 정확도
uv run pytest tests/test_s1_golden.py -v
```

서버 상태를 보려면:

```bash
ssh jovyan@168.131.30.102 -p 32067 -i private.pem
tmux attach -t vllm          # 로그 보기 (Ctrl+B, D 로 나오기)
nvidia-smi                    # GPU 사용량
```

---

## 2차 준비 사항

**LocateAnything-3B(VLM)를 붙일 때 메모리가 문제가 됩니다.**

- BF16으로는 A100에서도 약 12GB → 10.2GiB에 단독으로도 안 들어간다
- 4bit 양자화하면 4GB 미만이 된다

그런데 다행히 **LLM과 VLM이 동시에 필요한 시점이 없습니다.**

```
LLM 사용 : S1(기획서 읽기), S2(케이스 제목)
VLM 사용 : S3(화면에서 요소 찾기)
```

`nodes.py`의 `run_cases`(S3~S5)는 LLM을 전혀 쓰지 않습니다. 그래서 시간을 나눠 쓰면
MIG 추가 할당 없이 2차가 가능합니다. 실측 후 결정할 예정입니다.

---

처음으로: [00-overview.md](00-overview.md)
