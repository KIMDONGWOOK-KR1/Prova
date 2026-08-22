"""2차 경로 — 접근성 속성으로 못 찾은 요소를 화면 이미지로 찾는다.

## 무엇을 확인하고 무엇을 확인하지 않는가

확인하는 것: **배관.** 탐지가 실패했을 때 스크린샷을 찍고, 위치를 받고, 그 좌표를
눌러서, 케이스가 끝까지 진행되고 판정이 나오는가.

확인하지 않는 것: **VLM 의 정확도.** MockVLM 은 정답을 안다(CSS selector 로 실측한다).
실제 모델이 아이콘만 있는 버튼을 '검색' 으로 알아보는지는 전혀 다른 문제이고, 실물
모델로 따로 측정해야 한다. 이 구분을 흐리면 mock 초록불을 보고 '2차가 동작한다' 고
말하게 되고, 정작 실물 모델이 요소를 못 찾을 때 그 사실이 어디서도 드러나지 않는다.

## 시험 대상 화면

`/nolabel/search` 는 검증 로직이 good 과 완전히 같고 제출 버튼만 아이콘이다.
기획서는 그 요소의 라벨을 '검색' 으로 적었는데 화면에 그 글자가 없어서 S3 의 네 전략이
모두 막힌다 — 실물 화면에서 흔한 모양이다.

## 가장 중요한 성질: 보정이 사실을 지우지 않는다

보정을 켜면 케이스가 통과한다. 그런데 '기획서의 라벨로 요소를 지목할 수 없다' 는 것은
그 자체로 기획-구현 불일치이면서 접근성 결함이다. 그 사실이 리포트에서 사라지면 보정은
검증을 약화시킨 것이 된다.

그래서 라벨 탐지 케이스는 보정 여부와 무관하게 FAIL 로 남아야 한다. 이 파일의 마지막
클래스가 그것을 못 박는다.
"""

from __future__ import annotations

import pytest

from prova.models import UIElement
from prova.s3_grounder.dom_locator import (
    GroundingError,
    MIN_CONFIDENCE,
    bbox_center,
    ground,
    heal_with_vlm,
)
from prova.vlm.base import Located
from prova.vlm.mock_backend import MockVLM

SEARCH_BTN = UIElement(element_id="search_btn", type="button", label="검색")


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1280, "height": 800})
        yield pg
        browser.close()


class TestSelectorPathStillFirst:
    """접근성 속성이 통하면 그걸 쓴다. 이미지 추론은 느리고 좌표는 쉽게 낡는다."""

    def test_good에서는_selector로_찾는다(self, page, sut_base):
        page.goto(f"{sut_base}/good/search")
        assert ground(page, "검색", SEARCH_BTN).strategy == "role"

    def test_nolabel에서는_selector가_막힌다(self, page, sut_base):
        """이 전제가 깨지면 아래 보정 테스트들이 아무것도 확인하지 않는다."""
        page.goto(f"{sut_base}/nolabel/search")
        with pytest.raises(GroundingError):
            ground(page, "검색", SEARCH_BTN)


class TestHealing:
    def test_이미지로_찾으면_좌표를_돌려준다(self, page, sut_base):
        page.goto(f"{sut_base}/nolabel/search")
        vlm = MockVLM(page=page)
        vlm.register_selector("검색", "button[type=submit]")

        location = heal_with_vlm(page, "검색", vlm, SEARCH_BTN)
        assert location.method == "vlm"
        assert location.healed is True
        assert location.selector is None, "보정된 요소에는 selector 가 없다"
        assert len(location.bbox) == 4

    def test_좌표가_실제_버튼_위에_있다(self, page, sut_base):
        """중심 좌표가 버튼 밖이면 눌러도 아무 일이 없거나 엉뚱한 것이 눌린다."""
        page.goto(f"{sut_base}/nolabel/search")
        vlm = MockVLM(page=page)
        vlm.register_selector("검색", "button[type=submit]")

        x, y = bbox_center(heal_with_vlm(page, "검색", vlm, SEARCH_BTN))
        box = page.locator("button[type=submit]").bounding_box()
        assert box["x"] <= x <= box["x"] + box["width"]
        assert box["y"] <= y <= box["y"] + box["height"]

    def test_신뢰도가_낮으면_보정하지_않는다(self, page, sut_base):
        """VLM 은 못 찾았을 때도 그럴듯한 좌표를 낸다. 그 좌표를 누르면 엉뚱한 곳을
        눌러 놓고 케이스를 진행하게 되고, FAIL 이 구현 결함인지 잘못 누른 것인지
        구분할 수 없다."""
        page.goto(f"{sut_base}/nolabel/search")
        vlm = MockVLM()
        vlm.register("검색", (0.1, 0.1, 0.2, 0.2), confidence=MIN_CONFIDENCE - 0.01)
        with pytest.raises(GroundingError):
            heal_with_vlm(page, "검색", vlm, SEARCH_BTN)

    def test_좌표가_화면_밖이면_보정하지_않는다(self, page, sut_base):
        page.goto(f"{sut_base}/nolabel/search")
        vlm = MockVLM()
        vlm.register("검색", (0.5, 0.5, 1.8, 1.9))
        with pytest.raises(GroundingError):
            heal_with_vlm(page, "검색", vlm, SEARCH_BTN)

    def test_좌표가_뒤집혀_있으면_보정하지_않는다(self, page, sut_base):
        """모델이 x2 < x1 로 내는 일이 실제로 있다. 그대로 쓰면 Playwright 가
        화면 밖을 눌러 '클릭 실패' 로 기록되고 원인이 흐려진다."""
        page.goto(f"{sut_base}/nolabel/search")
        vlm = MockVLM()
        vlm.register("검색", (0.8, 0.8, 0.2, 0.2))
        with pytest.raises(GroundingError):
            heal_with_vlm(page, "검색", vlm, SEARCH_BTN)

    def test_VLM_호출이_실패하면_탐지_실패로_남는다(self, page, sut_base):
        """보정 실패를 새 실패 유형으로 만들지 않는다 — 호출자에게 필요한 사실은
        '요소를 확정하지 못했다' 하나이고 그 처리는 이미 있다."""
        page.goto(f"{sut_base}/nolabel/search")
        with pytest.raises(GroundingError):
            heal_with_vlm(page, "검색", MockVLM(), SEARCH_BTN)


class TestHealFailureReason:
    """보정 실패의 **사유**가 남아야 한다 (2026-08-22).

    스크린샷 실패·VL 서버 오류·신뢰도 미달·좌표 비정상이 전부 `vlm=0개` 로
    접혀 "일치하는 요소가 없음" 으로 찍혔다. 실행 중 VL 서버가 죽어도 리포트는
    "요소를 못 찾았다" 고 말했다 — 도구 오류가 탐지 실패로 둔갑한다. 그리고
    1차 경로의 진단("후보 2개")도 2차 예외로 덮여 사라졌다.
    """

    def test_서버_오류는_사유에_도구_오류로_남는다(self, page, sut_base):
        page.goto(f"{sut_base}/nolabel/search")
        from prova.vlm.base import VLMError

        class Down:
            def locate(self, **kw):
                raise VLMError("connection refused")

        with pytest.raises(GroundingError) as info:
            heal_with_vlm(page, "검색", Down(), SEARCH_BTN)
        assert "도구 오류" in info.value.reason or "서버" in info.value.reason
        assert "connection refused" in info.value.reason

    def test_신뢰도_미달은_수치가_사유에_남는다(self, page, sut_base):
        page.goto(f"{sut_base}/nolabel/search")
        vlm = MockVLM()
        vlm.register("검색", (0.1, 0.1, 0.2, 0.2), confidence=0.31)
        with pytest.raises(GroundingError) as info:
            heal_with_vlm(page, "검색", vlm, SEARCH_BTN)
        assert "신뢰도" in info.value.reason and "0.31" in info.value.reason

    def test_좌표_비정상은_사유에_남는다(self, page, sut_base):
        page.goto(f"{sut_base}/nolabel/search")
        vlm = MockVLM()
        vlm.register("검색", (0.8, 0.8, 0.2, 0.2))
        with pytest.raises(GroundingError) as info:
            heal_with_vlm(page, "검색", vlm, SEARCH_BTN)
        assert "좌표" in info.value.reason

    def test_드라이버는_1차_시도를_버리지_않는다(self, page, sut_base, tmp_path):
        """라벨이 둘인 화면에서 보정까지 실패하면, 사유는 여전히 '후보가 여러 개'
        여야 한다 — 그게 개발자가 고칠 사실이다."""
        from prova.s4_executor.playwright_driver import ExecutionContext, _locate

        page.set_content(
            '<button aria-label="검색">1</button><button aria-label="검색">2</button>'
        )
        ctx = ExecutionContext(page=page, base_url="http://x", specs=[], run_dir=tmp_path,
                               case_id="c", vlm=MockVLM(), max_heal=2)
        with pytest.raises(GroundingError) as info:
            _locate(ctx, "검색", SEARCH_BTN)
        assert any(a.count > 1 for a in info.value.attempts)
        assert any(a.strategy == "vlm" for a in info.value.attempts)
        assert "여러 개" in info.value.reason


class TestLocatedSanity:
    """좌표 검사는 브라우저 없이 값으로 확인한다."""

    def test_정상_좌표(self):
        assert Located(bbox=(0.1, 0.2, 0.3, 0.4)).is_sane()

    def test_범위를_벗어나면_거부(self):
        assert not Located(bbox=(-0.1, 0.2, 0.3, 0.4)).is_sane()
        assert not Located(bbox=(0.1, 0.2, 1.3, 0.4)).is_sane()

    def test_크기가_0이면_거부(self):
        assert not Located(bbox=(0.3, 0.2, 0.3, 0.4)).is_sane()

    def test_중심을_계산한다(self):
        assert Located(bbox=(0.0, 0.0, 0.4, 0.6)).center == (0.2, 0.3)


# 파이프라인 수준 확인은 tests/test_nolabel_e2e.py 에 있다.
#
# 왜 파일을 나눴는가: 이 파일은 모듈 범위로 브라우저를 하나 띄워 두고 쓴다.
# run_pipeline 은 자기 sync_playwright() 컨텍스트를 여는데, 같은 스레드에서 그것을
# 겹치면 Playwright 가 "Sync API inside the asyncio loop" 로 거부한다.
