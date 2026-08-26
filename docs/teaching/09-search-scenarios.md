# 09. 규칙으로 표현할 수 없는 검증 — 검색 화면

> 대상 파일: `src/prova/models.py`(`Scenario`), `src/prova/s1_spec_extractor/pdf_parser.py`,
> `src/prova/s2_case_generator/generator.py`, `fixtures/specs/search_spec.*`

---

## 이 화면이 왜 다른가

로그인·회원가입의 검증은 **모두 같은 모양**이었습니다.

> 규칙을 어긴 값을 넣는다 → 기획서가 지정한 에러가 뜨는가?

그래서 `rule_expander`가 규칙에서 위반값을 만들어낼 수 있었고, 그게 이 프로젝트의 핵심
아이디어였습니다([03-llm-vs-code.md](03-llm-vs-code.md) 참고).

검색은 다릅니다.

> 정상 입력을 넣는다 → 정해진 결과가 나오는가?

`notebook`을 검색하면 3건이 나와야 한다는 것은 **값의 흠이 아닙니다.** `notebook`은
모든 입력 규칙을 만족하는 멀쩡한 검색어입니다. 어겨진 규칙이 없으니 위반값을 만들 수도
없습니다.

---

## 결과부터

| 화면 | 대상 | 결과 |
|---|---|---|
| 검색 | `good` | **6/6 PASS** |
| 검색 | `bad` | **3 PASS / 3 FAIL** (오탐 0건) |

로그인(7/7, 3·4)과 회원가입(14/14, 11·3)은 그대로 유지됐습니다.

> 이 노트를 쓴 뒤 검색에 건수 검증을 더해 8건이 됐습니다(`bad` 는 4 PASS / 4 FAIL).
> 그 이야기는 [10-counting-dom.md](10-counting-dom.md) 에 있습니다. 아래 내용은
> 문구 기반 확인만 있던 시점의 기록이고, 그 한계가 10번 노트의 출발점입니다.

---

## `Scenario` — 기획서가 데이터를 직접 제시하는 경로

```python
# models.py
class Scenario(BaseModel):
    given: dict[str, str]   # element_id -> 입력값
    expect_text: str        # 화면에 노출돼야 하는 문구
```

기획서에는 이렇게 적습니다.

```markdown
## 6. 예시 검색

| 검색어 | 노출돼야 하는 문구 |
|---|---|
| notebook | 검색 결과 3건 |
| zzzz | 검색 결과가 없습니다. |
```

**기획서가 이 표를 주지 않으면 이 검증은 불가능합니다.** 그건 도구의 한계가 아니라
기획서의 한계입니다 — "검색이 잘 되어야 한다"만 적혀 있으면 사람도 확인할 수 없습니다.
Prova가 요구하는 것은 기획서가 원래 갖춰야 하는 구체성입니다.

### 왜 `expect_text` 하나로 좁혔나

`Expectation` 전체(`type` + `value` + `url_contains`)를 담을 수도 있었습니다. 그러면
표현력은 늘지만 **S1이 `type` 열거값까지 골라야 합니다.** 로컬 7B에 선택지를 늘리면
추출이 흔들리고, S1이 흔들리면 검증이 조용히 무력해집니다.

기획서가 '노출돼야 하는 문구'를 적어 두는 형태면 문구 비교만으로 충분합니다. 모델이
표에서 문구를 옮기기만 하면 됩니다.

> 나중에 건수를 DOM에서 직접 세야 하면 **필드를 추가**합니다. 이 필드의 의미를 넓혀
> 재해석하면 안 됩니다. **필드 이름이 할 수 있는 일을 말하고 있어야 합니다.**

### 케이스 유형은 `positive`다

헷갈리기 쉬운 부분입니다. "결과가 없습니다"를 확인하는 케이스는 negative처럼 보입니다.
아닙니다.

```python
# generator.py 의 _scenario_cases()
type="positive"    # 규칙을 어긴 값이 아니라 정상 입력이다
violates=None      # 어긴 규칙이 없다
```

`negative`로 두면 S5의 판정이 뒤집혀 **'에러가 떠야 PASS'**가 됩니다
([05-verdict-report.md](05-verdict-report.md)의 뒤집힌 논리 참고). `zzzz` 검색은 에러가
아니라 정상 동작이므로, 뒤집으면 판정이 정반대가 됩니다.

---

## `bad`에 심은 결함이 새로운 종류다

| 심은 결함 | 왜 새로운가 |
|---|---|
| **대소문자를 구분한다** (기획서는 구분 안 함) | 값에 흠이 없고 구현도 검사를 한다. **검사 방법이 다르다** |
| **0건일 때 안내 문구를 안 보여준다** | 틀린 것을 보여주는 게 아니라 보여줘야 할 것을 안 보여준다 |
| 검색어 최소 길이 검증 없음 | 회원가입 C3와 같은 종류 — 규칙 경로가 이 화면에서도 도는지 확인 |

**첫 번째가 이 화면을 추가한 이유입니다.** 로그인·회원가입의 결함은 모두 '값을 검사하지
않았다'였고 위반값 생성으로 잡혔습니다. 대소문자 결함은 검사를 하는데 방법이 다릅니다 —
규칙에서 위반값을 만드는 방식으로는 **도달할 경로가 없습니다.**

---

## 검색 화면에서 새로 조심한 것들

### '결과 없음'은 에러가 아니다

```html
<!-- role=alert 를 붙이지 않는다 -->
<div class="empty">검색 결과가 없습니다.</div>
```

붙이면 `capture_page_state`가 이걸 에러로 읽고, 정상 케이스가 "에러가 노출됐다"로
판정됩니다. 실제로 결과 0건은 사용자 잘못도 구현 결함도 아닙니다.

검증 에러(`검색어는 2자 이상...`)만 `role="alert"`을 답니다. **화면의 의미 구조가
판정에 직접 영향을 줍니다.**

### 첫 진입과 '빈 값으로 제출'을 구분해야 한다

```python
if query is None:        # 파라미터가 없다 = 첫 진입
    return render_search(request, "good")
if not query:            # 빈 문자열로 제출됐다
    return render_search(request, "good", error=MSG_QUERY_REQUIRED)
```

구분하지 않으면 아무 조작도 하지 않은 화면에 에러가 떠 있게 됩니다. `method=get`을 쓰기
때문에 이 구분이 자연스럽게 됩니다 — 첫 진입에는 `query` 파라미터 자체가 없습니다.

### SUT 주석에 기대 문구를 쓰지 않는다

만들다가 실제로 헷갈린 부분입니다. 템플릿 주석에 `검색 결과가 없습니다.`를 그대로
적어 뒀더니, `curl | grep`으로 확인할 때 **결과가 있을 때도 그 문구가 잡혔습니다.**

판정에는 영향이 없습니다(`inner_text`는 주석을 읽지 않습니다). 하지만 `page.content()`를
보는 검사나 사람이 하는 확인에서 '문구가 있다'로 잘못 읽힙니다.

---

## 가장 값진 교훈: 표에 적힌 사실을 AI에 맡기지 마라

이번 확장에서 **같은 종류의 실패를 네 번** 겪었습니다.

| 무엇을 | 7B가 한 일 | 결과 |
|---|---|---|
| 요소 목록 | 7행 표에서 버튼 행을 생략 | 폼이 제출되지 않아 전 케이스 FAIL |
| `screen_id` | `화면 ID \| search`를 두고 `product_search`를 지어냄 | `case_id`·스크린샷 경로가 어긋남 |
| `sample_value` | few-shot 표 제목을 바꾸자 두 번 놓침 | 정상 케이스가 오탐 FAIL |
| `scenarios` | 없는 시나리오를 창작, 실패 조건 표의 행을 가져옴 | 없는 기대를 요구해 오탐 |

넷 다 **표에 그대로 적혀 있는 값**입니다. 추론할 것이 없습니다.

`pdfplumber`가 이미 괘선으로 열을 갈라 읽고 있는데, 그걸 다시 AI에게 "읽어 줘"라고
부탁하고 있었던 것입니다. 그리고 매번 프롬프트를 고쳐서 달래려 했습니다.

### 그래서 코드가 읽는다

```python
doc.declared_element_ids()    # 요소 ID 목록      -> 프롬프트 주입 + 누락 경고
doc.declared_screen_meta()    # 화면 ID / 경로    -> 프롬프트 주입 + 불일치 경고
doc.declared_sample_values()  # 라벨 -> 예시값    -> 프롬프트 주입 + 누락 경고
doc.declared_scenarios()      # 입력-결과 짝      -> 이 값을 그대로 쓴다
```

마지막 것은 주입에서 멈추지 않고 **결과를 대체합니다.** 보정이 아니라 애초에 AI가
판단할 일이 아니었기 때문입니다. AI가 다른 답을 냈다는 사실은 경고로 남겨, 프롬프트가
나빠지고 있는지 알 수 있게 합니다.

### 표를 고르는 기준이 캡션이 아니라 열 제목이다

이게 이 방식을 견고하게 만드는 핵심입니다.

```
열 제목이 전부 요소 라벨    -> 요소별 예시값 표 (sample_value)
열 제목이 일부만 라벨       -> 입력-결과 짝 표 (scenarios)
라벨이 하나도 없음          -> 개요·실패 조건 등 다른 표
```

기획서마다 표 제목이 '테스트 계정'/'입력 예시 데이터'/'예시 검색'으로 달라도 이 기준은
흔들리지 않습니다. 실제로 이 기준 하나가 검색 기획서의 두 표를 정확히 갈라냈습니다.

캡션으로 판별하려면 표 위쪽 본문 텍스트와 표의 위치를 맞춰 봐야 하고, 기획서마다 다른
표현을 모두 열거해야 합니다. 열 제목은 **표 안에 있고 구조로 정해져 있습니다.**

### AI에 남는 일

```
"8자 이상"          -> min_length: 8        ← 자연어 판단, AI
"비밀번호와 동일"     -> same_as: password    ← 자연어 판단, AI
표의 3열 값          -> 라벨                 ← 조회, 코드
표의 행 수           -> 요소 개수             ← 세기, 코드
```

**표 안에 구조로 적혀 있지 않은 것만 AI가 판단합니다.** 이 경계가
[03-llm-vs-code.md](03-llm-vs-code.md)의 판단 기준에 한 줄을 더합니다 —
"필요한 게 조회라면 코드로 짠다."

### 테스트에도 구멍이 있었다

`scenarios` 창작을 처음에는 **테스트가 잡지 못했습니다.** 골든 데이터에 시나리오가 없으면
비교를 `skip`하고 있었기 때문입니다.

```python
# 이렇게 되어 있었다
if not golden.scenarios:
    pytest.skip("기획서에 예시 시나리오가 없다")
```

'있어야 할 것이 있는가'만 보고 **'없어야 할 것이 없는가'는 보지 않았습니다.** 파이프라인
케이스 수가 14건에서 15건으로 늘어난 것을 눈으로 보고서야 알았습니다.

> **없는 것을 확인하는 테스트가 있는 것을 확인하는 테스트보다 자주 빠집니다.**

---

## 확인해보기

```powershell
# 테스트 대상 웹앱
uv run uvicorn sut.app:app --port 8100 --reload --reload-dir sut

# 검색 검증 (GPU 없이 mock 으로)
uv run prova run --pdf fixtures/specs/search_spec.pdf --url http://localhost:8100/good --backend mock
uv run prova run --pdf fixtures/specs/search_spec.pdf --url http://localhost:8100/bad  --backend mock

# AI 없이 표에서 읽어내는 것들
uv run python -c "
from prova.s1_spec_extractor.pdf_parser import parse_pdf
for stem in ('login', 'signup', 'search'):
    doc = parse_pdf(f'fixtures/specs/{stem}_spec.pdf')
    print(f'--- {stem}')
    print('  개요   ', doc.declared_screen_meta())
    print('  예시값 ', doc.declared_sample_values())
    print('  시나리오', doc.declared_scenarios())
"

# 검색 관통 테스트
uv run pytest tests/test_search_e2e.py -v

# 실제 모델 정확도 (vLLM 없으면 skip)
uv run pytest tests/test_s1_golden.py -v
```

대소문자 결함을 눈으로 보려면:

```powershell
uv run prova run --pdf fixtures/specs/search_spec.pdf --url http://localhost:8100/bad `
  --only scenario-005 --headed --slow 500 --hold 3
```

`notebook`을 입력하고 검색을 누르는데 결과가 하나도 나오지 않습니다. `--url`을
`.../good`으로 바꾸면 3건이 나옵니다.

---

## 다음

명세서 §1이 1차 대상으로 꼽은 네 화면 중 셋이 끝났습니다. 남은 하나(아이디/비밀번호
찾기)는 기존 기계로 대부분 덮입니다 — 이메일 형식 검증과 에러 문구 대조가 대부분이어서
로그인의 부분집합에 가깝습니다.

그래서 다음으로 값이 큰 것은 화면이 아니라 **결과를 DOM에서 직접 세는 능력**입니다.
지금 검색 검증은 기획서가 "검색 결과 N건" 문구를 노출한다고 적어 둔 데 기대고 있습니다.
WITCHES 실물 화면이 건수를 문구로 보여주지 않으면 그 경로가 막힙니다.

그 확장은 S3의 **'정확히 1개만 확정한다'**는 계약을 건드립니다
([04-grounding-execution.md](04-grounding-execution.md) 참고). 그 계약이 지금까지 판정을
신뢰할 근거였으므로, 느슨하게 만들면 기존 화면에 영향이 갑니다. 반복 요소 탐지를 별도
경로로 두고 기존 경로는 그대로 남기는 편이 안전합니다.

→ 실제로 그렇게 했습니다. [10-counting-dom.md](10-counting-dom.md) 에서 이어집니다.
계약을 건드릴 필요가 없었다는 것이 결론입니다 — 한 겹 내려가 보니 컨테이너는 여전히
정확히 1개였고, 여러 개인 것은 그 안의 항목이었습니다.

---

이전: [08-screen-expansion.md](08-screen-expansion.md) — 화면을 늘릴 때 실제로 깨진 것들
다음: [10-counting-dom.md](10-counting-dom.md) — 화면이 말해 주지 않는 것을 확인하기
