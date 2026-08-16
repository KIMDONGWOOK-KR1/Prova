# 08. 화면을 늘릴 때 실제로 깨진 것들 — 회원가입 확장

> 대상 파일: `src/prova/s2_case_generator/`, `src/prova/models.py`, `sut/app.py`,
> `fixtures/specs/signup_spec.*`

---

## 이 노트가 왜 있나

1차 목표(로그인 검증)가 초록불이 된 뒤, 자연스러운 다음 단계는 "화면 하나 더"였습니다.
계획을 세울 때는 **단순 반복**으로 보였습니다. 기획서 하나 더 쓰고, SUT에 화면 하나 더
붙이고, 돌리면 되는 일.

아니었습니다. 코드를 열어보기 전에 검토했더니 **네 군데가 막혔고**, 실제로 붙이는
과정에서 **문서로 예측하지 못한 것이 세 개 더** 나왔습니다.

이 노트는 "왜 화면 하나 늘리는 게 설계 변경이었는가"를 다룹니다. 검색 화면을 붙일 때
같은 종류의 검토를 먼저 하기 위한 기록입니다.

---

## 결과부터

| 화면 | 대상 | 결과 |
|---|---|---|
| 회원가입 | `good` | **14/14 PASS** |
| 회원가입 | `bad` | **11 PASS / 3 FAIL** (오탐 0건) |

그리고 **로그인 결과가 그대로 유지**됐습니다 (7/7, 3 PASS·4 FAIL). 이게 확장의 실질적인
완료 조건입니다. 위반값 생성 로직의 계약을 건드렸는데 그 변경이 로그인 검증을 조용히
망가뜨렸다면, 확장이 아니라 후퇴입니다.

---

## 왜 단순 반복이 아니었나

로그인 화면은 운이 좋았습니다.

- 입력란이 2개고 **둘 다 텍스트 입력**이었다
- 규칙이 모두 **값 하나만 보면 판정되는** 것이었다 (길이, 문자 종류, 이메일 형식)

회원가입은 이 두 전제가 다 깨집니다.

| 회원가입 요소 | 새로 필요한 것 |
|---|---|
| 이메일 | (없음 — 로그인과 같다) |
| 비밀번호 | (없음) |
| 비밀번호 확인 | **교차 필드 규칙** — 다른 요소와 같아야 한다 |
| 닉네임 | (없음… 이라고 생각했는데 아니었다, 아래 함정 2) |
| 가입 경로 | **선택 목록** — 고를 값을 담을 곳이 없었다 |
| 약관 동의 | **체크박스** — `fill()`이 통하지 않는다 |
| 가입하기 | (없음) |

---

## 1. 체크박스 — 액션을 나눴다

가장 먼저, 가장 확실하게 터지는 곳입니다. 자세한 내용은
[04-grounding-execution.md](04-grounding-execution.md)의 "체크박스에 `fill()`을 부르면
안 된다"에 있습니다. 요약하면:

- `fill()` → `Element is not an <input> that can be filled`
- 그 실패가 "조작 오류"로 기록되어 **판정이 뭉개진다**
- → `check` / `uncheck` 액션을 추가하고, **빈 값 = 체크 해제**로 규칙을 통일

---

## 2. 선택 목록 — `constraints`가 아니라 새 필드

`<select>`의 선택지를 어디에 담을지가 문제였습니다. `constraints`에 넣고 싶은 유혹이
있습니다. 넣으면 안 됩니다.

```python
# 이렇게 하면 안 된다
constraints = {"options": ["검색", "지인 추천", "광고"]}
```

`constraints`는 **위반값을 만들 수 있는 규칙**을 담는 곳입니다. `rule_expander`가 그
안의 키를 하나씩 돌면서 "이 규칙만 어기는 값"을 만듭니다. 선택지 목록은 규칙이 아니라
**값의 후보 집합**이라 위반값을 만들 수 없습니다. 섞어두면 `rule_expander`가 이것도
전개하려 들고, 뭘 만들어야 할지 몰라 이상한 값이 나옵니다.

```python
# models.py
class UIElement(BaseModel):
    constraints: dict = Field(default_factory=dict)   # 규칙
    options: list[str] = Field(default_factory=list)  # 값의 후보
```

**배운 것**: 자료구조를 재사용할지 새로 만들지는 "모양이 비슷한가"가 아니라 **"같은
코드가 같은 방식으로 다루는가"**로 판단합니다.

### 선택·체크 요소에는 문자 규칙을 전개하지 않는다

```python
# rule_expander.py
NON_TEXT_TYPES = ("checkbox", "select")
```

체크박스에 `min_length: 8`이 붙어 있다면(기획서가 실수했든, S1이 잘못 뽑았든)
'8자 미달인 체크 상태'라는 입력은 만들 수 없습니다. 억지로 만들면 실행이 실패해 판정이
뭉개집니다. 이 요소들에서 검증할 수 있는 것은 **'선택/체크하지 않았을 때'** 뿐입니다.

---

## 3. 교차 필드 규칙 — 가장 어려웠던 곳

'비밀번호 확인'은 자기 규칙이 없습니다. **다른 입력란과 같아야 한다**는 것이 규칙입니다.

이 규칙 하나가 값 생성 방식을 바꿨습니다. 자세한 내용은
[03-llm-vs-code.md](03-llm-vs-code.md)의 "순수 함수가 부족해진 순간"에 있습니다. 요약:

1. **요소 단위 함수로는 값을 정할 수 없다** → 화면 단위 해석(`resolve_values`)이 필요
2. **의존 순서대로 풀어야 한다** → 비밀번호를 먼저, 확인값은 그 결과를 받아서
3. **'한 케이스는 한 규칙만 위반' 계약이 깨질 뻔했다** → 위반값을 고정하고 의존값을 다시 계산

```python
values, _ = resolve_values(inputs, overrides={"password": "a1!aaaaa"})
# 비밀번호      = 'a1!aaaaa'   ← 대문자 규칙 위반 (의도)
# 비밀번호 확인  = 'a1!aaaaa'   ← 다시 계산되어 일치한다 (일치 규칙은 안 깨짐)
```

### 기획서 결함도 함께 잡히게 됐다

요소 간 참조를 다루게 되니 **기획서가 앞뒤 안 맞는 경우**를 알려줄 수 있게 됐습니다.

```python
# spec_defects() 가 잡는 것
- same_as 가 없는 요소를 가리킴
- same_as 가 서로를 가리켜 순환
- 선택 요소인데 선택 목록이 비어 있음
- 예시값이 자기 기획서의 검증 규칙을 위반함
```

이건 **구현 결함이 아니라 기획 결함**입니다. 그래서 케이스 FAIL이 아니라 경고로 알립니다.
섞어놓으면 개발자가 자기 코드를 고치려 하는데 정작 고칠 곳은 기획서입니다.

---

## 4. 기획서 PDF를 화면마다 하나씩

`ScreenSpec`은 화면 하나를 담는 타입입니다. 한 PDF에 여러 화면을 넣으려면 S1이 화면
경계를 판단해야 하고, 그건 지금 필요 없는 복잡함입니다.

→ `login_spec.pdf`, `signup_spec.pdf`로 나눴습니다. mock 백엔드도 PDF 이름에서 정답
파일을 찾게 바꿨습니다.

```python
MockLLM.for_spec("fixtures/specs/signup_spec.pdf")
# -> signup_spec.golden.json 을 ScreenSpec 응답으로 등록
```

화면이 늘어날 때마다 `if` 문이 늘어나지 않게 하는 것이 목적입니다. 다중 화면 추출은
WITCHES 실물 기획서를 받고 나서 판단합니다 — 실물이 화면당 한 파일일 수도 있습니다.

---

## 문서로 예측하지 못했던 것들

여기까지는 코드를 열기 전에 검토해서 알아낸 것입니다. 아래는 **실제로 돌려보고** 알게 된
것들입니다.

### 함정 1: 필수 입력 문구의 출처가 요소마다 다르다

로그인 화면에서 배운 규칙은 이랬습니다.

> `required` 위반의 기대 문구는 **화면 공통 문구**(§4)를 쓴다.
> 요소의 `error_message`는 형식 검증용이라 쓰면 어긋난다.

회원가입에 이 규칙을 그대로 적용하면 **오탐이 납니다.**

```
약관 동의의 error_message = "약관에 동의해야 합니다."
화면 공통 문구            = "필수 입력 항목입니다."
```

체크박스에 형식 검증이 있을 수 없습니다. 그러니 "약관에 동의해야 합니다."는 **미동의
상태의 문구**입니다. 화면 공통 문구를 기대하면, 구현이 옳게 동작해도 문구가 달라 FAIL이
됩니다.

처음엔 "체크박스와 선택 요소는 예외"로 짤 생각을 했습니다. 더 나은 규칙이 있었습니다.

```python
# generator.py
def _required_message_for(element, spec):
    # 그 요소에 다른 검증 규칙이 없으면 error_message 는 필수 여부에 대한
    # 문구일 수밖에 없다
    if element.error_message and not element.constraints:
        return element.error_message
    return spec.required_message or element.error_message
```

체크박스·선택뿐 아니라 **"필수인데 다른 규칙은 없는 텍스트 입력"**("이름을 입력하세요.")
까지 자연스럽게 처리됩니다.

**배운 것**: 예외를 나열하기 전에 **왜 예외인지**를 생각하면 더 좁고 정확한 규칙이
나옵니다. "체크박스라서"가 아니라 "다른 규칙이 없어서"가 진짜 이유였습니다.

### 함정 2: 닉네임의 "2자 이상" 위반값이 만들어지지 않았다

닉네임 규칙은 `min_length: 2, max_length: 10`입니다. 그런데 `min_length` 위반 케이스가
**아예 생성되지 않았습니다.**

원인은 값을 만드는 코드에 있던 **정책 한 줄**이었습니다.

```python
n_lower = max(int(others.get("require_lowercase", 0)), 1)   # 최소 1자
n_digit = max(int(others.get("require_digit", 0)), 1)        # 최소 1자
```

이건 규칙이 아니라 **값을 사람이 읽기 좋게 만들려는 정책**입니다. 규칙이 없어도
`"aaaaaaaa"`보다 `"Aa1!aaaa"`가 낫다는 판단이었습니다. 비밀번호에는 잘 맞았습니다.

닉네임에서는 이게 발목을 잡았습니다. 소문자 1 + 숫자 1 = 최소 2자인데, 필요한 위반값은
**1자**입니다. 만들 수 없어서 조용히 건너뛰었습니다.

**조용히 건너뛰는 것 자체는 의도된 동작입니다** — 규칙끼리 충돌해 대상 규칙만 깨는 값이
없을 때 억지로 만들면 다른 규칙까지 깨져 원인이 흐려지니까요. 문제는 여기선 **충돌이
없었다**는 것입니다. 닉네임에는 문자 종류 규칙이 아예 없었습니다.

```python
if len(base) > target:
    # 읽기 좋게 만들려고 넣은 소문자·숫자 때문에 목표 길이를 넘었을 수 있다.
    # 실제 규칙만으로 다시 만들어 본다.
    base = _compose(length=0, n_upper=n_upper, n_lower=n_lower_req,
                    n_digit=n_digit_req, n_special=n_special)
    if len(base) > target:
        return None
```

정책용 하한(`n_lower`)과 규칙상 필요한 개수(`n_lower_req`)를 갈라놓고, 정책 때문에 막힌
경우에만 정책을 내려놓습니다. 비밀번호의 위반값은 한 글자도 변하지 않았습니다 —
`min_length` 위반값은 여전히 `'Aa1!aaa'`입니다. 그걸 테스트로 못 박았습니다.

**배운 것**: 편의를 위한 기본값이 **기능을 조용히 없앨 수 있습니다.** 그리고 "만들 수
없으면 건너뛴다"는 안전장치는 **정말 만들 수 없을 때만** 발동해야 합니다.

### 함정 3: 7B가 버튼 행을 빠뜨렸다

요소가 3개에서 7개로 늘자 S1이 흔들렸습니다. 자세한 내용은
[02-s1-spec-extraction.md](02-s1-spec-extraction.md)의 "함정 3"에 있습니다. 요약:

- 검증 규칙이 모두 `-`인 버튼 행을 모델이 스스로 생략했다 (길이 제한 때문이 아니었다)
- 제출 버튼이 없으면 폼이 제출되지 않아 **전 케이스가 FAIL** — 원인은 추출인데 리포트는
  "구현이 전부 틀렸다"고 말한다
- → **예방**(표에서 읽은 요소 ID를 프롬프트에 박기) + **검출**(대조해서 경고) 두 겹

같은 노트의 "함정 4"에 프롬프트를 고치다 **로그인의 다른 필드가 깨진** 이야기도 있습니다.

---

## `bad` 구현에 무엇을 심을지도 설계다

`bad`에 심는 결함은 아무거나 고르면 안 됩니다. **로그인에서 이미 확인한 종류를 한 번 더
심으면 화면을 늘린 만큼의 검증력을 얻지 못합니다.**

| 심은 결함 | 새로 확인되는 것 |
|---|---|
| 비밀번호 확인 일치 검증 없음 | 교차 필드 규칙 — 값 하나만 봐선 판정 못 하는 규칙 |
| 약관 동의 필수 검증 없음 | 체크 '상태'를 보는 규칙 |
| 닉네임 최대 길이 검증 없음 (최소만 구현) | 한 요소의 규칙 중 **일부만** 빠진 경우 |

세 번째가 "규칙 하나당 케이스 하나" 설계의 값을 증명합니다. 최소·최대를 한 케이스로
묶었다면 최소 쪽이 걸려 에러가 뜨고, **최대 검증이 없다는 사실이 가려집니다.**
실제 결과가 그걸 보여줍니다.

```
닉네임 min_length  → PASS  (2자 미달은 막는다)
닉네임 max_length  → FAIL  (10자 초과는 통과된다)
```

### 오탐 검증도 요소 단위로 강해졌다

로그인에서는 "어느 **규칙**이 FAIL인가"만 봐도 충분했습니다. 회원가입에서는 부족합니다 —
`required` 규칙을 가진 요소가 6개고, 그중 하나만 검증이 빠졌습니다.

```python
# tests/test_signup_e2e.py
EXPECTED_BAD_FAILURES = {
    ("password_confirm", "same_as"),
    ("agree_terms", "required"),
    ("nickname", "max_length"),
}
```

규칙 이름만으로 대조하면 "`required`가 FAIL"만 확인되고, **나머지 5개가 PASS인지는
확인되지 않습니다.** 그래서 `Verdict.target_element` 필드를 추가해 (요소, 규칙) 쌍으로
비교합니다. 리포트 화면에도 `agree_terms.required` 형태로 함께 보여줍니다.

**배운 것**: 화면이 커지면 **판정의 식별자도 함께 커져야** 합니다. 규칙 이름만으로는
어디를 고쳐야 할지 알려주지 못합니다.

---

## 확인해보기

```powershell
# 테스트 대상 웹앱
uv run uvicorn sut.app:app --port 8100

# 회원가입 검증 (GPU 없이 mock 으로)
uv run prova run --pdf fixtures/specs/signup_spec.pdf --url http://localhost:8100/good --backend mock
uv run prova run --pdf fixtures/specs/signup_spec.pdf --url http://localhost:8100/bad  --backend mock

# 어떤 케이스가 만들어지는지 (브라우저 없이)
uv run python -c "
import json
from prova.models import ScreenSpec
from prova.s2_case_generator.generator import generate_cases

spec = ScreenSpec.model_validate(json.load(open('fixtures/specs/signup_spec.golden.json', encoding='utf-8')))
for c in generate_cases(spec):
    print(f'{c.violates or \"(정상)\":16} {c.target_element or \"\":18} {c.expected.value!r}')
"

# 회원가입 관통 테스트
uv run pytest tests/test_signup_e2e.py -v

# 교차 필드·체크박스 계약
uv run pytest tests/test_rule_expander.py tests/test_generator.py -v
```

`--headed --slow 500 --only agree_terms` 를 붙이면 체크박스를 체크하지 않고 제출하는
장면을 눈으로 볼 수 있습니다.

---

## 검색 화면을 붙이기 전에 검토할 것

같은 실수를 반복하지 않으려면, 코드를 열기 전에 이걸 확인해야 합니다.

1. **검증 축이 다르다.** 지금까지는 "에러가 뜨는가"였는데 검색은 "결과 건수가 맞는가"입니다.
   `Expectation`에 `error_message` / `error_shown` 밖의 유형이 필요합니다.
2. **위반값이라는 개념이 흐려진다.** 검색어에 규칙이 있나요? "빈 검색어", "결과 없는
   검색어"는 규칙 위반이라기보다 **상태**입니다. `rule_expander`의 모델에 맞는지 먼저 봐야
   합니다.
3. **SUT에 데이터가 필요하다.** 지금 SUT는 상태가 없습니다(회원가입도 계정을 저장하지
   않습니다). 검색은 검색될 데이터가 있어야 하고, 그러면 테스트 간 상태 공유를 생각해야
   합니다 — `conftest.py`의 SUT 픽스처가 세션 범위인 근거가 흔들립니다.
4. **완료 조건은 같다.** 로그인·회원가입 결과가 그대로 유지되어야 합니다.

---

이전: [07-cheetah-cuda.md](07-cheetah-cuda.md) — GPU 서버에서 실제로 막힌 세 지점
