"""표를 칸 위치로 읽는다 — colspan·rowspan 이 있어도 제 열을 본다.

2026-09-30 까지 열 위치를 '머리글 줄 안에서 몇 번째 칸인가' 로 셌고, 본문도 행의
n번째 칸을 읽었다. 앞 칸에 colspan·rowspan 이 있으면 **오류 없이 엉뚱한 열을 읽었다**:

    <th colspan=2>상품</th><th>금액</th>        '금액' 이 상품명을 읽음
    두 줄 머리글의 아래 칸(앞에 rowspan)          '수량' 이 단가를 읽음
    <td colspan=N>주문이 없습니다</td>            0건 표를 1건으로 셈 → 0건 기대 오탐

정한 규칙:
- 머리글·본문 모두 colspan·rowspan 을 반영한 칸 위치로 짝짓는다.
- 한 칸짜리 본문 행(표 폭이 2칸 이상일 때)은 안내 행이다 — 값도 건수도 아니다.
- 대상 열의 본문 칸이 여러 칸·여러 행에 걸치면 짝을 정할 수 없다 — 짐작하지 않고
  absent 로 둔다(시끄러운 실패).
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
        yield browser.new_page()
        browser.close()


def hint(label: str, type_: str = "text") -> UIElement:
    return UIElement(element_id="x", type=type_, label=label)


COLSPAN_BEFORE = """
<table><thead><tr><th colspan="2">상품</th><th>금액</th></tr></thead>
<tbody><tr><td>A</td><td>셔츠</td><td>1000</td></tr>
<tr><td>B</td><td>바지</td><td>2000</td></tr></tbody></table>"""

TWO_ROW_HEAD = """
<table><thead>
<tr><th rowspan="2">주문일</th><th colspan="2">금액</th></tr>
<tr><th>단가</th><th>수량</th></tr></thead>
<tbody><tr><td>2026-09-01</td><td>500</td><td>3</td></tr>
<tr><td>2026-09-02</td><td>700</td><td>1</td></tr></tbody></table>"""

EMPTY_NOTICE = """
<table><caption>주문 목록</caption>
<thead><tr><th>주문일</th><th>금액</th></tr></thead>
<tbody><tr><td colspan="2">주문이 없습니다</td></tr></tbody></table>"""

EMPTY_NOTICE_NO_COLSPAN = """
<table><caption>주문 목록</caption>
<thead><tr><th>주문일</th><th>금액</th></tr></thead>
<tbody><tr><td>주문이 없습니다</td></tr></tbody></table>"""

GROUPED_ROWS = """
<table><thead><tr><th>주문일</th><th>상품</th></tr></thead>
<tbody><tr><td rowspan="2">2026-09-01</td><td>셔츠</td></tr>
<tr><td>바지</td></tr></tbody></table>"""


class TestColumnPosition:
    def test_앞_칸의_colspan_을_건너뛴다(self, page):
        page.set_content(COLSPAN_BEFORE)
        r = collect_item_texts(page, "금액", hint("금액"))
        assert r.status == "ok"
        assert r.texts == ["1000", "2000"]
        assert "3열" in r.detail

    def test_두_줄_머리글의_아래_칸(self, page):
        page.set_content(TWO_ROW_HEAD)
        assert collect_item_texts(page, "수량", hint("수량")).texts == ["3", "1"]
        assert collect_item_texts(page, "단가", hint("단가")).texts == ["500", "700"]

    def test_rowspan_머리글_자체도_제_열이다(self, page):
        page.set_content(TWO_ROW_HEAD)
        r = collect_item_texts(page, "주문일", hint("주문일"))
        assert r.texts == ["2026-09-01", "2026-09-02"]

    def test_여러_열에_걸친_그룹_머리글은_열을_정하지_않는다(self, page):
        page.set_content(TWO_ROW_HEAD)
        r = collect_item_texts(page, "금액", hint("금액"))
        assert r.status == "absent"
        assert "colspan" in r.detail


class TestNoticeRow:
    def test_안내_행은_열_값이_아니다(self, page):
        page.set_content(EMPTY_NOTICE)
        r = count_items(page, "주문일", hint("주문일"))
        assert r.status == "ok" and r.count == 0

    def test_안내_행은_표의_건수가_아니다(self, page):
        page.set_content(EMPTY_NOTICE)
        r = count_items(page, "주문 목록", hint("주문 목록", "list"))
        assert r.status == "ok" and r.count == 0

    def test_colspan_없는_한_칸_안내_행도_같다(self, page):
        page.set_content(EMPTY_NOTICE_NO_COLSPAN)
        assert count_items(page, "주문 목록", hint("주문 목록", "list")).count == 0
        assert count_items(page, "금액", hint("금액")).count == 0

    def test_한_열짜리_표의_행은_안내_행이_아니다(self, page):
        page.set_content("<table><caption>목록</caption><thead><tr><th>이름</th></tr></thead>"
                         "<tbody><tr><td>가</td></tr><tr><td>나</td></tr></tbody></table>")
        assert count_items(page, "목록", hint("목록", "list")).count == 2
        assert collect_item_texts(page, "이름", hint("이름")).texts == ["가", "나"]


class TestCannotPair:
    def test_대상_열이_여러_행에_걸치면_짐작하지_않는다(self, page):
        page.set_content(GROUPED_ROWS)
        r = collect_item_texts(page, "주문일", hint("주문일"))
        assert r.status == "absent"
        assert "rowspan" in r.detail

    def test_다른_열의_rowspan_은_대상_열을_막지_않는다(self, page):
        page.set_content(GROUPED_ROWS)
        assert collect_item_texts(page, "상품", hint("상품")).texts == ["셔츠", "바지"]
