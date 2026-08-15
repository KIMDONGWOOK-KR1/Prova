# Prova

**설계 문서를 읽어 테스트를 스스로 만들고, 실제 브라우저로 실행해 기획과 구현의 불일치를 찾아내는 웹 GUI QA 에이전트.**

팀 소인배 · 2026 하반기 WE-Meet · 의뢰: ㈜WITCHES

---

## 왜 만드는가

개발 현장에서 기획서와 실제 구현이 어긋나는 일이 잦고, 그걸 찾아 고치는 데 시간이 든다.
지금 그 확인은 QA 담당자가 화면기획서를 읽고 손으로 테스트 케이스를 만들어 하나씩 눌러보는 수작업이다.

Prova는 이 작업을 자동화한다. 증명하려는 명제는 하나다 —
**"기획서에 적힌 검증 규칙이 구현에 빠져 있으면 Prova가 그것을 짚어낸다."**

### 지금 동작하는 것

```
login_spec.pdf ──S1──> ScreenSpec ──S2──> TestCase[] ──S3+S4──> 브라우저 실행
                                                                      │
                          report.html <──S6── Verdict[] <──S5────────┘
```

같은 기획서로 두 구현을 검증한 결과 (CHEETAH의 로컬 Qwen2.5-7B-AWQ 사용, 2026-08-15 실측):

| 대상 | 결과 |
|---|---|
| `good` — 기획서를 지킨 구현 | **7/7 PASS** (통과율 100%) |
| `bad` — 의도적으로 검증을 빠뜨린 구현 | **3 PASS / 4 FAIL** — 빠진 규칙 4개를 정확히 지목, 오탐 0건 |

`bad`에서도 `required` 검증은 구현돼 있어 PASS로 나온다. 한 리포트 안에
"구현된 규칙은 PASS, 누락된 규칙은 FAIL"이 함께 나오는 것이 판정을 신뢰할 근거다.

S1 추출 정확도도 골든 데이터와 대조해 확인했다 — **10/10 통과**. 로컬 7B가 기획서에서
`constraints`(`min_length`, `require_uppercase`, `require_special`)를 키 이름까지 정확히
뽑아내므로, 계획 단계에서 우려했던 "7B가 검증 규칙을 놓칠 위험"은 해소됐다. Claude API가 필요하지 않다.

---

## 코드를 처음 보는 사람은

`docs/teaching/overview.html`을 브라우저로 열면 파이프라인 구조와 결과를 그림으로 볼 수 있다.
그다음 `docs/teaching/00-overview.md`부터 번호 순으로 읽으면 각 단계의 설계 판단을 알 수 있다.

---

## 빨리 돌려보기

```powershell
# 1. 의존성
uv sync --extra dev
uv run playwright install chromium

# 2. 기획서 PDF 생성 (md -> pdf)
uv run python scripts/make_spec_pdf.py

# 3. 테스트 대상 웹앱 띄우기 (별 터미널)
uv run uvicorn sut.app:app --port 8100

# 4. 검증 — GPU 없이도 mock 백엔드로 파이프라인 전체가 돈다
uv run prova run --pdf fixtures/specs/login_spec.pdf --url http://localhost:8100/good --backend mock
uv run prova run --pdf fixtures/specs/login_spec.pdf --url http://localhost:8100/bad  --backend mock

# 5. 리포트 열기
start runs/<run-id>/report.html
```

실제 로컬 LLM으로 돌리려면 [docs/CHEETAH_SETUP.md](docs/CHEETAH_SETUP.md)를 따라
CHEETAH에 vLLM을 올리고 `--backend` 없이 실행한다.

```powershell
uv run prova check     # vLLM 연결 + guided_json 동작 확인
uv run pytest          # 테스트 93개
```

---

## 구조

```
src/prova/
├── models.py                 데이터 계약 (명세서 §3) — 파이프라인 전체의 타입
├── text_utils.py             PDF 문구 ↔ 화면 문구 비교 규칙
├── llm/                      백엔드 추상화 (base / mock / vllm)
├── s1_spec_extractor/        PDF -> ScreenSpec
│   ├── pdf_parser.py           결정적 추출 (pdfplumber, LLM 없음)
│   └── extractor.py            LLM 구조화 (guided_json)
├── s2_case_generator/        ScreenSpec -> TestCase[]
│   ├── rule_expander.py        규칙 -> 위반값 (순수 함수, LLM 없음)
│   └── generator.py            케이스 조립 + 기대 결정
├── s3_grounder/dom_locator.py  라벨 -> 실제 요소 (selector-first)
├── s4_executor/                Playwright 실행 + 스텝별 증거 수집
├── s5_verifier/                PASS/FAIL 판정
├── s6_report/                  JSON + HTML 리포트
├── nodes.py                  (state) -> state 노드
├── pipeline.py               노드 순차 실행
├── graph.py                  같은 노드를 LangGraph 로 배선
└── cli.py                    prova run / prova check

sut/                          테스트 대상 미니 로그인 앱 (good / bad)
fixtures/specs/               로그인 화면기획서 md / pdf / 정답(golden)
docs/
├── specs/                    Prova_서비스명세서.md (개발 기준 문서)
├── reference/                계획서·주제개요서·멘토링보고서
├── teaching/                 티칭 노트 8개 + overview.html (그림 자료)
├── CHEETAH_SETUP.md          GPU 서버 vLLM 세팅 절차
└── README.md                 문서 안내
```

---

## 설계 판단 (명세서와 다르게 한 것)

명세서([`docs/specs/Prova_서비스명세서.md`](docs/specs/Prova_서비스명세서.md))를
구현하면서 세 군데를 바꿨다. 각각 이유가 있다.

### 1. negative 케이스는 규칙을 하나씩만 위반시킨다

명세서 예시 `signup-pw-no-upper-002`는 `require_uppercase`와 `require_special`을
동시에 위반한다. 그러면 FAIL이 떴을 때 **어느 규칙이 미구현인지 분리되지 않는다.**

```
require_uppercase 위반 -> "a1!aaaaa"   (대문자만 없음, 나머지 규칙 충족)
require_special   위반 -> "Aa1aaaaa"   (특수문자만 없음)
min_length        위반 -> "Aa1!aaa"    (길이만 부족)
```

리포트에서 규칙과 실패가 1:1로 연결되어, 개발자가 어느 검증 로직을 추가해야 하는지 바로 안다.

### 2. `rule_expander`를 LLM 밖 순수 함수로 뒀다

'대문자 1자 이상' 규칙에서 '대문자가 없는 값'을 만드는 데는 추론이 필요하지 않다.
코드로 짜면 결정적이고, 공짜이고, **생성값이 정말 그 규칙만 위반하는지 단위 테스트로
보증**할 수 있다. LLM 출력에는 그런 보증을 걸 수 없다.

LLM은 판단이 필요한 곳에만 쓴다 — S1의 자연어→스키마 매핑, S2의 케이스 제목.

### 3. S1을 결정적 추출 + LLM 구조화 2단계로 나눴다

명세서 §10-2는 PDF 추출을 🔴 API 후보로 봤다. 그건 이미지·자유서술이 섞인 실무
기획서 전제다. 텍스트 레이어가 있는 PDF는 pdfplumber가 표와 글자를 정확히 읽으므로,
LLM에 남는 일은 텍스트→JSON 구조화뿐이고 로컬 7B로 충분하다.
WITCHES 실물 PDF가 오면 `pdf_parser.py`만 교체하면 된다.

---

## 구현 중 드러난 것들

문서로 예측하지 못했고 코드를 돌려서 알게 된 문제들. 각각 대응이 코드에 남아 있다.

### PDF는 원문을 그대로 복원하지 못한다

```
원문   비밀번호는 8자 이상이며 대문자·특수문자를 각 1자 이상 포함해야 합니다.
추출   '비밀번호는 8자\n이상이며 대문자·\n특수문자를 각\n1자 이상\n포함해야 합니다.'
```

`8자\n이상이며`의 개행은 공백으로 바꿔야 맞고, `대문자·\n특수문자`의 개행은 지워야 맞다.
한글은 문자 단위로도 줄바꿈되므로 텍스트만 보고는 판별할 수 없다.

→ 복원을 포기하고 **비교를 정규형에서** 한다 (`text_utils.loosen`). 공백만 무시하고,
문구 자체가 다르면 반드시 FAIL이 된다.

### 필수 입력 문구는 요소별이 아니라 화면 공통이다

기획서 §2 표의 `에러 메시지`는 형식 검증용 문구이고, "필수 입력 항목입니다."는
§4 실패 조건 표에 화면 단위로 따로 적혀 있다.

→ `ScreenSpec.required_message` 필드를 추가했다. 이 값이 없으면 문구를 억측하지 않고
`error_shown`으로 격하해 '에러가 떴는지'만 확인한다. **억측한 문구는 오탐을 만들고,
오탐이 나오는 QA 도구는 개발자가 신뢰하지 않게 된다.**

### 규칙을 만족하는 값 ≠ 등록된 계정의 값

`rule_expander`가 만든 `Aa1!aaaa`는 비밀번호 규칙을 다 지키지만 등록된 계정의
비밀번호가 아니다. 그래서 정상 케이스가 **구현 결함 없이** 실패했다.

→ `UIElement.sample_value` 필드를 추가하고, 기획서 §5 테스트 계정을 정상 케이스에 쓴다.

### `guided_json`은 오류 없이 조용히 무시된다

vLLM 0.24에서 `guided_json`이 제거됐는데, **에러가 나지 않는다.** 요청한 필드명
(`screen_name`)이 아니라 모델이 지어낸 이름(`screenName`)이 돌아오고 응답이 마크다운
코드펜스로 감싸진다. 스키마가 강제되지 않으면 S1이 `constraints` 키를 흔들고, 그러면
`rule_expander`가 규칙을 인식하지 못해 **검증이 조용히 무력해진다.**

→ OpenAI 표준 `response_format={"type": "json_schema", ...}`로 교체했다. 표준이라
버전 업그레이드에 강건하고, `prova check`는 연결뿐 아니라 **필드명을 대조해 스키마가
실제로 걸렸는지**까지 확인한다.

### mock 백엔드는 조용히 쓰이면 안 된다

vLLM 연결 실패 시 mock으로 자동 폴백하면, 아무 추론도 하지 않은 리포트가 정상
결과처럼 보인다. QA 도구에서 가장 위험한 실패다.

→ 연결 실패는 명확한 오류로 알리고, mock은 `--backend mock`으로 직접 고를 때만 쓴다.
리포트 HTML 상단에도 경고를 띄운다.

---

## 1차 범위에서 제외한 것

Figma 연동 · VLM 요소 탐지(S3 fallback) · Self-Healing 루프 · LLM 기반 실패 분류 ·
회원가입/검색 화면 · locator 캐시 · 병렬 실행 · CI 연동.

모두 명세서에 있고, 관통선이 초록불이 된 지금 순서대로 붙인다.
`AgentState`의 `heal_count`/`max_heal`과 `ElementLocation`의 `bbox`/`confidence`는
그 확장에서 상태 구조가 흔들리지 않게 미리 자리를 잡아둔 필드다.

### 2차 착수 전 확인할 것

**VRAM 10GiB에 LLM과 VLM을 동시에 올릴 수 없다.** Qwen2.5-7B-AWQ(약 5.6GB) +
LocateAnything-3B(약 6.5GB)는 넘친다. MIG 추가 할당(`2g.20gb` 이상)을 요청하거나
시간 분할 서빙을 설계해야 한다 — **9월 중 GPU 담당자에게 미리 문의.**
