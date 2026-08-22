"""시맨틱 <table> 탐지 — aria-label 없는 순수 표 마크업에서 반복 요소를 찾는다.

## 왜 이 경로가 필요한가

반복 요소 탐지는 라벨(aria-label)로 간다. 주문조회 SUT 는 `<ul aria-label>` 로
만들어 그 한계를 피해 갔지만, 실물 화면은 `<table><thead><th>주문일</th>…` 처럼
라벨 없는 표로 온다. 그때 라벨 경로는 0개를 돌려주고, 0건 기대는 PASS · 정렬 기대는
absent FAIL 이 된다 — **탐지 한계가 화면 관측처럼 보이는** 자리다.

## 계약

- 라벨 경로가 0개일 때만 표 경로로 내려간다. 라벨이 있는 화면은 그대로다.
- 일치는 normalize_ws 정확 일치뿐이다. 부분 일치·유사도는 쓰지 않는다(오탐 0).
- 일치하는 caption/th 가 2개 이상이면 ambiguous — 집지 않는다.
- 어느 경로로 찾았는지 detail 에 남는다(리포트 사유로 흐른다).
"""

from __future__ import annotations

import pytest

from prova.models import UIElement
from prova.s3_grounder.dom_locator import collect_item_texts, count_items


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


TABLE = """
<table>
  <caption>주문 목록</caption>
  <thead><tr><th>주문번호</th><th>주문일</th><th> 금액 </th></tr></thead>
  <tbody>
    <tr><td>A1</td><td>2026-08-15</td><td>12,000원</td></tr>
    <tr><td>A2</td><td>2026-08-12</td><td>3,000원</td></tr>
    <tr><td>A3</td><td>2026-08-09</td><td>500원</td></tr>
  </tbody>
  <tfoot><tr><th>합계</th><td colspan="2">15,500원</td></tr></tfoot>
</table>
"""


class TestContainer:
    def test_caption_으로_표를_찾고_본문_행을_센다(self, page):
        page.set_content(TABLE)
        r = count_items(page, "주문 목록", hint("주문 목록", "list"))
        assert r.status == "ok"
        assert r.count == 3            # thead·tfoot 행은 세지 않는다
        assert "caption" in r.detail

    def test_caption_이_둘이면_ambiguous(self, page):
        page.set_content(TABLE + TABLE)
        r = count_items(page, "주문 목록", hint("주문 목록", "list"))
        assert r.status == "ambiguous"
        assert "2개" in r.detail


class TestColumn:
    def test_머리글로_열을_찾아_셀_값을_순서대로_모은다(self, page):
        page.set_content(TABLE)
        r = collect_item_texts(page, "주문일", hint("주문일"))
        assert r.status == "ok"
        assert r.texts == ["2026-08-15", "2026-08-12", "2026-08-09"]
        assert "머리글" in r.detail and "2열" in r.detail

    def test_머리글_공백은_정규화해_맞춘다(self, page):
        page.set_content(TABLE)
        r = collect_item_texts(page, "금액", hint("금액"))
        assert r.status == "ok"
        assert r.texts == ["12,000원", "3,000원", "500원"]

    def test_열_개수도_센다(self, page):
        page.set_content(TABLE)
        r = count_items(page, "금액", hint("금액"))
        assert r.status == "ok" and r.count == 3

    def test_같은_머리글이_두_표에_있으면_ambiguous(self, page):
        page.set_content(TABLE + TABLE)
        r = collect_item_texts(page, "주문일", hint("주문일"))
        assert r.status == "ambiguous"

    def test_행머리_셀은_같은_행의_값을_돌려준다(self, page):
        """tfoot 의 <th>합계</th><td>15,500원</td> — 열이 아니라 행이다."""
        page.set_content(TABLE)
        r = collect_item_texts(page, "합계", hint("합계"))
        assert r.status == "ok"
        assert r.texts == ["15,500원"]
        assert "행머리" in r.detail

    def test_없는_머리글은_absent(self, page):
        page.set_content(TABLE)
        r = collect_item_texts(page, "상품명", hint("상품명"))
        assert r.status == "absent"

    def test_부분_일치는_쓰지_않는다(self, page):
        page.set_content(TABLE)
        r = collect_item_texts(page, "주문", hint("주문"))
        assert r.status == "absent"


class TestLabelPathFirst:
    def test_라벨이_있으면_표_경로를_타지_않는다(self, page):
        """aria-label 과 표 머리글이 둘 다 있을 때 라벨 경로가 이긴다 — 기존 화면의
        판정 근거가 바뀌지 않는다."""
        page.set_content(
            '<div><span aria-label="주문일">X</span></div>' + TABLE
        )
        r = collect_item_texts(page, "주문일", hint("주문일"))
        assert r.status == "ok"
        assert r.texts == ["X"]
        assert "머리글" not in r.detail
