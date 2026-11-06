"""라벨 안의 필수 표시·띄어쓰기 차이 — 2026-11-06 실물 사이트에서 잡은 오탐.

한국 사이트에 흔한 모양: `<label for="name">성명<i class="required">필수</i></label>`.
화면에는 빨간 점이나 별표로 보이지만 접근성 이름은 '성명 필수' 다. 도구는 기획서 라벨
'성명' 을 정확히 찾았고, 문의 폼의 입력란 8개를 전부 못 찾아 **기획서와 다름** 으로
보고했다(입력란은 다 있었다). 기획서의 '회사/기관명' 과 화면의 '회사 / 기관명' 처럼
띄어쓰기만 다른 것도 같았다.

## 지키는 것

- 정확한 라벨이 먼저다. 이 변형은 못 찾을 때만 본다.
- 앞뒤의 필수 표시 낱말('필수'·'(필수)'·'*'·'required')과 띄어쓰기만 무시한다 — 부분
  일치로 넓히지 않는다. '성명' 은 '성명 확인' 을 잡지 않는다.
- 조작은 여전히 정확히 하나일 때만 한다.
"""

from __future__ import annotations

import pytest

from prova.models import UIElement
from prova.s3_grounder.dom_locator import (
    GroundingError,
    check_findable,
    ground,
    label_variants,
    marked_variant,
    resolve_locator,
)


class TestMarkedVariant:
    @pytest.mark.parametrize("name", ["성명 필수", "성명필수", "(필수) 성명", "* 성명", "성명 *",
                                      "성명 required", "성 명"])
    def test_필수_표시와_띄어쓰기만_무시한다(self, name):
        assert marked_variant("성명").search(name)

    @pytest.mark.parametrize("name", ["성명 확인", "보호자 성명", "성명을 입력하세요"])
    def test_부분_일치로_넓히지_않는다(self, name):
        assert not marked_variant("성명").search(name)

    def test_띄어쓰기가_다른_라벨(self):
        assert marked_variant("회사/기관명").search("회사 / 기관명 필수")

    def test_끝의_역할_낱말과_영문_대소문자(self):
        """기획서 설명 'Top 버튼' ↔ 화면 'TOP'. 모델이 라벨에 역할 낱말을 붙였다."""
        assert marked_variant("Top 버튼").search("TOP")
        assert marked_variant("검색 링크").search("검색")
        assert not marked_variant("Top 버튼").search("Topic")

    def test_가운뎃점과_마침표는_띄어쓰기처럼(self):
        assert marked_variant("개인정보 수집·이용에 동의합니다").search(
            "(필수) 개인정보 수집 이용에 동의합니다.")

    def test_모양_변형_목록은_그대로다(self):
        """label_variants 의 '모양 없는 라벨은 빈 목록' 계약은 건드리지 않는다."""
        assert label_variants("성명") == []


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        yield pg
        browser.close()


_FORM = ('<label for="c">회사 / 기관명<i class="required">필수</i></label><input id="c">'
         '<label for="n">성명<i class="required">필수</i></label><input id="n">'
         '<label for="n2">성명 확인</label><input id="n2">')


class TestGround:
    def test_필수_표시가_붙은_라벨로_찾고_다시_살린다(self, page):
        page.set_content(_FORM)
        hint = UIElement(element_id="n", type="input", label="성명")
        loc = ground(page, "성명", hint)
        assert resolve_locator(page, loc, hint).get_attribute("id") == "n"

    def test_띄어쓰기만_다른_라벨로_찾는다(self, page):
        page.set_content(_FORM)
        hint = UIElement(element_id="c", type="input", label="회사/기관명")
        loc = ground(page, "회사/기관명", hint)
        assert resolve_locator(page, loc, hint).get_attribute("id") == "c"

    def test_정확한_라벨이_있으면_그것이_먼저다(self, page):
        page.set_content('<label for="a">성명</label><input id="a">'
                         '<label for="b">성명<i>필수</i></label><input id="b">')
        hint = UIElement(element_id="a", type="input", label="성명")
        assert resolve_locator(page, ground(page, "성명", hint), hint).get_attribute("id") == "a"

    def test_필수_표시를_빼도_여럿이면_고르지_않는다(self, page):
        page.set_content('<label for="a">성명 *</label><input id="a">'
                         '<label for="b">성명 필수</label><input id="b">')
        with pytest.raises(GroundingError):
            ground(page, "성명", UIElement(element_id="a", type="input", label="성명"))

    def test_라벨_확인도_있다로_본다(self, page):
        page.set_content(_FORM)
        assert check_findable(page, [], ["성명", "회사/기관명"]) == {"성명": "", "회사/기관명": ""}

    def test_없는_라벨은_여전히_없다(self, page):
        page.set_content(_FORM)
        assert check_findable(page, [], ["이메일"])["이메일"] != ""


def test_대소문자만_다른_이름은_기록에서_되살려도_같은_요소다(page):
    """찾을 때는 'Top'↔'TOP' 을 같다고 보고, 누를 때 0개가 되어 시간 초과가 났다 (2026-11-06).

    위치 기록에는 패턴 문자열만 남는다 — 대소문자 무시가 플래그에 있으면 되살릴 때 빠진다.
    """
    page.set_content('<button id="t">TOP</button>')
    hint = UIElement(element_id="top", type="button", label="Top 버튼")
    loc = ground(page, "Top 버튼", hint)
    again = resolve_locator(page, loc, hint)
    assert again.count() == 1 and again.get_attribute("id") == "t"
