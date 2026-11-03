"""기획서 라벨이 화면 이름의 '모양' 을 적은 경우: 토글(A / B)·틀({name})·괄호 설명.

## 2026-11-03 WebTestBench 2차 측정에서 잡은 구멍

GPT 가 쓴 기획서 6개에서 요소 못 찾음 166건 중 46건이 라벨의 모양 때문이었다.

- 상태에 따라 글자가 바뀌는 토글: `Save to favorites / Remove from favorites`, `Like / Liked` (26)
- 항목마다 이름이 들어가는 틀: `Remove {pet.name} from favorites` (15)
- 한국어 기획서가 영어 화면 이름에 붙인 설명: `Sort pets (접근성 이름)` (5)

기획서 기준으로 틀린 라벨이 아니다 — 사람이 읽으면 무엇을 가리키는지 안다. 그런데 도구는 글자
그대로 찾았고, 라벨 확인 케이스는 이것을 **기획서와 다름** 으로 보고했다(오탐).

## 지키는 것

- 정확한 라벨이 먼저다. 변형은 그것으로 못 찾을 때만 본다 — 지금 찾히는 요소의 판정은 그대로.
- **조작할 요소는 정확히 하나일 때만** 받는다. 카드마다 있는 `Remove {pet.name}` 처럼 여럿이면
  고르지 않는다 — 아무거나 누르면 그 뒤의 FAIL 이 결함인지 엉뚱한 요소를 눌러서인지 모른다.
- 라벨 확인(있는가)은 하나 이상이면 '있다' 다. 그 케이스가 묻는 것은 존재다.
"""

from __future__ import annotations

import pytest

from prova.models import UIElement
from prova.s3_grounder.dom_locator import (
    GroundingError,
    check_findable,
    ground,
    label_variants,
    resolve_locator,
)


class TestLabelVariants:
    def _match(self, target, name):
        return [p.pattern for p in label_variants(target) if p.search(name)]

    def test_토글은_양쪽_이름을_다_본다(self):
        assert self._match("Save to favorites / Remove from favorites", "Remove from favorites")
        assert self._match("Like / Liked", "Liked")
        assert not self._match("Like / Liked", "Unlike")

    def test_틀은_자리에_아무_글자나_받는다(self):
        assert self._match("Remove {pet.name} from favorites", "Remove Luna from favorites")
        assert not self._match("Remove {pet.name} from favorites", "Remove from favorites")

    def test_한글_괄호_설명을_뗀다(self):
        assert self._match("Sort pets (접근성 이름)", "Sort pets")

    def test_영어_괄호는_이름의_일부다(self):
        # 'Topics (3)' 같은 화면 글자는 설명이 아니다.
        assert label_variants("Price (USD)") == []

    def test_부분_일치로_넓히지_않는다(self):
        assert not self._match("Like / Liked", "Like this review")
        assert not self._match("Remove {pet.name} from favorites",
                               "Remove Luna from favorites now")

    def test_모양이_없는_라벨은_변형이_없다(self):
        assert label_variants("Email") == []
        # 슬래시가 띄어쓰기 없이 붙은 것은 토글이 아니라 이름이다 (예: 'and/or').
        assert label_variants("Read/Write") == []


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser.new_page()
        browser.close()


BTN = UIElement(element_id="fav", type="button", label="Save to favorites / Remove from favorites")


class TestGround:
    def test_토글의_지금_글자로_찾는다(self, page):
        page.set_content('<button>Remove from favorites</button>')
        loc = ground(page, BTN.label, BTN)
        assert resolve_locator(page, loc, BTN).inner_text() == "Remove from favorites"

    def test_틀로_찾고_다시_살린다(self, page):
        hint = UIElement(element_id="rm", type="button", label="Remove {pet.name} from favorites")
        page.set_content('<button>Remove Luna from favorites</button>')
        loc = ground(page, hint.label, hint)
        assert resolve_locator(page, loc, hint).count() == 1

    def test_괄호_설명을_떼고_라벨로_찾는다(self, page):
        hint = UIElement(element_id="q", type="input", label="Search pets (접근성 이름)")
        page.set_content('<label for="q">Search pets</label><input id="q">')
        loc = ground(page, hint.label, hint)
        resolve_locator(page, loc, hint).fill("dog")
        assert page.locator("#q").input_value() == "dog"

    def test_여럿이_맞으면_고르지_않는다(self, page):
        hint = UIElement(element_id="rm", type="button", label="Remove {pet.name} from favorites")
        page.set_content('<button>Remove Luna from favorites</button>'
                         '<button>Remove Milo from favorites</button>')
        with pytest.raises(GroundingError):
            ground(page, hint.label, hint)

    def test_토글_양쪽이_다_보이면_고르지_않는다(self, page):
        page.set_content('<button>Save to favorites</button><button>Remove from favorites</button>')
        with pytest.raises(GroundingError):
            ground(page, BTN.label, BTN)

    def test_정확한_라벨이_있으면_그것이_먼저다(self, page):
        hint = UIElement(element_id="x", type="button", label="Like / Liked")
        page.set_content('<button>Like / Liked</button><button>Liked</button>')
        loc = ground(page, hint.label, hint)
        assert resolve_locator(page, loc, hint).inner_text() == "Like / Liked"

    def test_기획서_유형_대조도_변형_이름으로_한다(self, page):
        # 변형으로 버튼을 찾았는데 유형 대조가 원래 글자로 role 을 찾으면 0개 → '유형 불일치' 오탐.
        page.set_content('<button>Liked</button>')
        hint = UIElement(element_id="x", type="button", label="Like / Liked")
        ground(page, hint.label, hint)  # SpecTypeMismatch 가 나면 실패


class TestFindable:
    def test_틀은_여럿이어도_있다(self, page):
        hint = UIElement(element_id="rm", type="button", label="Remove {pet.name} from favorites")
        page.set_content('<button>Remove Luna from favorites</button>'
                         '<button>Remove Milo from favorites</button>')
        assert check_findable(page, [hint], [hint.label]) == {hint.label: ""}

    def test_어느_모양으로도_없으면_없다(self, page):
        page.set_content('<button>Add</button>')
        result = check_findable(page, [BTN], [BTN.label])
        assert result[BTN.label] != ""
