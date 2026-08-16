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
<화면>_spec.pdf ──S1──> ScreenSpec ──S2──> TestCase[] ──S3+S4──> 브라우저 실행
                                                                      │
                          report.html <──S6── Verdict[] <──S5────────┘
```

로그인·회원가입 두 화면을 각각 두 구현에 대해 검증한 결과
(CHEETAH의 로컬 Qwen2.5-7B-AWQ 사용, 2026-08-16 실측):

| 화면 | 대상 | 결과 |
|---|---|---|
| 로그인 | `good` — 기획서를 지킨 구현 | **7/7 PASS** (통과율 100%) |
| 로그인 | `bad` — 검증을 빠뜨린 구현 | **3 PASS / 4 FAIL** — 빠진 규칙 4개를 정확히 지목, 오탐 0건 |
| 회원가입 | `good` | **14/14 PASS** (통과율 100%) |
| 회원가입 | `bad` | **11 PASS / 3 FAIL** — 빠진 규칙 3개를 정확히 지목, 오탐 0건 |

`bad`에서도 구현돼 있는 검증은 PASS로 나온다. 한 리포트 안에
"구현된 규칙은 PASS, 누락된 규칙은 FAIL"이 함께 나오는 것이 판정을 신뢰할 근거다.

회원가입 화면이 이 점을 더 강하게 보여준다. `required` 규칙을 가진 요소가 6개인데
검증이 빠진 것은 약관 동의 하나뿐이고, Prova는 **그 하나만** FAIL로 지목한다.
닉네임도 `min_length`는 PASS, `max_length`만 FAIL이다 — 한 요소의 규칙 중 일부만
구현된 경우를 규칙 단위로 분리해 짚어낸다.

S1 추출 정확도도 골든 데이터와 대조해 확인했다 — 두 화면 **22/22 통과**.
로컬 7B가 `constraints` 키 이름(`min_length`, `require_uppercase`, `same_as` 등)까지
정확히 뽑아내므로, 계획 단계에서 우려했던 "7B가 검증 규칙을 놓칠 위험"은 해소됐다.
Claude API가 필요하지 않다.

---

## 저장소에 있는 다른 도구

`extract_auth_search_json.py`는 이 파이프라인보다 먼저 만들어진 독립 추출 도구다.
**HWPX 파싱과 OCR**을 지원하는데 이 파이프라인에는 없는 능력이라 그대로 둔다.
`feature/figma-extractor` 브랜치에는 Figma 추출기가 있다.
자세한 내용은 [docs/reference/legacy-extractors.md](docs/reference/legacy-extractors.md).

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
uv run prova run --pdf fixtures/specs/login_spec.pdf  --url http://localhost:8100/good --backend mock
uv run prova run --pdf fixtures/specs/login_spec.pdf  --url http://localhost:8100/bad  --backend mock
uv run prova run --pdf fixtures/specs/signup_spec.pdf --url http://localhost:8100/good --backend mock
uv run prova run --pdf fixtures/specs/signup_spec.pdf --url http://localhost:8100/bad  --backend mock

# 5. 리포트 열기
start runs/<run-id>/report.html
```

실제 로컬 LLM으로 돌리려면 [docs/CHEETAH_SETUP.md](docs/CHEETAH_SETUP.md)를 따라
CHEETAH에 vLLM을 올리고 `--backend` 없이 실행한다.

```powershell
uv run prova check     # vLLM 연결 + 정형 출력 동작 확인
uv run pytest          # 테스트 170개 (vLLM 없으면 정확도 측정 22개는 자동 skip)
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
│   ├── rule_expander.py        규칙 -> 위반값 + 요소 간 의존 해석 (순수 함수, LLM 없음)
│   └── generator.py            케이스 조립 + 기대 결정 + 요소 유형별 액션
├── s3_grounder/dom_locator.py  라벨 -> 실제 요소 (selector-first)
├── s4_executor/                Playwright 실행 + 스텝별 증거 수집
├── s5_verifier/                PASS/FAIL 판정
├── s6_report/                  JSON + HTML 리포트
├── nodes.py                  (state) -> state 노드
├── pipeline.py               노드 순차 실행
├── graph.py                  같은 노드를 LangGraph 로 배선
└── cli.py                    prova run / prova check

sut/                          테스트 대상 미니 웹앱 — 로그인·회원가입 (good / bad)
fixtures/specs/               화면기획서 md / pdf / 정답(golden) — 화면마다 한 벌
docs/
├── specs/                    Prova_서비스명세서.md (개발 기준 문서)
├── reference/                계획서·주제개요서·멘토링보고서
├── teaching/                 티칭 노트 9개 + overview.html (그림 자료)
├── CHEETAH_SETUP.md          GPU 서버 vLLM 세팅 절차
└── README.md                 문서 안내
```

---

## 설계 판단 (명세서와 다르게 한 것)

명세서([`docs/specs/Prova_서비스명세서.md`](docs/specs/Prova_서비스명세서.md))를
구현하면서 네 군데를 바꿨다. 각각 이유가 있다.

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

### 4. `constraints`에 요소 간 규칙(`same_as`)을 넣었다

명세서의 `constraints`는 값 하나만 보고 판정되는 규칙만 담는다. 그런데 회원가입의
'비밀번호 확인'은 자기 규칙이 없고 **다른 요소와 같아야 한다**는 것이 규칙이다.

이 규칙 하나가 값 생성 방식을 바꿨다. 요소 단위 함수로는 값을 정할 수 없어
화면 단위 해석(`resolve_values`)이 필요해졌고, 의존 순서대로 풀어야 한다.

더 미묘한 문제는 '한 케이스는 한 규칙만 위반한다'는 계약과 부딪히는 지점이다.
비밀번호에 위반값을 넣으면 비밀번호 확인 값도 함께 어긋나 두 규칙이 동시에 깨진다.

→ 위반값을 먼저 고정하고 **그것에 의존하는 값들을 다시 계산한다**
(`resolve_values(inputs, overrides=...)`). 비밀번호 확인은 위반값과 같은 값이 되어,
깨지는 규칙은 여전히 비밀번호의 것 하나다.

같은 이유로 체크박스·선택 요소에는 문자 규칙을 전개하지 않는다. 사용자가 문자를
직접 입력하지 않으므로 '8자 미달인 체크 상태' 같은 입력은 만들 수 없고, 억지로
만들면 실행이 조작 오류로 실패해 판정이 뭉개진다. 이 요소들에서 검증할 수 있는
것은 '선택/체크하지 않았을 때'뿐이다.

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

### 7B는 표의 행을 조용히 빠뜨린다 — 그리고 그게 전 케이스 오탐이 된다

회원가입 화면(요소 7개)에서 로컬 7B가 **버튼 행을 빠뜨렸다.** 검증 규칙과 에러
메시지가 모두 `-`인 행이라 중요하지 않다고 판단한 것으로 보인다. 로그인 화면
(요소 3개)에서는 일어나지 않았다.

제출 버튼이 없으면 폼이 제출되지 않는다. 그러면 에러가 뜰 일도 없어 **모든 위반
케이스가 FAIL**이 되고, 정상 케이스도 이동하지 않아 FAIL이 된다. 원인은 추출인데
리포트는 "구현이 전부 틀렸다"고 보고한다. 출력 길이 제한 때문이 아니었다 — 응답은
1,635자로 상한에 한참 못 미쳤다.

→ 두 겹으로 막는다.
1. **예방**: `pdf_parser`가 표에서 읽은 요소 ID 목록을 프롬프트에 직접 넣는다
   (`declared_element_ids`). 표의 몇 번째 열이 ID인지는 괘선으로 정해지므로 추론할
   여지가 없다. **코드가 확실히 아는 사실을 추론에 맡기지 않는다.**
2. **검출**: 추출 결과를 그 목록과 대조해 빠진 요소를 경고한다
   (`structural_warnings`). 버튼이 하나도 없으면 따로 경고한다.

예방만 두면 모델·버전이 바뀔 때 조용히 다시 깨진다. 검출만 두면 매번 깨진 리포트를
받는다. 둘 다 필요하다.

### few-shot 예시를 바꾸면 다른 필드의 정확도가 함께 움직인다

회원가입 화면을 추가하며 프롬프트의 few-shot 예시를 교체했다. 원래 예시가 회원가입
화면이었는데, 그대로 두면 회원가입 정확도 측정이 **예시를 베낀 결과**를 재는 셈이라
'비밀번호 변경'이라는 다른 화면으로 바꿨다.

그 교체가 **로그인의 `sample_value` 추출을 깨뜨렸다.** 새 예시에서 `sample_value`가
대부분 `null`이었던 것이 원인으로 보인다. 정상 케이스가 등록되지 않은 계정 값을 쓰게
되어 구현 결함 없이 실패하는, 이미 한 번 겪은 오탐이 되돌아왔다.

→ 예시의 데이터 표를 2열로 만들어 '열 제목 = 라벨' 대응을 보이게 하고, 두 요소에
실제 값을 채웠다. 프롬프트 설명도 표 제목 예시를 열거해 강화했다.

**교훈은 프롬프트가 전역 상태라는 것이다.** 한 화면을 위해 고친 프롬프트가 다른
화면의 다른 필드를 조용히 망가뜨린다. 화면별 골든 테스트를 모두 돌려야 확인된다.

### element_id에 공백이 섞여 들어온다

7B가 `password_confirm`을 `password_confir m`으로 냈다. 그러면 `same_as` 참조가
어긋나 교차 필드 위반 케이스가 아예 생성되지 않고, `case_id`에 공백이 들어가
스크린샷 경로도 깨진다.

→ `element_id`의 공백을 지우고 `same_as` 참조도 함께 고친다. 판정 강도를 낮추는
종류의 보정이 아니라 표기 복원이므로(슬러그에 공백이 들어갈 여지가 없고 고칠 방법도
하나뿐이다) 경고 없이 처리한다. 매 실행마다 뜨는 경고는 정작 중요한 경고를 묻는다.

---

## 아직 안 한 것

Figma 연동 · VLM 요소 탐지(S3 fallback) · Self-Healing 루프 · LLM 기반 실패 분류 ·
**검색 화면** · locator 캐시 · 병렬 실행 · CI 연동 · 한 PDF에 여러 화면.

모두 명세서에 있다. 회원가입 화면은 2차에서 붙였고(위 결과 표), 다음은 검색 화면이다.
검색은 '에러가 뜨는가'가 아니라 '결과 건수가 맞는가'를 봐야 해서 `Expectation` 확장이
필요하다 — 지금까지의 화면들과 검증 축이 다르다.

`AgentState`의 `heal_count`/`max_heal`과 `ElementLocation`의 `bbox`/`confidence`는
그 확장에서 상태 구조가 흔들리지 않게 미리 자리를 잡아둔 필드다.

### 2차 착수 전 확인할 것

**VRAM 10GiB에 LLM과 VLM을 동시에 올릴 수 없다.** Qwen2.5-7B-AWQ(약 5.6GB) +
LocateAnything-3B(약 6.5GB)는 넘친다. MIG 추가 할당(`2g.20gb` 이상)을 요청하거나
시간 분할 서빙을 설계해야 한다 — **9월 중 GPU 담당자에게 미리 문의.**
