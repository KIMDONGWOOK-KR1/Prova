# 03. AI에 맡길 일과 코드로 짤 일 — 이 프로젝트의 핵심 판단

> 대상 파일: `src/prova/s2_case_generator/rule_expander.py`, `generator.py`

---

## 질문

우리는 AI를 쓰는 프로젝트를 하고 있습니다. 그런데 6단계 중 AI를 쓰는 곳은 **S1 하나뿐**입니다.
왜 그럴까요?

이 노트가 그 판단 기준을 다룹니다. **이 프로젝트에서 가장 중요한 설계 결정**이고, 팀원들에게
가르칠 때도 핵심이 될 내용입니다.

---

## S2가 하는 일

`ScreenSpec`(기획서 명세)을 받아 `TestCase[]`(검사 시나리오 목록)을 만듭니다.

```
기획서: "비밀번호는 8자 이상, 대문자 1자 이상, 특수문자 1자 이상"
                          ↓
케이스 1: Aa1!aaa    (7자 — 길이만 어김)
케이스 2: a1!aaaaa   (대문자만 없음)
케이스 3: Aa1aaaaa   (특수문자만 없음)
```

여기서 질문: **"대문자 1자 이상"이라는 규칙에서 "대문자가 없는 값"을 만드는 데 AI가
필요한가?**

필요 없습니다. 그냥 코드로 만들면 됩니다.

```python
# rule_expander.py 의 _violation_value()
if rule == "require_uppercase":
    counts["require_uppercase"] = 0        # 대문자를 0개로
    # 나머지 요건(소문자, 숫자, 특수문자, 길이)은 그대로 채운다
```

---

## 코드로 짜면 얻는 것 세 가지

### 1. 항상 같은 결과가 나온다 (결정적)

AI는 같은 질문에도 다르게 답할 수 있습니다. `temperature=0`으로 두면 많이 줄지만 완전히
같지는 않고, 모델을 바꾸면 확실히 달라집니다.

코드는 언제나 같은 값을 만듭니다. 그래서 **어제 결과와 오늘 결과를 비교**할 수 있습니다.
"어제는 PASS였는데 오늘 FAIL이다 → 구현이 바뀌었다"고 결론 내릴 수 있습니다. AI가 케이스를
만들면 "케이스가 바뀐 건가, 구현이 바뀐 건가"를 알 수 없습니다.

### 2. 비용이 0이다

우리는 대학 동아리 팀이고 API 비용을 아껴야 합니다. GPU도 A100의 7분의 1(MIG 1g)만 씁니다.
코드로 되는 일에 GPU 시간을 쓸 이유가 없습니다.

### 3. 검사할 수 있다 ← 가장 중요

만든 값이 **정말 그 규칙만 어기는지** 테스트로 확인할 수 있습니다.

```python
# tests/test_rule_expander.py
def test_각_위반값은_대상_규칙만_깨뜨린다(self):
    c = {"min_length": 8, "require_uppercase": 1, "require_special": 1,
         "require_digit": 1, "require_lowercase": 1}
    for v in violations_for_element(elem(constraints=c)):
        # 대상 규칙은 어겨야 한다
        assert not satisfies(v.value, {v.rule: c[v.rule]})
        # 나머지 규칙은 지켜야 한다
        others = {k: val for k, val in c.items() if k != v.rule}
        assert satisfies(v.value, others)
```

**AI 출력에는 이런 보증을 걸 수 없습니다.** "AI가 만든 값이 정말 대문자만 없는가"를
확인하려면... 결국 코드로 검사해야 합니다. 그러면 애초에 코드로 만드는 게 낫습니다.

---

### 순수 함수가 부족해진 순간 — 그래도 AI를 부르지 않았다

회원가입 화면의 '비밀번호 확인'은 자기 규칙이 없습니다. **다른 입력란과 같아야 한다**는
것이 규칙입니다(`constraints: {"same_as": "password"}`).

그러면 값을 요소 하나만 보고 정할 수 없습니다. `valid_value_for(element)` 로는 답이
안 나옵니다. AI를 부를 유혹이 생기는 지점입니다 — "알아서 적당한 값을 채워줘".

부르지 않았습니다. 필요한 건 추론이 아니라 **순서**였기 때문입니다.

```python
# rule_expander.py
values, warnings = resolve_values(inputs)
# password 를 먼저 풀고, password_confirm 은 그 결과를 받아 정한다
```

의존 관계를 따라 순서대로 푸는 건 정해진 절차입니다. 그리고 여전히 테스트로 보증할 수
있습니다 — "확인값이 참조값과 같은가"는 코드로 검사됩니다.

### 더 미묘한 문제: 계약이 깨질 뻔했다

'한 케이스는 한 규칙만 위반한다'가 이 모듈의 계약입니다. 그런데 비밀번호에 위반값을
넣으면 확인값도 함께 어긋나서 **두 규칙이 동시에 깨집니다.**

```
비밀번호      = 'a1!aaaaa'   ← 대문자 규칙 위반 (의도)
비밀번호 확인  = 'Signup1!'   ← 일치 규칙도 위반됨 (의도 아님!)
```

FAIL이 떴을 때 "대문자 검증이 없나, 일치 검증이 없나"를 알 수 없게 됩니다. 명세서 예시가
가진 문제와 똑같은 것이 다른 경로로 되돌아온 것입니다.

→ 위반값을 **먼저 고정하고** 그것에 의존하는 값을 다시 계산합니다.

```python
values, _ = resolve_values(inputs, overrides={"password": "a1!aaaaa"})
# 비밀번호      = 'a1!aaaaa'
# 비밀번호 확인  = 'a1!aaaaa'   ← 다시 계산되어 일치한다
```

이제 깨지는 규칙은 비밀번호의 것 하나뿐입니다.

**피할 수 없는 예외가 하나 있습니다.** 비밀번호를 비우면(required 위반) 확인값도 비게
되어 두 요소의 required가 함께 깨집니다. 빈 값과 같아야 하는 값은 빈 값뿐이라 방법이
없습니다. 다행히 두 경우의 기대 문구가 같은 "필수 입력" 문구라서 판정은 흔들리지 않습니다.
이런 예외는 **숨기지 말고 코드에 적어두는 것**이 맞습니다 — `rule_expander.py` 맨 위
docstring에 적혀 있습니다.

---

## 판단 기준

정리하면 이렇습니다.

| 코드로 짠다 | AI에게 맡긴다 |
|---|---|
| 규칙이 정해져 있다 | 정답이 여러 개다 |
| 입력과 출력의 대응이 명확하다 | 문맥을 이해해야 한다 |
| 결과를 검사할 수 있다 | 사람이 봐야 품질을 안다 |
| 자주 실행된다 (비용 누적) | 한 번만 실행된다 |
| **필요한 게 순서·절차다** | **필요한 게 판단이다** |

마지막 줄이 `same_as`에서 배운 것입니다. "요소 하나만 봐선 안 된다"는 것이 곧 "AI가
필요하다"는 뜻은 아닙니다.

이 기준으로 우리 파이프라인을 보면:

| 작업 | 판단 | 이유 |
|---|---|---|
| 사람 말 "8자 이상" → `{"min_length": 8}` | **AI** | 표현이 무한히 다양하다. "최소 8글자", "8자부터" 등 |
| `{"min_length": 8}` → 7자 문자열 | **코드** | 완전히 결정적 |
| 케이스 제목 다듬기 | AI (선택) | 사람이 읽을 문장. 틀려도 판정에 영향 없음 |
| 화면에서 요소 찾기 | 1차 코드, 2차 AI | selector로 찾히면 코드로. 못 찾으면 VLM |
| 에러 문구 비교 | **코드** | 문자열 비교. AI를 쓰면 오히려 부정확 |

서비스명세서 §10-2도 같은 판단을 했습니다 — "S2 표준 케이스(규칙→위반)는 🟢 로컬 유력,
규칙→위반 매핑은 거의 결정적 패턴". 우리는 한 발 더 나가서 **AI를 아예 쓰지 않았습니다.**

---

## 핵심 계약: 한 케이스는 한 규칙만 어긴다

서비스명세서의 예시 케이스를 보세요 (§2-S2).

```json
{
  "case_id": "signup-pw-no-upper-002",
  "violates": "require_uppercase, require_special",
  "steps": [... {"action": "fill", "target": "비밀번호", "value": "abcd1234"} ...]
}
```

`abcd1234`는 **대문자도 없고 특수문자도 없습니다.** 두 규칙을 동시에 어깁니다.

이 케이스가 FAIL이면 개발자는 무엇을 알 수 있나요?

> "대문자 검증이 없나? 특수문자 검증이 없나? 둘 다인가?"

**알 수 없습니다.** 그래서 우리는 규칙 하나당 케이스 하나로 바꿨습니다.

```python
require_uppercase 위반 → "a1!aaaaa"   (대문자만 없음. 소문자·숫자·특수문자·길이는 충족)
require_special   위반 → "Aa1aaaaa"   (특수문자만 없음)
min_length        위반 → "Aa1!aaa"    (길이만 부족. 문자 종류는 다 충족)
```

이제 리포트에서 규칙과 실패가 **1:1로 연결**됩니다.

```
FAIL [require_uppercase] → 대문자 검증 코드를 추가하라
FAIL [require_special]   → 특수문자 검증 코드를 추가하라
```

개발자가 무엇을 고쳐야 하는지 바로 압니다.

---

## 만들 수 없는 위반은 건너뛴다

규칙끼리 충돌하면 "그 규칙만 어기는 값"이 존재하지 않을 수 있습니다.

예: `{"min_length": 3, "require_uppercase": 1, "require_lowercase": 1, "require_digit": 1,
"require_special": 1}` — 문자 종류 4개를 다 넣으면 최소 4자가 되므로 "3자 미만이면서 종류
요건을 다 지키는 값"은 없습니다.

```python
# rule_expander.py 의 _violation_value()
if len(base) > target:
    # 종류 요건을 지키면 이미 목표 길이를 넘는다 -> 이 규칙만 위반하는
    # 값이 존재하지 않는다. 억지로 만들면 다른 규칙까지 깨진다.
    return None
```

`None`을 반환하면 그 케이스를 만들지 않습니다. **억지로 만들면 여러 규칙을 동시에 어겨서
FAIL 원인이 흐려집니다.** 케이스가 하나 없는 것보다 원인을 알 수 없는 FAIL이 나쁩니다.

---

## AI에게 남긴 일: 케이스 제목

`generator.py`의 `_polish_titles()`가 유일하게 AI를 씁니다.

```
코드가 만든 제목: "비밀번호 대문자 포함 규칙 위반 (입력값 'a1!aaaaa') — 규칙 강제 여부 확인"
AI가 다듬은 제목: "비밀번호 대문자 검증"
```

**제목은 판정 근거가 아닙니다.** 사람이 리포트를 읽는 편의를 위한 것입니다. 그래서
AI 호출이 실패해도 파이프라인을 세우지 않습니다.

```python
try:
    raw = llm.complete_json(...)
except LLMError as exc:
    spec.warnings.append(f"케이스 제목 다듬기를 건너뛰었습니다: {exc}")
    return          # 규칙 기반 제목을 그대로 쓴다
```

**AI가 실패해도 검증 결과가 오염되지 않는 구조**입니다. 이게 AI를 쓰는 위치를 고를 때의
또 하나의 기준입니다 — "이게 틀려도 결과가 망가지지 않는 곳"에 먼저 쓰는 것.

---

## 기대 문구의 출처가 규칙마다 다르다

`generator.py`에서 조심해야 하는 부분입니다. 케이스의 "기대 결과"를 어디서 가져오나?

| 위반 규칙 | 기대 문구의 출처 |
|---|---|
| 형식·길이·문자종류 | `UIElement.error_message` (기획서 §2 표의 에러 메시지 열) |
| `required` (빈 값) | `ScreenSpec.required_message` (기획서 §4의 화면 공통 문구) |
| **문구를 모를 때** | **`error_shown`으로 격하** |

세 번째가 중요합니다.

```python
# generator.py 의 _expectation_for_violation()
if message:
    return Expectation(type="error_message", value=message)
# 문구를 모를 때는 격하한다. 억측한 문구로 오탐을 만드는 것보다,
# '에러가 떴고 이동하지 않았다' 만 확인하는 편이 낫다.
return Expectation(type="error_shown", value="")
```

**왜?** 기획서에 문구가 없는데 그럴듯한 문구를 지어 넣으면, 실제 화면에 올바른 에러가
떠 있어도 문구가 달라 FAIL이 됩니다. 그게 **오탐**입니다.

### 오탐이 미탐보다 위험한 이유

- **미탐** (버그를 놓침): 아쉽지만 사람이 나중에 발견한다
- **오탐** (없는 버그를 보고): 개발자가 확인해보고 "아니네"를 반복하면 **도구를 신뢰하지
  않게 된다.** 그러면 진짜 버그 보고도 무시당한다

QA 도구는 신뢰를 잃으면 아무 가치가 없습니다. 그래서 확신이 없으면 약하게 판정합니다.

---

## 확인해보기

```powershell
# 실제로 어떤 위반값이 만들어지는지
uv run python -c "
import json
from prova.models import ScreenSpec
from prova.s2_case_generator.rule_expander import violations_for_element, satisfies

spec = ScreenSpec.model_validate(json.load(open('fixtures/specs/login_spec.golden.json', encoding='utf-8')))
for e in spec.elements:
    for v in violations_for_element(e):
        others = {k: val for k, val in e.constraints.items() if k != v.rule}
        print(f'{e.label:6} / {v.rule_label:10} = {v.value!r:14} 다른규칙충족={satisfies(v.value, others) if others else True}')
"

# 테스트 (규칙 하나만 어기는지 검사하는 부분이 핵심)
uv run pytest tests/test_rule_expander.py -v
```

---

다음: [04-grounding-execution.md](04-grounding-execution.md) — 라벨로 실제 요소를 찾고 조작하기
