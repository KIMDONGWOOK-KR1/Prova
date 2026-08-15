# 01. 데이터 계약 — `models.py`가 왜 중요한가

> 대상 파일: `src/prova/models.py` (227줄)

---

## 먼저 용어

**pydantic**이란 파이썬에서 "데이터의 모양"을 미리 정해두는 도구입니다. 이렇게 씁니다.

```python
from pydantic import BaseModel

class UIElement(BaseModel):
    element_id: str          # 문자열이어야 한다
    required: bool = False   # 참/거짓, 안 쓰면 False
    constraints: dict        # 딕셔너리여야 한다
```

이렇게 정의하면 세 가지 일이 자동으로 됩니다.

```python
# 1) 타입이 틀리면 즉시 에러
UIElement(element_id=123, ...)     # 에러! 숫자를 넣었다

# 2) 필수 항목이 빠지면 즉시 에러
UIElement(required=True)            # 에러! element_id가 없다

# 3) JSON Schema를 뽑아낼 수 있다
UIElement.model_json_schema()        # {"properties": {"element_id": {"type": "string"}}, ...}
```

3번이 이 프로젝트에서 특히 중요합니다. 나중에 설명합니다.

---

## `models.py`가 하는 일

파이프라인의 6단계는 각자 다른 일을 하지만, **서로 데이터를 주고받습니다.**

```
ScreenSpec → TestCase[] → ElementLocation → StepResult[] → Verdict → TestReport
   (S1)         (S2)           (S3)            (S4)         (S5)      (S6)
```

이 화살표에 적힌 타입들이 전부 `models.py`에 정의돼 있습니다. 그래서 이 파일을
**파이프라인의 계약(contract)** 이라고 부릅니다. "S1은 반드시 `ScreenSpec`을 내놓고,
S2는 반드시 `ScreenSpec`을 받는다"는 약속입니다.

### 주요 타입

| 타입 | 무엇을 담나 |
|---|---|
| `UIElement` | 화면의 요소 하나 (입력란, 버튼 등) + **검증 규칙** |
| `ScreenSpec` | 화면 하나의 명세. `UIElement` 목록 + 성공/실패 조건 |
| `TestStep` | 실행 단위 하나 ("이메일 칸에 xxx를 입력") |
| `TestCase` | 검사 시나리오 하나. `TestStep` 목록 + 기대 결과 |
| `ElementLocation` | 라벨을 실제 요소로 바꾼 결과 |
| `StepResult` | 한 동작의 실행 결과 + 스크린샷 경로 |
| `Verdict` | 케이스 하나의 PASS/FAIL + 근거 |
| `TestReport` | 전체 결과 |

---

## 가장 중요한 필드: `UIElement.constraints`

```python
class UIElement(BaseModel):
    element_id: str
    type: ElementType          # "input" | "button" | "checkbox" | ...
    label: str                 # "이메일", "비밀번호"
    required: bool = False
    constraints: dict = {}     # ← 이것
    error_message: str | None = None
```

`constraints`에 **기획서에 적힌 검증 규칙**이 들어갑니다.

```python
# 기획서: "8자 이상, 대문자 1자 이상, 특수문자 1자 이상"
constraints = {
    "min_length": 8,
    "require_uppercase": 1,
    "require_special": 1,
}
```

**이 필드가 프로젝트 전체에서 가장 중요합니다.** 이유는 이렇습니다.

S2(`rule_expander`)가 이 딕셔너리를 하나씩 훑어서 위반 케이스를 만듭니다. 즉:

```
constraints에 규칙 3개  →  위반 케이스 3개  →  브라우저에서 3번 확인
```

**여기서 규칙 하나를 놓치면 그 규칙은 아예 검사되지 않습니다.** 개발자가 그 검증을
빼먹었어도 리포트는 초록불이 됩니다. 이걸 **미탐(false negative)** 이라고 하는데, 경고도
없이 조용히 일어나기 때문에 가장 위험합니다.

그래서 `tests/test_s1_golden.py`에서 `constraints`만 **엄격 비교**합니다.

```python
assert got.constraints == want.constraints    # 키 이름·값이 정확히 같아야 한다
```

에러 문구는 공백 차이를 허용하는데(다음 노트에서 설명) `constraints`는 허용하지 않습니다.
키 이름이 `min_length`가 아니라 `min_len`으로 나오면 `rule_expander`가 그 규칙을 알아보지
못하기 때문입니다.

---

## 왜 pydantic인가 — 명세서는 TypedDict를 쓰라고 했다

서비스명세서 §3은 이렇게 규정했습니다.

```python
class UIElement(TypedDict):     # ← 명세서
    element_id: str
    ...
```

우리는 `BaseModel`(pydantic)로 바꿨습니다. 이유가 두 가지입니다.

### 이유 1: AI에게 형식을 강제하려면 JSON Schema가 필요하다

S1에서 AI에게 "이 형식으로 답해"라고 강제할 때, 그 형식을 **기계가 읽는 형태**로 넘겨야
합니다. pydantic은 이걸 자동으로 만들어 줍니다.

```python
# src/prova/s1_spec_extractor/extractor.py 의 extract_screen_spec()
raw = llm.complete_json(
    system=SYSTEM_PROMPT,
    user=...,
    schema=ScreenSpec.model_json_schema(),   # ← 여기
)
```

`TypedDict`는 `model_json_schema()` 같은 게 없습니다. 손으로 JSON Schema를 또 써야 하고,
그러면 **파이썬 타입과 JSON Schema가 갈라질 수 있습니다.** 한쪽만 고치고 다른 쪽을
잊어버리는 사고가 납니다.

### 이유 2: TypedDict는 실행할 때 검사하지 않는다

```python
# TypedDict — 타입 힌트일 뿐이다
spec: ScreenSpec = {"screen_id": 123}      # 실행됨! 에러 안 남
print(spec["screen_id"])                    # 123 (숫자인데 그냥 넘어감)

# pydantic — 즉시 잡는다
spec = ScreenSpec(screen_id=123, ...)       # ValidationError!
```

AI가 만든 데이터를 받는 상황에서는 이게 결정적입니다. AI는 언제든 예상 밖 형태를 낼 수
있고, 그걸 **받는 즉시** 알아야 합니다. 열 단계 뒤에서 이상한 에러로 터지면 원인을 찾는 데
훨씬 오래 걸립니다.

---

## 로그인만 하는데 타입을 다 정의한 이유

1차 목표는 로그인 화면 하나입니다. 그런데 `models.py`에는 명세서 §3의 **전체 타입**이
들어 있습니다. `select`, `checkbox` 같은 지금 안 쓰는 요소 타입도 있고, `ElementLocation`에는
2차 VLM용 `bbox`, `confidence` 필드가 미리 있습니다.

```python
class ElementLocation(BaseModel):
    target: str
    method: Literal["selector", "vlm"] = "selector"
    selector: str | None = None
    bbox: list[int] | None = None      # ← 2차 VLM용, 지금은 안 씀
    confidence: float = 1.0            # ← 2차 VLM용
    healed: bool = False               # ← 2차 Self-Healing용
```

**왜 미리 두나?** 나중에 필드를 추가하면 그 타입을 쓰는 모든 코드가 흔들립니다. 함수
시그니처가 바뀌고, 테스트가 깨지고, 저장된 JSON 파일이 호환되지 않습니다. 자리만 미리
잡아두면 2차에서 값을 채우기만 하면 됩니다.

같은 이유로 `nodes.py`의 `AgentState`에도 `heal_count`, `max_heal`이 미리 있습니다.

---

## 실제로 구현하면서 계약을 두 번 확장했다

문서만 보고는 몰랐고, 코드를 돌려보니 필요해진 필드가 두 개 있습니다.

### `ScreenSpec.required_message`

기획서를 다시 보세요.

- §2 표의 "에러 메시지" 열 → **형식 검증** 실패 문구 ("올바른 이메일 형식을 입력하세요.")
- §4 실패 조건 표 → "필수 입력값이 비어 있음 → **필수 입력 항목입니다.**"

**필수 입력 문구는 요소별이 아니라 화면 공통**입니다. 이메일이 비어도, 비밀번호가 비어도
같은 문구가 뜹니다. 그래서 `UIElement`가 아니라 `ScreenSpec`에 뒀습니다.

### `UIElement.sample_value`

`rule_expander`가 규칙을 만족하는 비밀번호를 만들면 `Aa1!aaaa`가 나옵니다. 규칙은 다
지킵니다. 그런데 **로그인이 안 됩니다.** 등록된 계정의 비밀번호(`Abcd123!`)가 아니니까요.

그래서 정상 케이스가 **구현에 아무 문제가 없는데도** FAIL이 났습니다. 이게 오탐입니다.

→ 기획서 §5의 테스트 계정을 `sample_value`에 담고, 정상 케이스는 그 값을 씁니다.

이 두 사례가 보여주는 것: **문서를 아무리 잘 써도 코드를 돌려봐야 아는 것이 있습니다.**
그래서 계획을 세울 때 "walking skeleton"(끝까지 얇게 연결)을 먼저 했습니다.

---

## 이걸 안 했으면 무슨 일이 벌어지나

계약을 한 곳에 모아두지 않고 각 단계가 자기 형식을 쓴다면:

- S1이 `{"screenName": ...}`을 내놓고 S2는 `{"screen_name": ...}`을 기대한다 → 통합할 때 터짐
- AI 출력을 검증하지 않으면 S5쯤에서 `KeyError`가 나고, 원인이 S1이라는 걸 찾는 데 시간이 걸림
- 리포트를 JSON으로 저장할 수 없다 (pydantic의 `model_dump()`가 그 일을 함)

계약을 먼저 고정한 덕에 6단계를 **각각 따로 만들어 나중에 붙일 수 있었습니다.**

---

## 확인해보기

```powershell
cd C:\dev\prova
uv run python -c "
from prova.models import ScreenSpec, UIElement

# 정상
e = UIElement(element_id='email', type='input', label='이메일',
              required=True, constraints={'format': 'email'})
print('OK:', e.label, e.constraints)

# 타입 위반 — 즉시 에러
try:
    UIElement(element_id='x', type='존재하지않는타입', label='y')
except Exception as ex:
    print('잡힘:', str(ex)[:80])

# JSON Schema 뽑기 (AI에게 넘기는 것)
print('필드:', list(ScreenSpec.model_json_schema()['properties']))
"
```

---

다음: [02-s1-spec-extraction.md](02-s1-spec-extraction.md) — PDF에서 기획서를 뽑는 방법과 함정
