"""collect_item_texts 테스트 — 반복 요소 경로에서 값을 읽는다.

## 왜 count_items 옆에 두는가

count_items 는 '몇 개인가' 만 본다. Phase B 의 정렬·합계 판정은 '무엇이 몇 번째에
있는가' 를 봐야 하므로 개수로는 부족하다 — 그래서 같은 탐색(라벨로 컨테이너를
찾고 항목 role 로 항목을 센다)에 값 수집을 얹는다.

탐색 로직은 count_items 와 똑같아야 한다. 라벨이 없거나 컨테이너가 여러 개인
상황에서 두 함수가 다른 판정을 내리면 '어디를 봤는가' 가 갈려서 결과를
신뢰할 수 없다. 그래서 이 테스트는 count_items 의 absent/ambiguous 시나리오를
그대로 거울처럼 확인한다.

## page 픽스처를 test_spec_type_conformance.py 에서 그대로 가져온 이유

이 저장소에서 dom_locator 의 함수를 실제 브라우저 페이지로 직접 검증하는 유일한
방식이다(다른 count 관련 테스트는 test_search_e2e.py 의 파이프라인 관통 테스트라
정적 HTML 을 직접 넣어 보는 이 픽스처가 필요하다).
"""

from __future__ import annotations

import pytest

from prova.models import UIElement
from prova.s3_grounder.dom_locator import CollectionTexts, collect_item_texts


@pytest.fixture(scope="module")
def page():
    """빈 페이지 하나. 테스트마다 set_content 로 마크업을 바꿔 쓴다."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        yield pg
        browser.close()


def list_hint(label: str = "주문일") -> UIElement:
    return UIElement(element_id="order_dates", type="list", label=label)


class TestOk:
    def test_문서_순서대로_텍스트를_담는다(self, page):
        page.set_content(
            '<ul aria-label="주문일">'
            "<li>2026-08-15</li>"
            "<li>2026-08-12</li>"
            "<li>2026-08-09</li>"
            "</ul>"
        )
        result = collect_item_texts(page, "주문일", list_hint())
        assert result.status == "ok"
        assert result.texts == ["2026-08-15", "2026-08-12", "2026-08-09"]

    def test_공백이_정리된다(self, page):
        """count_items 와 같은 정규화(normalize_ws)를 쓴다 — 리포트에서 다른
        경로로 읽은 같은 값이 서로 다르게 보이면 비교가 어긋난다."""
        page.set_content(
            '<ul aria-label="주문일">'
            "<li>  2026-08-15  \n</li>"
            "</ul>"
        )
        result = collect_item_texts(page, "주문일", list_hint())
        assert result.status == "ok"
        assert result.texts == ["2026-08-15"]


class TestAbsent:
    def test_라벨이_없으면_absent(self, page):
        page.set_content("<div>다른 내용</div>")
        result = collect_item_texts(page, "주문일", list_hint())
        assert result.status == "absent"
        assert result.texts == []
        assert result.detail


class TestAmbiguous:
    def test_같은_라벨의_목록이_여러_개면_ambiguous(self, page):
        """count_items 와 같은 계약 — 컨테이너는 정확히 1개여야 한다. 어느
        목록의 값을 모을지 모르는 상태에서 아무거나 고르면 결과를 신뢰할 수
        없다."""
        page.set_content(
            '<ul aria-label="주문일"><li>2026-08-15</li></ul>'
            '<ul aria-label="주문일"><li>2026-08-12</li></ul>'
        )
        result = collect_item_texts(page, "주문일", list_hint())
        assert result.status == "ambiguous"
        assert result.texts == []
        assert result.detail


class TestConstruction:
    def test_세_인자만으로_만들_수_있다(self):
        """판정 쪽(assertion_engine)이 target 없이 만들어 쓴다 — 필수로 만들면
        그쪽이 깨진다."""
        ct = CollectionTexts(status="ok", texts=["a"], detail="")
        assert ct.target == ""
