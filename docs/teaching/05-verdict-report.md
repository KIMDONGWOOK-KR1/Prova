# 05. S5·S6 — 판정과 리포트, 뒤집힌 논리

> 대상 파일: `src/prova/s5_verifier/assertion_engine.py`, `src/prova/s6_report/report_builder.py`

---

## 가장 헷갈리는 부분: 판정이 뒤집혀 있다

일반적인 테스트는 이렇습니다.

> 기능이 정상 동작하면 PASS

Prova의 **negative 케이스는 반대입니다.**

> **에러가 떠야 PASS**

왜냐하면 우리가 일부러 규칙을 어긴 값을 넣었기 때문입니다. 기획서대로 구현됐다면 에러가
나와야 정상입니다.

| 케이스 | 입력 | 화면 결과 | 판정 | 의미 |
|---|---|---|---|---|
| 정상 | `Abcd123!` | 대시보드로 이동 | PASS | 로그인이 된다 |
| 위반 | `a1!aaaaa` (대문자 없음) | "비밀번호는 8자 이상이며..." | **PASS** | 구현이 규칙을 지킨다 |
| 위반 | `a1!aaaaa` | 에러 없이 통과 | **FAIL** | **구현이 규칙을 빼먹었다** |

세 번째 줄이 이 프로젝트의 목적입니다. 기획과 구현의 불일치를 찾아내는 순간입니다.

이 뒤집힘이 직관과 반대라서 코드를 읽을 때 헷갈립니다. 그래서 판정 함수를 기대 유형별로
나눠 각각의 의미를 **함수 이름으로 드러냈습니다.**

```python
_judge_error_message      # 특정 에러 문구가 떠야 PASS
_judge_error_shown        # 문구는 상관없고, 에러가 떠야 PASS
_judge_redirect           # 특정 경로로 이동해야 PASS
_judge_toast_or_redirect  # 정상 처리 (경로 + 문구 둘 다)
_judge_text_visible       # 특정 문구가 보여야 PASS
```

---

## `PageState` — 브라우저 대신 값으로 다룬다

판정 함수에 Playwright의 `Page` 객체를 넘기면 테스트하기 어렵습니다. 매번 브라우저를 띄워야
하니까요. 그래서 판정에 필요한 정보만 뽑아 **값 객체**로 만듭니다.

```python
@dataclass
class PageState:
    url: str                    # 최종 URL
    text: str                   # 화면에 보이는 전체 텍스트
    error_texts: list[str]      # 에러 영역([role=alert])의 텍스트만
    console_errors: list[str]   # JS 콘솔 오류
```

덕분에 `tests/test_assertion_engine.py`는 브라우저 없이 16개 테스트를 0.1초에 돌립니다.

```python
def state(url="http://h/good/login", text="", errors=None) -> PageState:
    return PageState(url=url, text=text or "", error_texts=errors or [], console_errors=[])

def test_에러가_아예_안_뜨면_FAIL(self):
    v = verify(case, steps_ok(), state(url="http://h/bad/dashboard", text="환영합니다"))
    assert v.verdict == "FAIL"
```

---

## 에러 영역을 따로 모으는 이유

```python
def capture_page_state(page, console_errors=None) -> PageState:
    error_texts = []
    for locator in page.get_by_role("alert").all():     # role="alert" 인 요소만
        ...
```

화면 전체 텍스트에서 에러 문구를 찾으면 안 되는 경우가 있습니다.

**상황**: 어떤 화면은 입력란 아래에 안내 문구를 **상시 표시**합니다.

```html
<p class="hint">비밀번호는 8자 이상이며 대문자·특수문자를 각 1자 이상 포함해야 합니다.</p>
```

이 문구가 항상 화면에 있으면, 에러가 안 떠도 "찾았다"가 되어 **PASS로 판정**됩니다.
버그를 놓치는 것입니다(미탐).

그래서 `error_shown` 판정은 **에러 영역만** 봅니다.

```python
def _judge_error_shown(expected, state) -> tuple[bool, str]:
    if _error_shown(state):        # error_texts 가 비어 있지 않은가
        return True, ...
    return False, "에러가 노출되지 않음 — 구현이 이 규칙을 강제하지 않는다"
```

`error_message` 판정은 에러 영역에서 먼저 찾고, 없으면 화면 전체에서 찾습니다(모든 구현이
`role="alert"`를 쓰지는 않으니까). 다만 **어디서 찾았는지를 근거에 남깁니다.**

```python
return True, "화면 텍스트에서 기대 문구를 확인 (에러 영역 밖)"
```

리포트를 보는 사람이 판정 근거의 강도를 알 수 있게 하는 것입니다.

---

## 정상 케이스는 두 조건을 다 본다

```python
def _judge_toast_or_redirect(expected, state):
    checks = []
    if expected.url_contains:
        checks.append((expected.url_contains in state.url, ...))    # 경로 이동
    if expected.value:
        checks.append((contains_loose(state.text, expected.value), ...))  # 문구 노출
    passed = all(ok for ok, _ in checks)     # 둘 다 만족해야 PASS
```

기획서가 "`/dashboard`로 이동하고 '환영합니다'를 노출한다"고 했으면 **둘 다** 확인합니다.

하나만 보고 넘기면 "URL은 바뀌었는데 화면이 텅 빈" 상태를 정상으로 판정하게 됩니다.

---

## 스텝이 끊기면 기대 대조를 하지 않는다

```python
failed_step = next((r for r in step_results if r.status == "error"), None)
if failed_step is not None:
    return Verdict(verdict="FAIL", failure_category=failed_step.error_code, ...)
```

입력 도중 요소를 못 찾아서 멈췄다면, 화면이 기대 상태에 **도달할 기회가 없었습니다.**
그때 "기대 문구가 없으니 FAIL"이라고 판정하면 원인을 잘못 짚습니다.

그래서 그 스텝의 실패 원인(`element_not_found` 등)을 그대로 케이스의 실패 원인으로 씁니다.

---

## 실패 원인 분류

서비스명세서 §6의 6가지 카테고리입니다.

| 카테고리 | 언제 |
|---|---|
| `element_not_found` | 요소를 못 찾음 |
| `input_error` | 요소는 찾았으나 조작 불가 (가려짐, 비활성) |
| `assertion_mismatch` | 실행은 됐으나 기대와 다름 |
| `timeout` | 대기 시간 초과 |
| `page_error` | HTTP 4xx/5xx, JS 콘솔 예외 |
| `unknown` | 위에 해당 없음 |

1차에서는 **AI를 쓰지 않고 규칙으로만** 분류합니다.

```python
def _classify(case, state) -> str:
    if state.console_errors:
        return "page_error"
    return "assertion_mismatch"
```

단순해 보이지만 이유가 있습니다. 실행이 끝까지 진행된 뒤의 불일치는 거의 다
`assertion_mismatch`이고, 그 판단에 추론이 필요하지 않습니다. AI 보조 분류는 2차에서
`unknown`으로 남는 사례를 모아본 뒤 도입합니다. **데이터 없이 미리 만들지 않는 것**입니다.

---

## 개발자가 바로 조치할 수 있는 설명

```python
def _failure_detail(case, reason: str) -> str:
    if case.type == "negative" and case.violates:
        return (
            f"기획서의 '{case.violates}' 검증 규칙이 구현에서 확인되지 않았습니다. "
            f"({reason})"
        )
    return reason
```

`violates`(어긴 규칙 이름)를 **앞세웁니다.** 그게 개발자가 추가해야 하는 코드를 직접
가리키기 때문입니다.

```
FAIL [require_uppercase] 비밀번호 대문자 검증
     기획서의 'require_uppercase' 검증 규칙이 구현에서 확인되지 않았습니다.
     (다른 문구가 노출됨: '로그인 정보를 확인해주세요.')
```

이 한 줄로 개발자는 "비밀번호 검증에 대문자 검사를 추가해야 한다"를 압니다.

---

## PASS에도 근거를 남긴다

```python
evidence = {
    "expected": ...,      # 무엇을 기대했나
    "actual": reason,     # 실제로 무엇을 봤나
    "url": state.url,     # 최종 URL
    "screenshot": ...,    # 마지막 스크린샷
    "error_texts": ...,   # 화면의 에러 문구들
}
```

FAIL만이 아니라 **PASS에도** 남깁니다. 왜냐하면 "왜 PASS인가"를 확인할 수 없으면 그 PASS를
신뢰할 근거가 없기 때문입니다.

`tests/test_assertion_engine.py`에 이 성질을 고정한 테스트가 있습니다.

```python
def test_PASS에도_근거를_남긴다(self):
    """왜 PASS 인지 확인할 수 없으면 그 PASS 를 신뢰할 근거가 없다."""
```

---

## S6: 리포트

### 읽는 사람이 알고 싶은 순서로 배치

리포트를 읽는 사람은 대개 기획서를 쓴 사람이 아니라 **코드를 고쳐야 하는 개발자**입니다.
그가 알고 싶은 것은 순서대로 이렇습니다.

| 순서 | 궁금한 것 | 리포트의 무엇 |
|---|---|---|
| 1 | 뭐가 깨졌나 | 요약 카드 (통과율, 실패 건수) |
| 2 | 어느 규칙이 문제인가 | 실패 목록의 위반 규칙 태그 |
| 3 | 정말 그런가 | 기대 vs 실제, 스크린샷 |
| 4 | 무엇을 고쳐야 하나 | `failure_detail` |

그래서 실패를 위에 모으고 기본 펼침으로, 통과는 아래에 접어둡니다. 통과를 지우지 않는
이유는 "무엇이 검증됐는지"도 기획-구현 일치의 증거이기 때문입니다.

### 외부 의존이 없는 단일 HTML

CSS를 문서 안에 인라인하고 CDN을 쓰지 않습니다.

```python
_CSS = """
:root { --bg:#f6f7f9; ... }
"""
```

리포트는 실행 산출물이라 브라우저에서 **파일로** 열립니다(`file://`). CDN을 불러오면 오프라인
이나 폐쇄망에서 깨집니다. B2B QA 도구는 폐쇄망 실행을 가정해야 합니다.

### mock 백엔드 경고

```python
if backend.startswith("mock"):
    mock_warn = (
        "<div class='warn'><b>mock 백엔드로 실행된 리포트입니다</b>"
        "<div>설계 문서 추출에 실제 모델이 쓰이지 않았습니다. "
        "이 결과를 실제 검증 결과로 사용하지 마세요.</div></div>"
    )
```

mock으로 돌린 결과를 실제 검증 결과로 착각하면 **아무 추론도 하지 않은 리포트가 정상처럼
보입니다.** QA 도구에서 가장 위험한 사고라 리포트 상단에 노란 경고를 띄웁니다.

같은 이유로 CLI는 vLLM 연결 실패 시 mock으로 **자동 전환하지 않습니다.**

---

## 확인해보기

```powershell
# 판정 테스트 (브라우저 없이 빠르다)
uv run pytest tests/test_assertion_engine.py -v

# 리포트 열어보기
start runs\real-bad\report.html
```

리포트에서 확인할 것:
- 실패 케이스에 `[format]` 같은 파란 태그 → 어긴 규칙
- 빨간 상자 → 개발자가 읽을 설명
- "기대 / 실제 / 최종 URL / 실패 분류 / 화면 에러" 표
- 스텝 표의 "탐지" 열 → `label`, `role` 중 어느 전략으로 요소를 찾았는지
- 스크린샷 4장 → 클릭하면 원본

---

다음: [06-langgraph.md](06-langgraph.md) — LangGraph를 나중에 붙인 이유
