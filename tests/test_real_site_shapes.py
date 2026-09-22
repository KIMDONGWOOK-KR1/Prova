"""우리가 안 만든 웹앱에서 드러난 탐지 결함을 마크업으로 재현한다 (2026-09-23).

공개 연습 사이트 세 곳에 실물 7B 로 돌렸더니 실패가 전부 '기획서와 다름' 으로
떴는데, 사이트는 멀쩡했다. 원인은 둘 다 탐지 쪽이었다. 외부 사이트는 바뀔 수
있으므로 모양만 떼어 여기 고정한다.

1. saucedemo — `<form aria-label="Login">` 안에 `<input type="submit" value="Login">`.
   label 전략이 먼저 돌아 **폼**을 잡았고, 폼을 눌러도 제출이 안 돼 필수·시나리오
   케이스가 전부 '구현이 규칙을 강제하지 않는다' 로 FAIL 했다. 버튼·링크에는
   <label>·placeholder 가 없다 — role 로 먼저 찾는다.
2. the-internet — `<button><i class="fa ..."> Login</i></button>`. Font Awesome 의
   ::before 글리프(사설 영역 문자 U+F090)가 접근성 이름 앞에 붙어 `"\\uf090 Login"`
   이 된다. 정확 일치 role 조회가 0 개라 '기획서의 유형(버튼)과 구현이 다르다' 로
   판정했다 — 버튼인데. 아이콘 글자와 앞뒤 공백은 이름 비교에서 뺀다.
"""

from __future__ import annotations

import pytest

from prova.models import UIElement
from prova.s3_grounder.dom_locator import ground, resolve_locator


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        yield pg
        browser.close()


def button(label="Login"):
    return UIElement(element_id="login_btn", type="button", label=label)


SAUCE = """
<form aria-label="Login" onsubmit="event.preventDefault(); document.title='submitted'">
  <input aria-label="Username" placeholder="Username">
  <input type="submit" value="Login">
</form>"""

ICON = """
<style>i.fa::before { content: "\\f090"; }</style>
<form onsubmit="event.preventDefault(); document.title='submitted'">
  <button type="submit"><i class="fa"> Login</i></button>
</form>"""


class TestButtonInsideNamedForm:
    def test_버튼은_폼이_아니라_버튼을_잡는다(self, page):
        page.set_content(SAUCE)
        loc = ground(page, "Login", button())
        assert loc.strategy == "role"
        target = resolve_locator(page, loc, button())
        assert target.evaluate("e => e.tagName") == "INPUT"

    def test_누르면_제출된다(self, page):
        page.set_content(SAUCE)
        resolve_locator(page, ground(page, "Login", button()), button()).click()
        assert page.title() == "submitted"


class TestIconGlyphInName:
    def test_아이콘_글자가_붙어도_버튼으로_찾는다(self, page):
        page.set_content(ICON)
        loc = ground(page, "Login", button())   # SpecTypeMismatch 가 나면 안 된다
        assert loc.strategy == "role"
        resolve_locator(page, loc, button()).click()
        assert page.title() == "submitted"

    def test_진짜_유형_불일치는_여전히_잡는다(self, page):
        """느슨하게 만든 것이 버튼 아닌 것을 버튼으로 받아 주면 안 된다."""
        from prova.s3_grounder.dom_locator import SpecTypeMismatch

        page.set_content('<span onclick="1"><i class="fa"> Login</i></span>'
                         '<style>i.fa::before { content: "\\f090"; }</style>')
        with pytest.raises(SpecTypeMismatch):
            ground(page, "Login", button())

    def test_다른_이름은_여전히_다르다(self, page):
        """글리프만 빼는 것이지 부분 일치가 아니다 — 'Login now' 는 'Login' 이 아니다."""
        from prova.s3_grounder.dom_locator import GroundingError, SpecTypeMismatch

        page.set_content('<button>Login now</button>')
        with pytest.raises((GroundingError, SpecTypeMismatch)):
            ground(page, "Login", button())
