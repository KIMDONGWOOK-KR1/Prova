"""2차 경로의 정체 대조 — 좌표 아래 요소가 '기획서의 다른 요소' 면 누르지 않는다.

실측 오탐 7/10(2026-08-22)의 모양: VLM 이 '검색' 을 찾으랬더니 다른 버튼의
좌표를 줬고, _require_actionable 은 '조작 가능한 무언가' 만 확인하므로 그대로
눌렀다. 엉뚱한 조작의 결과를 판정이 구현 결함으로 읽는다 — 없는 결함을
보고하는 오탐이다.

절제가 핵심이다: 막는 것은 좌표 아래 요소의 접근성 이름이 기획서의 **다른**
요소 라벨과 일치할 때뿐이다. 이름이 없거나 모르는 텍스트면 통과 — 라벨 없는
아이콘 버튼이 2차 경로의 존재 이유이므로, 모른다고 막으면 nolabel 화면에서
보정이 통째로 죽는다.
"""

from __future__ import annotations

import pytest

from prova.models import ScreenSpec, TestStep, UIElement
from prova.s3_grounder.dom_locator import ElementLocation, GroundingError
from prova.s4_executor.playwright_driver import ExecutionContext, _require_actionable


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1280, "height": 800})
        yield pg
        browser.close()


SPEC = ScreenSpec(
    screen_id="s", screen_name="검색", url_path="/s",
    elements=[
        UIElement(element_id="q", type="input", label="검색어"),
        UIElement(element_id="go", type="button", label="검색"),
        UIElement(element_id="login", type="button", label="로그인"),
    ],
)

HTML = """
<button aria-label="로그인" style="position:absolute;left:100px;top:100px;
        width:120px;height:40px">들어가기</button>
<button aria-label="검색" style="position:absolute;left:300px;top:100px;
        width:120px;height:40px">찾기</button>
<button style="position:absolute;left:500px;top:100px;width:40px;height:40px">🔍</button>
<label for="q" style="position:absolute;left:100px;top:200px">검색어</label>
<input id="q" style="position:absolute;left:180px;top:200px;width:160px;height:30px">
"""


def _ctx(page, tmp_path):
    return ExecutionContext(page=page, base_url="http://x", specs=[SPEC],
                            run_dir=tmp_path, case_id="t")


def _center(page, selector):
    box = page.locator(selector).bounding_box()
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def _loc(target):
    return ElementLocation(target=target, method="vlm", selector=None,
                           bbox=[0, 0, 10, 10], confidence=0.9, healed=True,
                           strategy="vlm")


def _click(target):
    return TestStep(seq=1, action="click", target=target)


class TestIdentityCheck:
    def test_다른_요소_라벨이면_누르지_않고_탐지_실패다(self, page, tmp_path):
        page.set_content(HTML)
        x, y = _center(page, "button[aria-label=로그인]")
        with pytest.raises(GroundingError) as exc:
            _require_actionable(_ctx(page, tmp_path), _loc("검색"), _click("검색"), x, y)
        assert "로그인" in str(exc.value.attempts[0].strategy)

    def test_맞는_요소면_통과한다(self, page, tmp_path):
        page.set_content(HTML)
        x, y = _center(page, "button[aria-label=검색]")
        _require_actionable(_ctx(page, tmp_path), _loc("검색"), _click("검색"), x, y)

    def test_이름_없는_아이콘_버튼은_막지_않는다(self, page, tmp_path):
        """라벨 없는 요소가 2차 경로의 존재 이유다 — 모르면 막지 않는다."""
        page.set_content(HTML)
        x, y = _center(page, "button:has-text('🔍')")
        _require_actionable(_ctx(page, tmp_path), _loc("검색"), _click("검색"), x, y)

    def test_연결된_label_도_이름으로_본다(self, page, tmp_path):
        page.set_content(HTML)
        x, y = _center(page, "#q")
        fill = TestStep(seq=1, action="fill", target="검색", value="x")
        with pytest.raises(GroundingError) as exc:
            _require_actionable(_ctx(page, tmp_path), _loc("검색"), fill, x, y)
        assert "검색어" in str(exc.value.attempts[0].strategy)

    def test_모르는_텍스트는_막지_않는다(self, page, tmp_path):
        """'들어가기' 는 기획서 라벨이 아니다 — 접근성 이름(aria-label)이 없고
        텍스트만 모르는 값이면 판정 근거가 없다. aria-label 이 '로그인' 인 위
        케이스와 달리, 여기는 aria-label 을 지운 사본으로 확인한다."""
        page.set_content(HTML.replace(' aria-label="로그인"', ""))
        x, y = _center(page, "button:has-text('들어가기')")
        _require_actionable(_ctx(page, tmp_path), _loc("검색"), _click("검색"), x, y)
