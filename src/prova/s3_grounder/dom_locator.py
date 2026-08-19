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

from dataclasses import dataclass, field
from typing import Literal

from prova.models import ElementLocation, UIElement
from prova.text_utils import normalize_ws

#: 전략 이름 -> 사람이 읽는 설명. 리포트의 스텝 표에 쓴다.
#
# 점검에서 이 표가 어디에도 쓰이지 않는 것을 찾았다 — 주석은 "리포트와 평가 지표에
# 쓴다" 고 했는데 리포트는 원시 이름(label·role)을 그대로 찍고 있었다. 그리고
# 2차 경로가 생긴 뒤에도 vlm 이 빠져 있었다. 주석이 하는 일을 말하지 않으면
# 읽는 사람이 코드를 잘못 이해한다.
STRATEGY_LABELS = {
    "label": "<label> 연결",
    "placeholder": "안내 문구",
    "role": "접근성 role+name",
    "text": "텍스트 일치",
    "vlm": "화면 이미지 (2차)",
}


def strategy_label(strategy: str | None) -> str:
    """리포트에 보여줄 전략 이름. 모르는 값은 그대로 보여준다 — 표에 없다는 이유로
    정보를 지우면 어떤 경로로 찾았는지 알 수 없게 된다."""
    if not strategy:
        return ""
    return STRATEGY_LABELS.get(strategy, strategy)


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
        "list": "list",
    }.get(hint.type, "button")


# 기획서가 선언한 유형과 화면의 실제 role 을 대조할 유형.
#
# ## 왜 버튼·링크만인가
#
# role 매핑을 신뢰할 수 있는 유형만 넣는다. 입력란은 넣을 수 없다 —
# input[type=password] 는 ARIA 에서 textbox role 을 갖지 않으므로, 대조하면
# 비밀번호 칸마다 '유형 불일치' 가 떠서 전부 오탐이 된다.
#
# 버튼과 링크는 그 대조가 정확하고, **가장 값진 대조이기도 하다.** 둘의 차이가
# 사용자에게 실제로 드러나기 때문이다 — 링크는 새 탭으로 열 수 있고 주소를
# 복사할 수 있고 스크린리더가 '링크' 로 읽는다. 기획서가 링크라고 적었는데
# 버튼으로 구현했다면 그건 기획-구현 불일치다.
ROLE_CHECKED_TYPES = ("button", "link")

# ElementType -> 기획서가 쓰는 낱말. 실패 사유를 기획서와 같은 낱말로 쓴다.
TYPE_WORDS = {"button": "버튼", "link": "링크"}


class SpecTypeMismatch(RuntimeError):
    """요소는 찾았지만 기획서가 적은 유형이 아니다.

    GroundingError 와 나눠 둔 이유: 이건 탐지 실패가 아니라 **기획-구현 불일치**다.
    같은 실패로 묶으면 리포트에서 '요소를 못 찾았다' 로 분류되어, 개발자가 라벨을
    고치려 들게 된다. 고쳐야 할 것은 요소의 종류다.
    """

    def __init__(self, target: str, declared: str, role: str) -> None:
        self.target = target
        self.declared = declared
        self.role = role
        # 기획서가 쓴 낱말로 말한다. 'link' 가 아니라 '링크' 다 — 리포트를 읽는
        # 사람이 기획서와 대조할 때 같은 낱말이어야 찾는 시간이 줄어든다.
        self.declared_word = TYPE_WORDS.get(declared, declared)
        super().__init__(
            f"기획서는 '{target}' 을 '{self.declared_word}'(으)로 적었는데 화면의 "
            f"그 요소는 {role} role 이 아닙니다"
        )

    @property
    def reason(self) -> str:
        return (
            f"기획서의 유형('{self.declared_word}')과 구현이 다릅니다 — "
            f"{self.role} role 로는 찾을 수 없고 다른 종류의 요소로 구현돼 있습니다"
        )


def _check_declared_role(page, target: str, hint: UIElement | None) -> None:
    """기획서가 선언한 유형대로 구현됐는지 본다. 아니면 예외를 던진다.

    role 로 찾히면 통과다. 탐지 자체는 다른 전략(텍스트 일치 등)으로 성공할 수
    있으므로, 여기서 막지 않으면 **버튼으로 구현된 링크를 아무 말 없이 눌러 준다.**
    그러면 기획서가 유형을 적어 둔 것이 검증에 아무 영향을 주지 않는다.

    조회 자체가 실패하면 통과로 둔다. 도구 문제로 기획-구현 불일치를 보고하면
    개발자가 없는 결함을 찾게 된다.
    """
    if hint is None or hint.type not in ROLE_CHECKED_TYPES:
        return
    role = _role_for(hint)
    try:
        found = page.get_by_role(role, name=target, exact=True).count()
    except Exception:
        return
    if found == 0:
        raise SpecTypeMismatch(target, hint.type, role)


def ground(page, target: str, hint: UIElement | None = None) -> ElementLocation:
    """target 라벨에 해당하는 요소를 확정한다.

    Args:
        page: Playwright Page
        target: 기획서의 자연어 라벨 (예: "이메일", "로그인")
        hint: 해당 UIElement. type 으로 role 을 좁히고 placeholder 를 활용한다.

    Raises:
        GroundingError: 확정 실패. 2차에서 self-heal 트리거가 된다.
        SpecTypeMismatch: 찾았지만 기획서가 적은 유형이 아니다 (기획-구현 불일치).
    """
    locator, strategy, attempts = _try_strategies(page, target, hint)
    if locator is None:
        raise GroundingError(target, attempts)

    # 탐지 뒤에 본다. 먼저 보면 요소가 아예 없는 경우까지 '유형 불일치' 로
    # 보고하게 되는데, 그 둘은 개발자가 할 일이 다르다.
    _check_declared_role(page, target, hint)

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


# ---------------------------------------------------------------------------
# 반복 목록을 세는 경로 (result_count)
# ---------------------------------------------------------------------------
#
# ## 왜 별도 경로인가
#
# 위의 ground() 는 '정확히 1개' 만 확정한다. 그 계약이 지금까지 판정을 신뢰할
# 근거였다 — 후보가 여럿일 때 아무거나 집으면 FAIL 이 구현 결함 때문인지 잘못된
# 요소를 눌러서인지 구분할 수 없다.
#
# 건수를 세려면 여러 개를 봐야 한다. 그렇다고 ground() 를 느슨하게 만들면 기존
# 세 화면의 판정 근거가 함께 약해진다. 그래서 계약을 건드리지 않고 경로를
# 하나 더 둔다.
#
# 그리고 여기서도 계약은 유지된다. **컨테이너는 여전히 정확히 1개여야 한다.**
# 세는 것은 그 안의 항목이다. '어디를 셀 것인가' 는 모호하지 않고, 모호한 것은
# '그 안에 몇 개인가' 뿐이며 그건 세면 답이 나온다.

# 목록 유형 -> 그 안에서 반복되는 항목의 ARIA role.
# <ul><li> 의 li 는 listitem, <table><tr> 의 tr 은 row 다.
ITEM_ROLES = {"list": "listitem", "table": "row"}


def _locate_collection(page, target: str, hint: UIElement | None):
    """반복 목록을 라벨로 찾는다. count_items 와 collect_item_texts 가 공유하는
    탐색 core — '어디를 볼 것인가' 는 두 경로에서 같아야 한다.

    이 핵심을 공유하지 않으면 라벨이 없거나 컨테이너가 여러 개인 상황에서 두
    함수가 서로 다른 판정(absent/ambiguous)을 내릴 수 있고, 그러면 개수와 값이
    '같은 곳을 본 결과'라는 전제가 깨진다.

    ## 두 가지 반복 모양

    hint.type 이 list/table 이면 **컨테이너 + 항목** 모양이다 — 목록 라벨을 가진
    요소 하나(<ul aria-label=...>) 안에 항목(listitem/row)이 반복된다. 건수
    세기(expect_count, 검색 결과 목록)가 이 모양이다.

    그 외(text 등)면 **반복되는 라벨 자체**가 항목이다 — 감싸는 컨테이너가
    따로 없고, 같은 aria-label 을 가진 요소가 행마다 그대로 반복된다(주문조회의
    '주문일'·'금액' 처럼: `<span aria-label="주문일">` 이 행마다 하나씩 있다).
    이때는 target 라벨로 찾은 요소들 자체가 항목이므로 item_role 을 None 으로
    돌려준다 — 호출자가 그 밑에서 다시 항목을 찾지 않는다. 개수 제약도 다르다 —
    컨테이너는 '정확히 1개' 여야 하지만, 반복 라벨은 **여러 개인 것이 정상**이다
    (행이 5개면 5개 나와야 한다). '합계' 처럼 화면에 한 번만 있는 라벨도 이
    경로로 자연히 1개가 나온다.

    Returns:
        (status, container, item_role, found, detail) 튜플.
        status 가 "ok" 일 때만 container 가 유효한 Locator 다. item_role 이
        None 이면 container 자체가 이미 항목 목록이다. found 는 라벨과 일치한
        컨테이너(또는 반복 라벨) 개수 — ambiguous 일 때 호출자가 몇 개가
        겹쳤는지 그대로 보고할 수 있게 남겨 둔다.
    """
    if hint is not None and hint.type not in ("list", "table"):
        try:
            items = page.get_by_label(target, exact=True)
            found = items.count()
        except Exception as exc:
            return "absent", None, None, 0, f"요소 조회 실패: {exc}"
        if found == 0:
            return "absent", None, None, 0, f"라벨 {target!r} 인 요소가 화면에 없음"
        return "ok", items, None, found, ""

    container_role = _role_for(hint) if hint else "list"
    item_role = ITEM_ROLES.get(container_role, "listitem")

    try:
        container = page.get_by_role(container_role, name=target, exact=True)
        found = container.count()
    except Exception as exc:  # role 조회 자체가 실패한 경우
        return "absent", None, item_role, 0, f"목록 조회 실패: {exc}"

    if found == 0:
        return (
            "absent", None, item_role, 0,
            f"role={container_role} name={target!r} 인 목록이 화면에 없음",
        )
    if found > 1:
        # 컨테이너의 '정확히 1개' 계약은 여기서도 유지한다. 어느 목록을 볼지
        # 모르는 상태에서 아무거나 고르면 그 결과를 신뢰할 수 없다.
        return (
            "ambiguous", None, item_role, found,
            f"같은 라벨의 목록이 {found}개 — 어느 것을 볼지 확정할 수 없음",
        )

    return "ok", container, item_role, 1, ""


@dataclass
class CollectionCount:
    """반복 목록의 항목 수를 센 결과.

    ## status 를 count 와 나눠 둔 이유

    '못 찾았다' 와 '0개다' 는 다른 사실인데 숫자로는 둘 다 0 이다. 합치면 판정이
    거짓말을 한다.

    검색 결과 0건인 화면은 목록 자체를 렌더하지 않는 것이 정상이다 (조건부
    렌더링). 그때 컨테이너를 못 찾은 것을 탐지 실패로 처리하면, 구현이 완벽한
    화면에서 '0건이어야 한다' 는 케이스가 오탐으로 FAIL 이 된다.

    반대로 3건이 나와야 하는데 목록이 없는 것은 진짜 실패다. 같은 status=absent
    이지만 기대값이 다르므로 판정이 갈린다 — 그 판단은 S5 가 한다. S3 는 무엇을
    봤는지만 사실대로 보고한다.
    """

    target: str
    status: str          # "ok" | "absent" | "ambiguous"
    count: int = 0
    detail: str = ""


def count_items(page, target: str, hint: UIElement | None = None) -> CollectionCount:
    """target 라벨의 반복 목록에 항목이 몇 개 렌더됐는지 센다.

    예외를 던지지 않는다. ground() 와 다른 점이다 — 목록의 부재는 그 자체로
    판정 재료이므로(위 설명 참고) 실패가 아니라 관측 결과로 돌려준다.

    Args:
        page: Playwright Page
        target: 목록의 라벨 (예: "검색 결과 목록")
        hint: 해당 UIElement. type 으로 컨테이너 role 과 항목 role 을 정한다.

    Returns:
        CollectionCount. status 가 "ok" 일 때만 count 가 의미를 가진다.
    """
    status, container, item_role, found, detail = _locate_collection(page, target, hint)
    if status != "ok":
        # ambiguous 일 때는 found 가 겹친 컨테이너 개수다 — 기존 계약대로
        # count 에도 남긴다. absent 일 때는 0 그대로다.
        return CollectionCount(target=target, status=status, count=found, detail=detail)

    # item_role 이 None 이면 반복 라벨 모양이다(_locate_collection 설명 참고) —
    # container 자체가 이미 항목 목록이므로 개수도 이미 found 에 있다.
    if item_role is None:
        return CollectionCount(
            target=target, status="ok", count=found,
            detail=f"라벨 {target!r} 요소 {found}개",
        )

    try:
        n = container.get_by_role(item_role).count()
    except Exception as exc:
        return CollectionCount(target=target, status="absent",
                               detail=f"항목 조회 실패: {exc}")

    return CollectionCount(
        target=target, status="ok", count=n,
        detail=f"{target!r} 안의 {item_role} {n}개",
    )


@dataclass
class CollectionTexts:
    """반복 목록의 항목마다 텍스트를 담은 결과.

    ## count_items 와 나란히 두는 이유

    Phase B 의 정렬·합계 판정은 '몇 개인가' 로는 답이 안 나온다 — 값이 무엇이고
    몇 번째에 있는지를 봐야 한다. 그렇다고 count_items 를 바꾸면 이미 그 숫자만
    보는 소비자(검색 결과 건수 등)가 매번 텍스트까지 읽는 비용을 치르게 된다.
    그래서 같은 탐색 위에 별도의 결과 타입을 얹는다.

    status 를 CollectionCount 와 똑같이 셋으로 나눈 이유도 같다. 목록의 부재는
    실패가 아니라 관측 결과다(위 CollectionCount 설명 참고) — count 와 같은
    이유로, texts 도 '못 찾았다' 를 빈 배열로 뭉개지 않는다.
    """

    status: Literal["ok", "absent", "ambiguous"]
    texts: list[str] = field(default_factory=list)
    detail: str = ""


def collect_item_texts(page, target: str, hint: UIElement | None = None) -> CollectionTexts:
    """target 라벨의 반복 목록에서 각 항목의 텍스트를 문서 순서대로 모은다.

    count_items 와 같은 탐색(_locate_collection)을 쓴다 — '어디를 볼 것인가' 가
    갈리면 개수와 값이 같은 목록을 본 결과라는 전제가 깨진다. 예외를 던지지
    않는다. count_items 와 같은 이유다: 목록의 부재는 판정 재료이지 도구 실패가
    아니다.

    각 항목의 텍스트는 inner_text 를 normalize_ws 로 정리한 값이다. assertion_engine
    이 화면 문구를 비교할 때 쓰는 것과 같은 정규화라서, 다른 경로로 읽은 같은
    값이 공백 차이만으로 다르게 보이는 일이 없다.

    Args:
        page: Playwright Page
        target: 목록의 라벨 (예: "주문일")
        hint: 해당 UIElement. type 으로 컨테이너 role 과 항목 role 을 정한다.

    Returns:
        CollectionTexts. status 가 "ok" 일 때만 texts 가 의미를 가진다.
    """
    status, container, item_role, _found, detail = _locate_collection(page, target, hint)
    if status != "ok":
        return CollectionTexts(status=status, texts=[], detail=detail)

    try:
        # item_role 이 None 이면 반복 라벨 모양이다(_locate_collection 설명
        # 참고) — container 자체가 이미 항목 목록이므로 그 아래에서 다시
        # 찾지 않는다.
        items = container if item_role is None else container.get_by_role(item_role)
        texts = [normalize_ws(t) for t in items.all_inner_texts()]
    except Exception as exc:
        return CollectionTexts(status="absent",
                               texts=[], detail=f"항목 조회 실패: {exc}")

    where = f"{target!r}" if item_role is None else f"{target!r} 안의 {item_role}"
    return CollectionTexts(
        status="ok", texts=texts,
        detail=f"{where} {len(texts)}개",
    )


def read_options(page, target: str, hint: UIElement | None = None) -> list[str] | None:
    """선택 요소가 화면에 실제로 담고 있는 항목들. 못 읽으면 None.

    ## 왜 이 조회가 필요한가

    기획서의 '선택 목록: 검색, 지인 추천, 광고' 는 지금까지 **정상 케이스가 넣을 값을
    고르는 데만** 쓰였다. 첫 항목을 골라 넣고 그것이 있으면 통과한다. 그래서 화면에
    '지인 추천' 이 빠져 있어도 아무 일도 일어나지 않았다 — 선택 항목 누락은 흔한
    결함인데 보이지 않는 구멍이었다.

    ## 예외를 던지지 않는다

    None 은 '읽지 못했다' 이고 빈 목록은 '항목이 하나도 없다' 다. 둘은 다른 사실이고,
    판정이 갈린다 — 못 읽은 것을 '항목 0개' 로 보고하면 도구 문제를 구현 결함으로
    보고하게 된다.

    안내용 첫 항목('선택하세요' 등)은 걸러내지 않는다. 무엇이 안내인지 추측하면
    기획서에 있는 항목을 안내로 착각해 없다고 보고할 수 있다. 대조는 '기획서 항목이
    화면에 다 있는가' 만 보므로 안내 항목이 더 있어도 통과한다.
    """
    try:
        locator = page.get_by_label(target, exact=True)
        if locator.count() != 1:
            role = _role_for(hint) if hint else "combobox"
            locator = page.get_by_role(role, name=target, exact=True)
            if locator.count() != 1:
                return None
        texts = locator.locator("option").all_text_contents()
    except Exception:
        return None
    return [t.strip() for t in texts]


def read_placeholders(page, labels: list[str]) -> dict[str, str]:
    """라벨별로 화면의 입력 안내 문구(placeholder)를 읽는다.

    ## 없는 키와 빈 값을 구별한다

        키가 없다   그 라벨의 요소를 화면에서 찾지 못했다
        빈 문자열   요소는 있는데 placeholder 가 없다

    둘은 개발자가 할 일이 다르다 — 하나는 요소를 만들거나 라벨을 맞춰야 하고, 하나는
    속성을 넣어야 한다. 합치면 리포트가 엉뚱한 곳을 가리킨다.

    라벨로만 찾는다(get_by_label). placeholder 를 가진 요소는 폼 입력란이고, 이
    프로젝트의 기획서는 입력란마다 라벨을 정의하기 때문이다. 라벨 연결이 없는 화면은
    애초에 S3 의 첫 전략이 통하지 않으므로 그 자체가 먼저 드러난다.
    """
    found: dict[str, str] = {}
    for label in labels:
        try:
            locator = page.get_by_label(label, exact=True)
            if locator.count() != 1:
                continue
            found[label] = locator.get_attribute("placeholder") or ""
        except Exception:
            continue
    return found


# ---------------------------------------------------------------------------
# 2차 경로 — 화면 이미지로 찾는다 (self-healing 진입점)
# ---------------------------------------------------------------------------
#
# ## 언제 여기로 오는가
#
# ground() 가 GroundingError 를 던졌을 때만이다. 접근성 속성이 통하면 그걸 쓴다 —
# 이미지 추론은 느리고, 좌표는 화면이 조금 바뀌면 낡고, 정확도를 보증할 수 없다.
#
# ## 보정이 사실을 지워서는 안 된다
#
# 이 경로가 만드는 가장 큰 위험은 오탐이 아니라 **미탐**이다. 기획서의 라벨로 요소를
# 찾을 수 없다는 것은 그 자체로 기획-구현 불일치인데(라벨 연결이 없거나 이름이 다르다),
# 이미지로 찾아 케이스를 통과시키면 그 사실이 리포트에서 사라진다.
#
# 그래서 보정한 케이스는 Verdict.healed 로 남고, 리포트가 그것을 따로 보여준다.
# 그리고 '라벨로 찾을 수 있는가' 를 확인하는 케이스를 따로 둔다
# (generator._label_case). 보정은 케이스를 살리는 것이고, 지적은 그대로 남는다.

# 이 값 아래면 보정을 포기한다.
#
# VLM 은 못 찾았을 때도 그럴듯한 좌표를 낸다. 그 좌표를 누르면 엉뚱한 곳을 눌러 놓고
# 케이스를 진행하게 되고, 그 FAIL 이 구현 결함인지 잘못 누른 것인지 구분할 수 없다 —
# ground() 가 '정확히 1개만 확정한다' 를 계약으로 삼은 것과 같은 이유다.
#: 2차 경로가 받아들일 기본 최소 신뢰도.
#
# VLM 은 못 찾았을 때도 그럴듯한 좌표를 낸다. 그 좌표를 누르면 엉뚱한 곳을 눌러
# 놓고 케이스를 진행하게 되고, FAIL 이 구현 결함인지 잘못 누른 것인지 구분할 수
# 없다. 설정(grounding.vlm_confidence_threshold)으로 덮어쓸 수 있다.
MIN_CONFIDENCE = 0.5

# UIElement.type -> VLM 에 줄 힌트. 사람이 화면을 보고 구분하는 말로 적는다.
VLM_HINTS = {
    "input": "입력란",
    "button": "버튼",
    "link": "링크",
    "select": "선택 목록",
    "checkbox": "체크박스",
    "list": "목록",
    "text": "텍스트",
}


def heal_with_vlm(page, target: str, vlm, hint: UIElement | None = None,
                  min_confidence: float = MIN_CONFIDENCE) -> ElementLocation:
    """화면 이미지로 요소의 위치를 찾는다. 실패하면 GroundingError 를 던진다.

    돌려주는 ElementLocation 은 selector 가 없고 bbox 만 있다. 조작은 좌표로 해야
    하므로 S4 가 method 로 분기한다 — resolve_locator() 로는 되살릴 수 없다.

    Raises:
        GroundingError: 호출 실패, 좌표가 이상함, 신뢰도 미달.
            보정 실패를 새 예외로 만들지 않는 이유: 호출자에게 필요한 사실은
            '요소를 확정하지 못했다' 하나이고, 그 처리는 이미 있다.
    """
    from prova.vlm.base import VLMError  # 순환 import 회피 (vlm 은 S3 를 모른다)

    try:
        shot = page.screenshot()
    except Exception as exc:
        raise GroundingError(target, [Attempt(strategy="vlm", count=0)]) from exc

    try:
        found = vlm.locate(image_png=shot, target=target,
                           hint=VLM_HINTS.get(hint.type, "") if hint else "")
    except VLMError:
        raise GroundingError(target, [Attempt(strategy="vlm", count=0)])

    if found.confidence < min_confidence or not found.is_sane():
        raise GroundingError(target, [Attempt(strategy="vlm", count=0)])

    return ElementLocation(
        target=target,
        method="vlm",
        selector=None,
        bbox=_to_pixels(page, found.bbox),
        confidence=found.confidence,
        healed=True,
        strategy="vlm",
    )


def _to_pixels(page, bbox: tuple[float, float, float, float]) -> list[int]:
    """0~1 상대값을 뷰포트 픽셀로. [x, y, w, h] 로 담는다 (ElementLocation 규약)."""
    size = page.viewport_size or {"width": 1280, "height": 800}
    w, h = size["width"], size["height"]
    x1, y1, x2, y2 = bbox
    return [round(x1 * w), round(y1 * h), round((x2 - x1) * w), round((y2 - y1) * h)]


def bbox_center(location: ElementLocation) -> tuple[float, float]:
    """bbox 의 중심 좌표. S4 가 여기를 누른다."""
    if not location.bbox or len(location.bbox) != 4:
        raise GroundingError(location.target, [Attempt(strategy="vlm", count=0)])
    x, y, w, h = location.bbox
    return x + w / 2, y + h / 2


def check_findable(page, elements: list[UIElement], labels: list[str]) -> dict[str, str]:
    """라벨별로 '접근성 속성으로 찾을 수 있는가'. 라벨 -> "" (가능) 또는 실패 사유.

    보정을 쓰지 않는다. 여기서 확인하는 것은 **보정 없이 찾을 수 있는가** 이고, 그게
    기획서의 라벨이 구현과 이어져 있는지를 뜻한다.

    유형 불일치(SpecTypeMismatch)는 '찾을 수 있다' 로 본다 — 요소는 지목됐고, 종류가
    다른 것은 그 케이스가 따로 보고한다. 여기서 겹쳐 보고하면 결함 하나가 두 곳에서
    같은 말을 한다.
    """
    by_label = {e.label: e for e in elements}
    result: dict[str, str] = {}
    for label in labels:
        try:
            ground(page, label, by_label.get(label))
            result[label] = ""
        except SpecTypeMismatch:
            result[label] = ""
        except GroundingError as exc:
            result[label] = exc.reason
    return result
