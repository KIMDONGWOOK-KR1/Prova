"""표 칸에 적힌 라벨로 입력란을 찾는다 — 그래도 접근성 지적은 남긴다 (2026-09-23).

parabank 회원가입은 `<td><b>First Name:</b></td><td><input></td>` 모양이다. 글자는
보이지만 입력란과 `<label for>` 로 이어져 있지 않아 1차 경로가 11칸 중 하나도 못 찾았다
(12건 '요소 미탐지'). 레거시·기업 화면에 흔한 모양이다.

- 같은 표 행에서 라벨 칸 **바로 다음 칸**의 입력란을 쓴다. 끝의 `:`·`*` 는 무시한다.
- 정확히 하나일 때만 확정한다 — 두 곳에 같은 라벨이 있으면 모호하다.
- '라벨로 요소 찾기' 검사는 이 경로를 '찾을 수 있음' 으로 치지 않는다. 도구가 조작할 수
  있게 된 것과 스크린리더가 읽을 수 있는 것은 다른 문제다.
"""

from __future__ import annotations

import pytest

from prova.models import UIElement
from prova.s3_grounder.dom_locator import (
    GroundingError,
    check_findable,
    ground,
    resolve_locator,
)

FORM = """
<form>
<table>
  <tr><td><b>First Name:</b></td><td><input id="fn"></td></tr>
  <tr><td><b>Zip Code*</b></td><td><input id="zip"></td></tr>
  <tr><td><b>Confirm:</b></td><td><input type="password" id="cf"></td></tr>
</table>
</form>"""


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        yield pg
        browser.close()


def field(label):
    return UIElement(element_id=label.lower().replace(" ", "_"), type="input", label=label)


def test_라벨_칸_다음_칸의_입력란을_찾아_입력한다(page):
    page.set_content(FORM)
    loc = ground(page, "First Name", field("First Name"))
    assert loc.strategy == "table_label"
    resolve_locator(page, loc, field("First Name")).fill("Prova")
    assert page.input_value("#fn") == "Prova"


@pytest.mark.parametrize("label,target_id", [("Zip Code", "zip"), ("Confirm", "cf")])
def test_콜론과_별표는_무시한다(page, label, target_id):
    page.set_content(FORM)
    loc = ground(page, label, field(label))
    resolve_locator(page, loc, field(label)).fill("x")
    assert page.input_value(f"#{target_id}") == "x"


def test_같은_라벨이_두_곳이면_모호하다(page):
    page.set_content(FORM + "<table><tr><td>First Name:</td><td><input></td></tr></table>")
    with pytest.raises(GroundingError):
        ground(page, "First Name", field("First Name"))


def test_label_for_가_있으면_그쪽이_먼저다(page):
    page.set_content('<table><tr><td><label for="a">Email</label></td>'
                     '<td><input id="a"></td></tr></table>')
    assert ground(page, "Email", field("Email")).strategy == "label"


def test_라벨_검사는_여전히_연결되지_않았다고_말한다(page):
    page.set_content(FORM)
    result = check_findable(page, [field("First Name")], ["First Name"])
    assert "연결되지 않았습니다" in result["First Name"]
    assert "표" in result["First Name"]


def test_같은_사유는_한_번만_말한다():
    """parabank 에서 11개 라벨이 같은 문장을 11번 반복해 사유를 읽을 수 없었다."""
    from prova.models import Expectation
    from prova.s5_verifier.assertion_engine import PageState, _judge_labels_findable

    reason = "라벨이 요소와 연결되지 않았습니다 — 같은 표 행의 글자로만 찾았습니다"
    state = PageState(url="u", text="", findable={"A": reason, "B": reason, "C": "일치하는 요소가 없음"})
    ok, text = _judge_labels_findable(Expectation(type="labels_findable", labels=["A", "B", "C"]), state)
    assert not ok
    assert text.count(reason) == 1
    assert "'A', 'B'" in text and "'C'" in text
