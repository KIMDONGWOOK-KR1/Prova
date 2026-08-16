# 04. S3·S4 — 라벨로 실제 요소를 찾고 조작하기

> 대상 파일: `src/prova/s3_grounder/dom_locator.py`, `src/prova/s4_executor/playwright_driver.py`

---

## 문제 상황

S2가 만든 케이스에는 이렇게 적혀 있습니다.

```python
TestStep(seq=2, action="fill", target="이메일", value="user@test.com")
```

`target`이 **"이메일"**입니다. selector가 아니라 사람이 읽는 라벨입니다.

그런데 실제 웹페이지에서 그 입력란의 주소는 무엇일까요?

```html
<input id="email" name="email">              <!-- #email 일 수도 -->
<input id="userEmail" name="user_email">     <!-- #userEmail 일 수도 -->
<input class="form-control-1">                <!-- 클래스만 있을 수도 -->
```

**기획자는 이걸 모릅니다.** 기획서를 쓸 때 구현이 아직 없으니까요. 이 연결을 만드는 것이
S3(Grounding)의 일입니다.

**Grounding**이란 "추상적인 표현을 실제 대상에 연결하는 것"을 말합니다. 여기서는
"이메일"이라는 말을 화면의 실제 입력란에 연결합니다.

---

## 왜 라벨에서 출발하는가

selector를 케이스에 직접 적으면 안 되나요? 두 가지 이유로 안 됩니다.

**1. 기획서에는 selector가 없습니다.** 기획서에서 케이스를 자동 생성하는 것이 이 프로젝트의
목적인데, 기획서가 모르는 정보를 케이스에 넣을 수 없습니다.

**2. 같은 케이스를 두 방식으로 실행해 비교하려면** 라벨이어야 합니다. 서비스명세서 §9는
"selector 방식 vs VLM 방식의 탐지 성공률·속도를 비교 측정"하라고 규정합니다. 케이스가
라벨로 되어 있으면 같은 케이스를 selector로도, VLM으로도 실행할 수 있습니다.

---

## 탐지 우선순위

`dom_locator.py`의 `_try_strategies()`가 순서대로 시도합니다.

| 순서 | 방법 | 무엇을 보나 |
|---|---|---|
| 1 | `get_by_label` | `<label for="email">이메일</label>`로 연결된 입력란 |
| 2 | `get_by_placeholder` | 입력란의 흐린 안내 글자 |
| 3 | `get_by_role` | 버튼·링크의 **접근성 이름** |
| 4 | `get_by_text` | 그냥 글자 일치 |

**왜 이 순서인가?** 위쪽 방법이 **구현 세부사항과 가장 느슨하게 묶여** 있기 때문입니다.

개발자가 리팩터링으로 클래스명을 `.btn-primary`에서 `.button-main`으로 바꿔도, 버튼에 적힌
"로그인"이라는 글자는 그대로입니다. 접근성 속성(label, role)은 사용자에게 보이는 것이라
쉽게 바뀌지 않습니다.

반대로 `#email` 같은 id 기반 selector는 개발자가 언제든 바꿉니다. 그게 서비스명세서 §7의
워크스루 상황입니다 — "개발자가 `#submit`을 `#signup-submit`으로 바꿔 selector가 깨진 상태".

### 접근성(accessibility)이란

화면을 볼 수 없는 사용자가 스크린 리더로 웹을 쓸 수 있게 하는 표준입니다. `<label>`,
`role`, `aria-*` 속성이 그 역할을 합니다.

우리에게는 부수 효과가 있습니다 — **접근성을 잘 지킨 웹사이트는 자동 테스트도 쉽습니다.**
스크린 리더가 "이메일 입력란"이라고 읽어줄 수 있다면, Playwright도 그것으로 찾을 수 있습니다.

---

## "정확히 1개이고 보일 때만" 확정한다

```python
# dom_locator.py 의 _try_strategies()
if count == 1:
    visible = locator.is_visible()
    if visible:
        return locator, strategy, attempts     # 확정
else:
    attempts.append(Attempt(strategy=strategy, count=count))   # 실패로 기록
```

후보가 0개면 못 찾은 것이고, **여러 개면 어느 것을 조작해야 할지 모릅니다.**

여기서 유혹이 생깁니다 — "여러 개면 첫 번째를 쓰면 되지 않나?"

**안 됩니다.** 만약 화면에 "이메일"이라는 글자가 두 곳(입력란 라벨, 안내 문구)에 있는데
엉뚱한 것을 클릭하면, 그 케이스가 FAIL이 났을 때 이렇게 됩니다.

> "구현이 잘못된 건가? 우리가 엉뚱한 요소를 조작한 건가?"

구분할 수 없습니다. 그래서 **모호하면 실패로 처리하고 이유를 남깁니다.**

```python
@property
def reason(self) -> str:
    if any(a.count > 1 for a in self.attempts):
        return "후보가 여러 개여서 어느 것을 조작할지 확정할 수 없음"
    if any(a.count == 1 and not a.visible for a in self.attempts):
        return "요소를 찾았으나 화면에 보이지 않음"
    return "일치하는 요소가 없음"
```

이 `GroundingError`가 **2차 Self-Healing의 시작점**이 됩니다. selector로 못 찾으면 VLM에게
"스크린샷에서 '로그인' 버튼을 찾아줘"라고 물어보는 것입니다.

### 그런데 검색 결과 목록은 여러 개를 세야 한다

이 계약이 처음 시험대에 오른 것이 건수 검증입니다. 세려면 여러 개를 봐야 하는데, 계약을
느슨하게 만들면 이미 초록불인 세 화면의 판정 근거가 함께 약해집니다.

**계약을 고치지 않고 경로를 하나 더 뒀습니다** — `ground()` 옆의 `count_items()` 입니다.
그리고 새 경로에서도 계약은 유지됩니다. 한 겹 내려가 보면 층이 둘이기 때문입니다.

```
컨테이너   검색 결과 목록      <- 1개여야 한다 (어디를 셀 것인가)
  항목     Notebook Pro 15   <- 여러 개다   (몇 개인가)
```

'어디를 셀 것인가' 는 모호하지 않고, 모호한 것은 '몇 개인가' 뿐이며 그건 세면 답이
나옵니다. 자세한 것은 [10-counting-dom.md](10-counting-dom.md) 에 있습니다.

---

## `ElementLocation`과 `Locator`를 분리한 이유

Playwright의 `Locator`는 **브라우저 세션에 묶인 객체**입니다. JSON으로 저장할 수 없습니다.

그런데 리포트에는 "어떤 방법으로 요소를 찾았는지"가 들어가야 합니다. 그래서 두 개로 나눴습니다.

```python
# 기록용 (JSON 저장 가능)
ElementLocation(target="이메일", method="selector", strategy="label", confidence=1.0)

# 조작용 (브라우저에 묶임)
locator = resolve_locator(page, location, hint)     # 필요할 때 되살린다
locator.fill("user@test.com")
```

`resolve_locator()`가 기록을 다시 실제 `Locator`로 만들어 줍니다. 이렇게 나누지 않으면
리포트를 JSON으로 저장할 수 없습니다.

---

## S4: 실제로 조작하기

`playwright_driver.py`가 브라우저를 조작합니다.

### 매 단계마다 증거를 남긴다

```python
# _capture()
ctx.page.screenshot(path=str(shot))                  # 스크린샷
dom.write_text(ctx.page.content(), encoding="utf-8")  # HTML 전체
```

한 케이스에 4단계면 파일이 8개 생깁니다. 케이스 7개면 56개입니다. 왜 이렇게 많이 남기나요?

**QA 도구가 FAIL을 보고했을 때 개발자가 가장 먼저 하는 일은 "정말 그런가?"를 확인하는
것입니다.** 그때 볼 것이 없으면 도구를 신뢰하지 않게 되고, 진짜 버그 보고도 무시당합니다.

서비스명세서 §9의 "리포트 완결성 100%"가 이걸 요구합니다.

### 실패를 예외로 던지지 않는다

이게 중요한 설계입니다.

```python
except GroundingError as exc:
    status, error_code, error_detail = "error", "element_not_found", exc.reason
except PlaywrightTimeout as exc:
    status, error_code = "error", "timeout"
# ... 예외를 잡아서 StepResult에 담는다
return StepResult(seq=..., status=status, error_code=error_code, ...)
```

**왜 예외를 던지지 않나?** 예외로 파이프라인을 세우면 그 케이스 **이후의 케이스가 전부
실행되지 않습니다.** 그러면 한 번 돌려서 전체 상태를 알 수 없습니다.

QA 도구는 "지금 무엇이 깨져 있는가"를 한 번에 보여줘야 합니다. 첫 실패에서 멈추면 다시
돌리고 또 멈추고를 반복해야 합니다.

**실패는 데이터로 다룹니다.** 판정은 S5가, 원인 분류는 S6가 합니다.

### 실패한 스텝 뒤는 건너뛴다

```python
# execute_case_steps()
for step in steps:
    result = execute_step(ctx, step)
    results.append(result)
    if result.status == "error":
        break               # 이 케이스의 남은 스텝은 건너뛴다
```

케이스 **안에서는** 멈춥니다. 로그인 폼을 못 채운 상태로 제출 버튼을 누르면 그 결과가
무엇을 의미하는지 해석할 수 없기 때문입니다. 하지만 **다음 케이스는 계속 실행**합니다.

### 빈 값도 명시적으로 채운다

```python
if step.action == "fill":
    # 빈 값도 명시적으로 채운다. required 위반 케이스는 '비워 두는
    # 것' 자체가 검증 대상이므로 건너뛰면 안 된다.
    locator.fill(step.value or "", timeout=ctx.step_timeout_ms)
```

"값이 비었으니 건너뛰자"고 최적화하면 `required` 검증 케이스가 사라집니다. 빈 값을 넣는
것이 그 케이스의 목적입니다.

### 체크박스에 `fill()`을 부르면 안 된다

회원가입 화면을 추가하면서 바로 터진 부분입니다. 처음 코드는 값을 채울 수 있는 요소
전부에 `fill`을 썼는데, 체크박스에 `fill()`을 부르면 Playwright가 이렇게 실패합니다.

```
Element is not an <input> that can be filled
```

이 실패는 "요소 조작 오류(`input_error`)"로 기록됩니다. **문제는 판정이 뭉개진다는
것입니다.** 그 케이스가 확인하려던 것은 "약관에 동의하지 않으면 에러가 뜨는가"였는데,
결과는 "요소를 조작할 수 없었다"가 됩니다. 구현에 검증이 있는지 없는지 알 수 없습니다.

→ 요소 유형마다 액션을 나눴습니다.

```python
# generator.py 의 _input_step()
if element.type == "checkbox":
    return TestStep(seq=seq, action="check" if value else "uncheck", target=element.label)
if element.type == "select":
    return TestStep(seq=seq, action="select", target=element.label, value=value)
return TestStep(seq=seq, action="fill", target=element.label, value=value)
```

```python
# playwright_driver.py
elif step.action == "check":
    locator.check(timeout=ctx.step_timeout_ms)
elif step.action == "uncheck":
    locator.uncheck(timeout=ctx.step_timeout_ms)
else:
    locator.select_option(step.value or "", timeout=ctx.step_timeout_ms)
```

**빈 값 = "체크 해제 / 선택 안 함"** 이라는 규칙을 두어, `fill`과 같은 방식으로
`required` 위반을 표현합니다.

`uncheck`는 이미 해제된 체크박스에 대해 아무 일도 하지 않습니다. 그래도 스텝으로
남깁니다 — 스텝이 없으면 그 케이스가 **무엇을 확인했는지** 나중에 알 수 없습니다.
리포트에서 "체크하지 않았다"는 사실이 검증 조건으로 읽혀야 합니다.

### 새 요소 유형도 라벨로 찾힌다

다행히 S3는 손볼 데가 없었습니다. `get_by_label("약관 동의")`이 체크박스를,
`get_by_label("가입 경로")`이 `<select>`를 그대로 찾아냅니다. `<label for="...">`로
연결돼 있으면 요소 종류와 무관하게 동작합니다.

`_role_for()`에 이미 매핑이 있었던 것도 도움이 됐습니다 — `checkbox → "checkbox"`,
`select → "combobox"`. **1차에서 쓰지 않는 유형까지 미리 적어둔 것이 여기서 값을 했습니다.**

### 브라우저가 값을 잘라내면 서버 검증을 확인할 수 없다

SUT의 닉네임 입력란에 `maxlength` 속성을 **일부러 넣지 않았습니다.**

```html
<!-- maxlength="10" 을 넣으면 안 된다 -->
<input type="text" id="nickname" name="nickname">
```

넣으면 브라우저가 11자를 10자로 잘라서 전송합니다. 그러면 서버는 규칙을 어긴 값을 아예
받지 못하고, **"서버에 최대 길이 검증이 있는가"를 확인할 방법이 사라집니다.**

기획서의 규칙은 서버가 강제해야 하는 것이고, Prova가 보려는 것도 그것입니다. 실무에서
프론트엔드에만 `maxlength`를 걸고 서버 검증을 잊는 것이 바로 이 프로젝트가 잡으려는
불일치 유형입니다.

### URL 조립

기획서에는 `/login`이라고 적혀 있고, 실제 주소는 `http://localhost:8100/good/login`입니다.

```python
def _resolve_url(ctx, target: str) -> str:
    if target.startswith(("http://", "https://")):
        return target
    return ctx.base_url.rstrip("/") + "/" + target.lstrip("/")
```

`urljoin`이라는 표준 함수가 있는데 쓰지 않았습니다. `urljoin("http://h/good", "/login")`은
`http://h/login`이 되어 **`/good`이 사라집니다.** 절대 경로를 호스트 루트에 붙이기 때문입니다.

이 처리가 **하나의 기획서로 `good`과 `bad` 두 구현을 검증할 수 있게** 하는 지점입니다.

---

## 확인해보기

```powershell
# SUT 띄우고
uv run uvicorn sut.app:app --port 8100

# 다른 터미널에서 — 요소 탐지가 어느 전략으로 되는지
uv run python -c "
import json
from playwright.sync_api import sync_playwright
from prova.models import ScreenSpec
from prova.s3_grounder.dom_locator import ground, GroundingError, STRATEGY_LABELS

spec = ScreenSpec.model_validate(json.load(open('fixtures/specs/login_spec.golden.json', encoding='utf-8')))
with sync_playwright() as p:
    page = p.chromium.launch().new_page()
    page.goto('http://localhost:8100/good/login')
    for e in spec.elements:
        try:
            loc = ground(page, e.label, e)
            print(f'OK   {e.label:8} -> {loc.strategy} ({STRATEGY_LABELS[loc.strategy]})')
        except GroundingError as ex:
            print(f'FAIL {e.label:8} -> {ex.reason}')
    # 없는 요소
    try:
        ground(page, '존재하지않는버튼')
    except GroundingError as ex:
        print('없는 요소:', ex.reason)
"
```

브라우저 창을 직접 보고 싶으면:

```powershell
uv run prova run --pdf fixtures/specs/login_spec.pdf --url http://localhost:8100/bad --headed
```

---

다음: [05-verdict-report.md](05-verdict-report.md) — 판정과 리포트, 뒤집힌 논리
