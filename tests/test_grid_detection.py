"""ARIA 격자(div role=grid) 탐지 — React 데이터 그리드 모양의 표를 읽는다.

MUI·AG Grid 같은 데이터 그리드는 <table> 이 아니라 div 에 role 을 붙인다
(grid > row > columnheader / gridcell). 2026-09-30 까지 이 모양은 '찾을 수 없음' 으로
끝나, 목록 건수·정렬·날짜 필터 검증이 이런 화면에서 통째로 돌지 않았다.

## 계약 (표 경로와 같다)

- 라벨 경로·caption·<th> 가 모두 0개일 때만 내려온다.
- 이름·머리글은 정확 일치. 후보가 둘 이상이면 ambiguous.
- 머리글 행·안내 행('주문이 없습니다' 한 칸)은 항목이 아니다.
- 열은 aria-colindex 가 있으면 그것으로 짝짓는다(열 가상화). 없으면 칸 순서.
- **일부 행만 그려진 격자는 세지도 읽지도 않는다.** 데이터 그리드는 보이는 행만
  그린다(가상화). aria-rowcount 가 그려진 행 수와 다르거나 -1 이면, 그리지 않은
  행을 0 으로 세어 '20건이어야 하는데 12건' 같은 오탐을 낸다.
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


def grid(rows: list[tuple[str, str, str]], *, name: str = "주문 목록",
         rowcount: str | None = "auto", header_cols=(1, 2, 3)) -> str:
    heads = {1: "주문번호", 2: "주문일", 3: "금액"}
    rc = len(rows) + 1 if rowcount == "auto" else rowcount
    rc_attr = f' aria-rowcount="{rc}"' if rc is not None else ""
    head = "".join(f'<div role="columnheader" aria-colindex="{i}">{heads[i]}</div>'
                   for i in header_cols)
    body = "".join(
        '<div role="row">' + "".join(
            f'<div role="gridcell" aria-colindex="{i + 1}">{v}</div>' for i, v in enumerate(r))
        + "</div>" for r in rows)
    return (f'<div role="grid" aria-label="{name}"{rc_attr}>'
            f'<div role="rowgroup"><div role="row">{head}</div></div>'
            f'<div role="rowgroup">{body}</div></div>')


ROWS = [("A1", "2026-08-15", "12,000원"), ("A2", "2026-08-12", "3,000원"),
        ("A3", "2026-08-09", "500원")]


class TestContainer:
    def test_이름으로_격자를_찾고_데이터_행을_센다(self, page):
        page.set_content(grid(ROWS))
        r = count_items(page, "주문 목록", hint("주문 목록", "list"))
        assert r.status == "ok" and r.count == 3     # 머리글 행은 세지 않는다
        assert "격자" in r.detail

    def test_안내_행은_세지_않는다(self, page):
        page.set_content(
            '<div role="grid" aria-label="주문 목록">'
            '<div role="row"><div role="columnheader">주문일</div>'
            '<div role="columnheader">금액</div></div>'
            '<div role="row"><div role="gridcell">주문이 없습니다</div></div></div>')
        assert count_items(page, "주문 목록", hint("주문 목록", "list")).count == 0

    def test_같은_이름의_격자가_둘이면_ambiguous(self, page):
        page.set_content(grid(ROWS) + grid(ROWS))
        assert count_items(page, "주문 목록", hint("주문 목록", "list")).status == "ambiguous"

    def test_aria_label_붙은_순수_table_도_닿는다(self, page):
        page.set_content(
            '<table aria-label="주문 목록"><thead><tr><th>주문일</th><th>금액</th></tr></thead>'
            '<tbody><tr><td>1</td><td>2</td></tr><tr><td>3</td><td>4</td></tr></tbody></table>')
        r = count_items(page, "주문 목록", hint("주문 목록", "list"))
        assert r.status == "ok" and r.count == 2

    def test_라벨_목록이_있으면_격자를_보지_않는다(self, page):
        page.set_content('<ul aria-label="주문 목록"><li>x</li></ul>'
                         + grid(ROWS, name="다른 목록"))
        assert count_items(page, "주문 목록", hint("주문 목록", "list")).count == 1


class TestColumn:
    def test_열_머리글로_값을_순서대로_모은다(self, page):
        page.set_content(grid(ROWS))
        r = collect_item_texts(page, "주문일", hint("주문일"))
        assert r.status == "ok"
        assert r.texts == ["2026-08-15", "2026-08-12", "2026-08-09"]
        assert "격자 머리글" in r.detail

    def test_열_가상화_aria_colindex_로_짝짓는다(self, page):
        """머리글 행이 1열을 그리지 않았어도(가상화) 3열은 3열이다."""
        page.set_content(grid(ROWS, header_cols=(2, 3)))
        assert collect_item_texts(page, "금액", hint("금액")).texts == [
            "12,000원", "3,000원", "500원"]

    def test_aria_colindex_없으면_칸_순서(self, page):
        page.set_content(
            '<div role="grid" aria-label="g"><div role="row">'
            '<div role="columnheader">이름</div><div role="columnheader">나이</div></div>'
            '<div role="row"><div role="gridcell">가</div><div role="gridcell">30</div></div>'
            '</div>')
        assert collect_item_texts(page, "나이", hint("나이")).texts == ["30"]

    def test_같은_머리글이_격자와_표에_있으면_ambiguous(self, page):
        page.set_content(grid(ROWS) + '<table><thead><tr><th>주문일</th></tr></thead>'
                         '<tbody><tr><td>x</td></tr></tbody></table>')
        assert collect_item_texts(page, "주문일", hint("주문일")).status == "ambiguous"

    def test_0건_격자의_열은_0개다(self, page):
        page.set_content(grid([]))
        r = count_items(page, "주문일", hint("주문일"))
        assert r.status == "ok" and r.count == 0


class TestVirtualized:
    def test_일부_행만_그려졌으면_세지_않는다(self, page):
        page.set_content(grid(ROWS, rowcount="50"))
        r = count_items(page, "주문 목록", hint("주문 목록", "list"))
        assert r.status == "absent"
        assert "일부 행만" in r.detail

    def test_일부_행만_그려졌으면_열도_읽지_않는다(self, page):
        page.set_content(grid(ROWS, rowcount="50"))
        r = collect_item_texts(page, "주문일", hint("주문일"))
        assert r.status == "absent" and "일부 행만" in r.detail

    def test_전체_행_수를_모르면_세지_않는다(self, page):
        page.set_content(grid(ROWS, rowcount="-1"))
        assert count_items(page, "주문 목록", hint("주문 목록", "list")).status == "absent"

    def test_불러오는_중인_격자는_0건이라_하지_않는다(self, page):
        """MUI 데모(2026-09-30): 스켈레톤 행을 그리는 동안 aria-rowcount=1, 데이터 행 0,
        aria-busy 도 없다. '0건' 으로 읽으면 0건 기대가 통과하고 N건 기대가 오탐 FAIL 한다."""
        skeleton = "".join('<div class="sk"><span style="display:inline-block;width:80px;'
                           'height:10px"></span></div>' for _ in range(5))
        page.set_content(grid([]) .replace('<div role="rowgroup"></div>',
                                           f'<div role="rowgroup">{skeleton}</div>'))
        r = count_items(page, "주문 목록", hint("주문 목록", "list"))
        assert r.status == "absent" and "불러오는 중" in r.detail
        assert collect_item_texts(page, "주문일", hint("주문일")).status == "absent"

    def test_빈_격자_안내_글자는_0건이다(self, page):
        page.set_content(grid([]).replace(
            '<div role="rowgroup"></div>',
            '<div role="rowgroup"><div style="height:40px">No rows</div></div>'))
        r = count_items(page, "주문 목록", hint("주문 목록", "list"))
        assert r.status == "ok" and r.count == 0

    def test_aria_rowcount_가_없으면_그려진_것을_센다(self, page):
        page.set_content(grid(ROWS, rowcount=None))
        assert count_items(page, "주문 목록", hint("주문 목록", "list")).count == 3
