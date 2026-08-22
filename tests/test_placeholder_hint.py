"""라벨과 안내 문구가 다른 입력란 — placeholder 힌트로 찾은 요소를 다시 살릴 수 있어야 한다.

## 2026-08-22 에 잡은 구멍

`_try_strategies` 는 `hint.placeholder` 로 요소를 찾는 후보를 끼워 넣는다. 기획서가
라벨('이메일')과 안내 문구('이메일을 입력하세요')를 따로 적어 둔 경우를 위한
분기다. 그런데 기록은 전략 이름 `placeholder` + **라벨**로 남겼고, `resolve_locator`
는 그 이름을 보고 라벨로 다시 찾았다 — 0개. fill 이 timeout 으로 죽고 `input_error`
"요소를 찾았으나 조작 불가" 가 된다. **탐지는 성공으로 남기고 실행은 구현 결함처럼
보고하는** 모양이다. 이 분기가 존재하는 이유인 '라벨 ≠ 안내 문구' 상황에서는
한 번도 동작한 적이 없었다.
"""

from __future__ import annotations

import pytest

from prova.models import UIElement
from prova.s3_grounder.dom_locator import ground, resolve_locator, strategy_label


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        yield pg
        browser.close()


HINT = UIElement(element_id="email", type="input", label="이메일",
                 placeholder="이메일을 입력하세요")


class TestPlaceholderHint:
    def test_안내_문구로만_찾을_수_있는_입력란을_찾고_다시_살린다(self, page):
        page.set_content('<input placeholder="이메일을 입력하세요">')
        loc = ground(page, "이메일", HINT)
        assert loc.strategy == "placeholder_hint"
        assert "이메일을 입력하세요" in loc.selector, "기록은 실제로 쓴 값을 담아야 한다"

        again = resolve_locator(page, loc, HINT)
        assert again.count() == 1
        again.fill("a@b.com")
        assert page.input_value("input") == "a@b.com"

    def test_리포트_표기가_있다(self):
        assert strategy_label("placeholder_hint") != "placeholder_hint"

    def test_라벨로_찾히면_라벨_전략이_우선이다(self, page):
        page.set_content('<label>이메일 <input placeholder="이메일을 입력하세요"></label>')
        loc = ground(page, "이메일", HINT)
        assert loc.strategy == "label"


class TestReadOptionsCustomWidget:
    """`read_options` 는 못 읽으면 None, 항목 없음이면 [] 이어야 한다 (docstring 계약).
    `locator("option")` 은 네이티브 <select> 에만 있으므로 커스텀 combobox 는 예외
    없이 [] 가 되어 '기획서 항목 전부 없음' 오탐 FAIL 이 났다 (2026-08-22)."""

    def test_네이티브_select_는_항목을_읽는다(self, page):
        from prova.s3_grounder.dom_locator import read_options
        page.set_content('<label>가입 경로 <select><option>검색</option><option>광고</option></select></label>')
        hint = UIElement(element_id="src", type="select", label="가입 경로")
        assert read_options(page, "가입 경로", hint) == ["검색", "광고"]

    def test_커스텀_combobox_는_None_이다(self, page):
        from prova.s3_grounder.dom_locator import read_options
        page.set_content('<div role="combobox" aria-label="가입 경로">검색</div>')
        hint = UIElement(element_id="src", type="select", label="가입 경로")
        assert read_options(page, "가입 경로", hint) is None

    def test_항목이_없는_select_는_빈_목록이다(self, page):
        from prova.s3_grounder.dom_locator import read_options
        page.set_content('<label>가입 경로 <select></select></label>')
        hint = UIElement(element_id="src", type="select", label="가입 경로")
        assert read_options(page, "가입 경로", hint) == []
