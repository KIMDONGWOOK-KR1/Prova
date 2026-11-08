"""라벨 확인은 기획서의 안내 문구(placeholder)로 찾은 것을 '라벨이 있다' 로 세지 않는다.

조작할 때는 기획서의 안내 문구로 칸을 찾아도 된다(placeholder_hint). 그런데 라벨 확인이
같은 길로 찾으면, 기획서의 라벨이 화면에 없어도 통과한다. 변이 시험(2026-11-07)에서
saucedemo 의 라벨을 바꾼 기획서가 라벨 확인을 통과했고, 계획 화면에서 사람이 라벨을 잘못
고친 문서도 통과했다(2026-11-08).
"""

from __future__ import annotations

import pytest

from prova.models import UIElement
from prova.s3_grounder.dom_locator import check_findable, ground


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        yield pg
        browser.close()


def _email(label: str) -> UIElement:
    return UIElement(element_id="email", type="input", label=label,
                     placeholder="이메일을 입력하세요")


def test_조작은_여전히_안내_문구로_찾는다(page):
    page.set_content('<label for="e">이메일</label><input id="e" placeholder="이메일을 입력하세요">')
    assert ground(page, "전자우편", _email("전자우편")).strategy == "placeholder_hint"


def test_화면에_없는_라벨은_안내_문구가_맞아도_없다고_본다(page):
    page.set_content('<label for="e">이메일</label><input id="e" placeholder="이메일을 입력하세요">')
    result = check_findable(page, [_email("전자우편")], ["전자우편"])
    assert result["전자우편"] != ""


def test_화면의_라벨은_그대로_있다고_본다(page):
    page.set_content('<label for="e">이메일</label><input id="e" placeholder="이메일을 입력하세요">')
    assert check_findable(page, [_email("이메일")], ["이메일"]) == {"이메일": ""}


def test_연결_없이_정의_목록으로_적힌_라벨은_전과_같이_있다고_본다(page):
    """안내 문구로 먼저 찾히던 화면 — 라벨 글자는 화면에 있다. 판정이 바뀌면 오탐이다."""
    page.set_content('<dl><dt>이메일</dt><dd><input placeholder="이메일을 입력하세요"></dd></dl>')
    assert check_findable(page, [_email("이메일")], ["이메일"]) == {"이메일": ""}
