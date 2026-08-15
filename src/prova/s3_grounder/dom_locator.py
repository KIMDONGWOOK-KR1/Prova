"""S3 — 자연어 라벨을 실제 조작 가능한 요소로 바꾼다 (selector-first).

## 왜 라벨에서 출발하는가

TestStep.target 은 '이메일', '로그인' 같은 기획서의 라벨이다. CSS selector 나
XPath 가 아니다. 이렇게 분리해 둔 이유가 두 가지 있다.

1) 기획서는 selector 를 모른다. 기획자가 쓴 '이메일' 이 구현에서 #email 인지
   input[name=userEmail] 인지는 구현을 봐야 안다. 그 연결을 이 모듈이 맡는다.
2) 같은 TestCase 를 selector 방식과 VLM 방식 양쪽으로 실행해 비교할 수 있다
   (명세서 §9 의 'selector vs VLM 탐지 성공률·속도 비교').

## 탐지 우선순위 (명세서 §5-1)

    1. get_by_label        폼 필드 — <label for> 로 연결된 것
    2. get_by_placeholder  라벨이 없고 placeholder 만 있는 필드
    3. get_by_role(name=)  버튼·링크 — 접근성 이름
    4. get_by_text         위 어느 것도 안 될 때

접근성 속성을 먼저 보는 이유는, 그것이 구현 세부(클래스명·DOM 구조)와 가장
느슨하게 결합돼 있어서다. 개발자가 리팩터링으로 클래스명을 바꿔도 라벨은
그대로 남는 경우가 많다.

## '정확히 1개 & 보이는 것' 만 확정한다

후보가 0개면 못 찾은 것이고, 여러 개면 어느 것을 조작해야 할지 모른다. 아무거나
집어서 진행하면 그 케이스의 FAIL 이 구현 결함 때문인지 잘못된 요소를 눌러서인지
구분할 수 없게 된다. 그래서 모호하면 실패로 처리하고 원인을 남긴다.

1차 범위는 여기서 끝난다. 2차에서 이 실패 지점이 VLM fallback 과
self-healing 의 진입점이 된다 (GroundingError 를 S6 가 받는다).
"""

from __future__ import annotations

from dataclasses import dataclass

from prova.models import ElementLocation, UIElement

# 전략 이름 -> 사람이 읽는 설명. 리포트와 평가 지표에 쓴다.
STRATEGY_LABELS = {
    "label": "<label> 연결",
    "placeholder": "placeholder",
    "role": "접근성 role+name",
    "text": "텍스트 일치",
}


class GroundingError(RuntimeError):
    """요소를 확정하지 못했다.

    2차에서 이 예외가 self-heal 의 트리거가 된다. 그때 필요한 정보(무엇을
    찾으려 했고, 각 전략이 몇 개를 찾았는지)를 지금부터 담아 둔다.
    """

    def __init__(self, target: str, attempts: list["Attempt"]) -> None:
        self.target = target
        self.attempts = attempts
        detail = ", ".join(f"{a.strategy}={a.count}개" for a in attempts) or "시도 없음"
        super().__init__(f"'{target}' 요소를 확정하지 못했습니다 ({detail})")

    @property
    def reason(self) -> str:
        """왜 실패했는지 한 줄로. 리포트의 실패 상세에 들어간다."""
        if any(a.count > 1 for a in self.attempts):
            return "후보가 여러 개여서 어느 것을 조작할지 확정할 수 없음"
        if any(a.count == 1 and not a.visible for a in self.attempts):
            return "요소를 찾았으나 화면에 보이지 않음"
        return "일치하는 요소가 없음"


@dataclass
class Attempt:
    """전략 하나의 시도 결과. 실패 원인을 설명하고 평가 지표를 내는 근거."""

    strategy: str
    count: int
    visible: bool = False


def _describe(locator, strategy: str, target: str) -> str:
    """확정된 요소를 사람이 읽을 수 있는 selector 문자열로.

    Playwright 의 Locator 는 내부 표현을 그대로 노출하지 않으므로, 어떤 전략으로
    무엇을 찾았는지를 재현 가능한 형태로 적어 둔다. 리포트에서 개발자가
    '이 요소를 이렇게 찾았다' 를 확인하는 근거가 된다.
    """
    return f"{strategy}={target!r}"


def _try_strategies(page, target: str, hint: UIElement | None):
    """전략을 순서대로 시도하고 (locator, strategy, attempts) 를 돌려준다.

    Playwright 의 get_by_* 는 호출 자체로는 DOM 을 건드리지 않는다(지연 평가).
    count() 를 부르는 시점에 조회가 일어난다.
    """
    attempts: list[Attempt] = []
    candidates = [
        ("label", lambda: page.get_by_label(target, exact=True)),
        ("placeholder", lambda: page.get_by_placeholder(target, exact=True)),
        ("role", lambda: page.get_by_role(_role_for(hint), name=target, exact=True)),
        ("text", lambda: page.get_by_text(target, exact=True)),
    ]

    # 힌트로 placeholder 를 알고 있으면 그 값으로도 시도한다. 기획서가 라벨과
    # placeholder 를 따로 적어 둔 경우에 대응한다.
    if hint and hint.placeholder:
        candidates.insert(
            2, ("placeholder", lambda: page.get_by_placeholder(hint.placeholder, exact=True))
        )

    for strategy, build in candidates:
        try:
            locator = build()
            count = locator.count()
        except Exception:
            # role 전략은 hint 가 없으면 role 을 추측하므로 실패할 수 있다.
            # 한 전략의 실패가 다음 전략을 막지 않게 한다.
            attempts.append(Attempt(strategy=strategy, count=0))
            continue

        if count == 1:
            visible = locator.is_visible()
            attempts.append(Attempt(strategy=strategy, count=1, visible=visible))
            if visible:
                return locator, strategy, attempts
        else:
            attempts.append(Attempt(strategy=strategy, count=count))

    return None, None, attempts


def _role_for(hint: UIElement | None) -> str:
    """UIElement.type 을 ARIA role 로. 힌트가 없으면 버튼으로 가정한다.

    버튼을 기본값으로 두는 이유: 라벨 기반 탐지가 실패해 role 까지 내려오는
    경우는 대개 버튼·링크다. 입력 필드는 앞의 label/placeholder 에서 잡힌다.
    """
    if hint is None:
        return "button"
    return {
        "input": "textbox",
        "button": "button",
        "link": "link",
        "select": "combobox",
        "checkbox": "checkbox",
        "text": "paragraph",
    }.get(hint.type, "button")


def ground(page, target: str, hint: UIElement | None = None) -> ElementLocation:
    """target 라벨에 해당하는 요소를 확정한다.

    Args:
        page: Playwright Page
        target: 기획서의 자연어 라벨 (예: "이메일", "로그인")
        hint: 해당 UIElement. type 으로 role 을 좁히고 placeholder 를 활용한다.

    Raises:
        GroundingError: 확정 실패. 2차에서 self-heal 트리거가 된다.
    """
    locator, strategy, attempts = _try_strategies(page, target, hint)
    if locator is None:
        raise GroundingError(target, attempts)

    return ElementLocation(
        target=target,
        method="selector",
        selector=_describe(locator, strategy, target),
        confidence=1.0,
        healed=False,
        strategy=strategy,
    )


def resolve_locator(page, location: ElementLocation, hint: UIElement | None = None):
    """ElementLocation 을 다시 조작 가능한 Playwright Locator 로 만든다.

    ElementLocation 은 직렬화 가능한 기록(리포트에 담기는 값)이고, Locator 는
    브라우저 세션에 묶인 객체다. 둘을 한 타입으로 합치면 리포트를 JSON 으로
    저장할 수 없게 되므로 분리해 두고, 조작 시점에 이 함수로 되살린다.
    """
    strategy = location.strategy
    target = location.target
    if strategy == "label":
        return page.get_by_label(target, exact=True)
    if strategy == "placeholder":
        return page.get_by_placeholder(target, exact=True)
    if strategy == "role":
        return page.get_by_role(_role_for(hint), name=target, exact=True)
    if strategy == "text":
        return page.get_by_text(target, exact=True)
    raise GroundingError(target, [Attempt(strategy=str(strategy), count=0)])
