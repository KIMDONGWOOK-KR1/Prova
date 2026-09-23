"""표를 못 읽은 것을 '0건으로 확인' 으로 두지 않는다.

## 무엇이 문제였나

`_locate_table_cells` 는 `<th>` 텍스트가 라벨과 맞는 열을 찾는다. 그런데 그
머리글에 `colspan` 이 붙어 있으면 어느 열인지 정할 수 없어서 `absent` 를 돌려주고
있었다. `absent` 는 '화면에 없다' 는 뜻이고, 0건 기대에서는 **PASS 의 근거**다
(조건부 렌더링이 정상 구현이라서 — `test_assertion_engine.py` 참고).

그래서 이런 일이 벌어졌다. 표에 주문이 3건 있고 머리글도 화면에 **있는데**,
도구가 열을 못 정했다는 이유로 판정이 이렇게 났다.

    기대 0건 -> PASS: '주문일' 이 렌더되지 않음 — 0건으로 확인

도구가 확인하지 못한 것이 '확인해서 0건' 으로 둔갑한다. 설계 판단 19 가 금지한
모양이고, 이 저장소가 가장 위험하다고 적어 둔 실패다 — FAIL 은 눈에 띄지만
**빈 통과는 아무 흔적도 남기지 않는다.**

## 고치는 방향

머리글을 **찾았는데 읽을 수 없는** 경우를 `absent` 와 갈라 `unverifiable` 로
돌려준다. 판정은 기대 건수와 무관하게 FAIL 이고, 분류는 `assertion_mismatch`
(기획서와 다름)가 아니라 `unverifiable`(확인 불가)이다 — 구현 결함이 아니라
도구의 한계이므로 '실행 문제' 쪽에 묶여야 개발자가 엉뚱한 곳을 고치지 않는다.

**머리글이 정말 화면에 없는 경우는 그대로 `absent` 다.** 그건 화면에 대한 참인
진술이고, 0건 기대에서 PASS 가 나는 것이 맞다. 이 파일의 회귀 테스트가 그
경계를 지킨다.
"""

from __future__ import annotations

import pytest

from prova.models import Expectation, StepResult, TestCase, TestStep
from prova.s3_grounder.dom_locator import (
    CollectionCount,
    collect_item_texts,
    count_items,
)
from prova.s5_verifier.assertion_engine import PageState, verify
from prova.models import UIElement


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        yield pg
        browser.close()


def hint(label: str, type_: str = "text") -> UIElement:
    return UIElement(element_id="x", type=type_, label=label)


# 머리글 '주문일' 이 두 열에 걸쳐 있다. 본문에는 주문이 3건 있다 —
# 즉 화면에는 분명히 내용이 있고, 못 읽는 것은 도구 쪽이다.
COLSPAN_TABLE = """
<table>
  <thead><tr><th colspan="2">주문일</th><th>금액</th></tr></thead>
  <tbody>
    <tr><td>2026-09-01</td><td>10:00</td><td>10,000원</td></tr>
    <tr><td>2026-09-02</td><td>11:00</td><td>20,000원</td></tr>
    <tr><td>2026-09-03</td><td>12:00</td><td>30,000원</td></tr>
  </tbody>
</table>
"""

# 비교군 — 머리글이 붙어 있고 colspan 이 없다. 이 표는 그대로 읽혀야 한다.
PLAIN_TABLE = """
<table>
  <thead><tr><th>주문일</th><th>금액</th></tr></thead>
  <tbody>
    <tr><td>2026-09-01</td><td>10,000원</td></tr>
    <tr><td>2026-09-02</td><td>20,000원</td></tr>
  </tbody>
</table>
"""


class TestGrounder:
    """S3 — 찾았는데 못 읽은 것을 '없다' 고 말하지 않는다."""

    def test_colspan_머리글은_absent_가_아니다(self, page):
        page.set_content(COLSPAN_TABLE)
        r = count_items(page, "주문일", hint("주문일"))
        assert r.status == "unverifiable", (
            "머리글이 화면에 있는데 absent 로 돌려주면 '0건으로 확인' 통과가 난다"
        )

    def test_colspan_사유를_남긴다(self, page):
        page.set_content(COLSPAN_TABLE)
        r = count_items(page, "주문일", hint("주문일"))
        assert "colspan" in r.detail and "주문일" in r.detail

    def test_텍스트_수집도_같은_status_다(self, page):
        """개수와 값이 같은 탐색(_locate_collection)을 쓰므로 판정도 갈리면 안 된다."""
        page.set_content(COLSPAN_TABLE)
        r = collect_item_texts(page, "주문일", hint("주문일"))
        assert r.status == "unverifiable"
        assert r.texts == []

    def test_머리글이_정말_없으면_absent_그대로(self, page):
        """회귀 — 화면에 대한 참인 진술은 바뀌면 안 된다."""
        page.set_content(PLAIN_TABLE)
        r = count_items(page, "상품명", hint("상품명"))
        assert r.status == "absent"

    def test_colspan_없는_표는_그대로_읽힌다(self, page):
        """회귀 — 기존 경로가 좁아지지 않았는지 본다."""
        page.set_content(PLAIN_TABLE)
        r = collect_item_texts(page, "주문일", hint("주문일"))
        assert r.status == "ok"
        assert r.texts == ["2026-09-01", "2026-09-02"]


def steps_ok(n: int = 4) -> list[StepResult]:
    return [StepResult(seq=i, action="fill", target="t", status="ok", elapsed_ms=10,
                       screenshot=f"runs/x/step{i}.png")
            for i in range(1, n + 1)]


def count_case(want: int) -> TestCase:
    return TestCase(
        case_id=f"orders-count-{want}",
        screen_id="orders",
        type="positive",
        title="주문 건수",
        steps=[TestStep(seq=1, action="navigate", target="/orders")],
        expected=Expectation(type="result_count", count=want, count_target="주문일"),
    )


def counted(status: str, n: int = 0) -> CollectionCount:
    return CollectionCount(target="주문일", status=status, count=n,
                           detail="표 머리글 '주문일' 가 여러 열에 걸쳐 있어(colspan) "
                                  "열을 정할 수 없음")


def state(collection: CollectionCount) -> PageState:
    return PageState(url="http://h/good/orders", text="", collection=collection)


class TestVerdict:
    """S5 — 확인 불가는 기대 건수와 무관하게 통과가 아니다."""

    def test_0건_기대여도_PASS_가_아니다(self):
        v = verify(count_case(0), steps_ok(), state(counted("unverifiable")))
        assert v.verdict == "FAIL", "이것이 이 변경의 핵심이다 — 빈 통과를 막는다"

    def test_1건_이상_기대도_FAIL(self):
        v = verify(count_case(3), steps_ok(), state(counted("unverifiable")))
        assert v.verdict == "FAIL"

    def test_구현_결함으로_분류하지_않는다(self):
        """'기획서와 다름' 으로 두면 없는 결함을 보고하는 것이다 (설계 판단 19)."""
        v = verify(count_case(0), steps_ok(), state(counted("unverifiable")))
        assert v.failure_category == "unverifiable"

    def test_사유가_도구의_한계임을_말한다(self):
        v = verify(count_case(0), steps_ok(), state(counted("unverifiable")))
        actual = v.evidence["actual"]
        assert "확인" in actual
        assert "0건으로 확인" not in actual, "못 읽은 것을 확인했다고 말하면 안 된다"

    def test_목록이_없고_0건_기대면_여전히_PASS(self):
        """회귀 — 조건부 렌더링이 정상 구현인 경로는 건드리지 않는다."""
        v = verify(count_case(0), steps_ok(), state(counted("absent")))
        assert v.verdict == "PASS"
