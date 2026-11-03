"""틀 라벨('Select {Job title} for comparison')은 항목마다 하나씩 있다 — n번째 스텝은 n번째 항목.

## 2026-11-03 WebTestBench 4차 측정에서 잡은 구멍

0094 B `job_search-valid-001` 은 공고 카드의 비교 체크박스를 누르는 스텝에서 멈췄다.
체크박스는 카드마다 하나씩 있고 **접근성 이름이 없다.** 1차 경로는 이름으로 못 찾고,
2차 경로(VLM)는 중괄호가 든 글자를 그대로 받아 신뢰도 0 을 냈다.

기획서의 틀 라벨은 '항목마다 반복되는 요소' 라는 뜻이다. 사람 테스터는 첫 항목의 것을
누른다. 그래서:

- 케이스 안에서 같은 틀 라벨을 k번째로 조작하면 **k번째 항목**의 것을 쓴다. 비교 흐름처럼
  두 번 체크하는 스텝이 같은 체크박스를 두 번 눌러 꺼 버리는 일을 막는다.
- 2차 경로는 VLM 에 '몇 번째 항목' 인지 말하고, **누르기 전에 좌표 아래 요소가 정말 그
  번째 항목인지 DOM 으로 확인한다.** 다르면 누르지 않는다 — 모델의 순서 세기를 믿지 않는다.
- 토글·괄호 설명처럼 틀이 아닌 라벨은 그대로다(여럿이면 고르지 않는다).
"""

from __future__ import annotations

import pytest

from prova.models import ScreenSpec, TestStep, UIElement
from prova.s3_grounder.dom_locator import (
    GroundingError,
    ground,
    heal_with_vlm,
    resolve_locator,
)
from prova.s4_executor.playwright_driver import (
    ExecutionContext,
    _require_actionable,
    execute_case_steps,
)
from prova.vlm.base import Located
from prova.vlm.mock_backend import MockVLM

TPL = "Select {Job title} for comparison"
CHECK = UIElement(element_id="cmp", type="checkbox", label=TPL)
SPEC = ScreenSpec(screen_id="jobs", screen_name="공고", url_path="/", elements=[CHECK])

# 카드 셋, 각 카드에 이름 없는 체크박스(Radix 는 button role=checkbox).
UNNAMED = """
<div class="list">
  <div class="card" style="height:120px"><button role="checkbox" aria-checked="false"
     onclick="this.setAttribute('aria-checked', this.getAttribute('aria-checked')==='true'?'false':'true')"
     style="width:20px;height:20px"></button><h3>Frontend</h3></div>
  <div class="card" style="height:120px"><button role="checkbox" aria-checked="false"
     onclick="this.setAttribute('aria-checked', this.getAttribute('aria-checked')==='true'?'false':'true')"
     style="width:20px;height:20px"></button><h3>Backend</h3></div>
  <div class="card" style="height:120px"><button role="checkbox" aria-checked="false"
     onclick="this.setAttribute('aria-checked', this.getAttribute('aria-checked')==='true'?'false':'true')"
     style="width:20px;height:20px"></button><h3>Data</h3></div>
</div>
"""

NAMED = """
<label><input type="checkbox" id="a"> Select Frontend for comparison</label>
<label><input type="checkbox" id="b"> Select Backend for comparison</label>
"""


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser.new_page(viewport={"width": 1280, "height": 800})
        browser.close()


def _ctx(page, tmp_path, vlm=None):
    return ExecutionContext(page=page, base_url="http://x", specs=[SPEC], run_dir=tmp_path,
                            case_id="t", vlm=vlm, screenshot_every_step=False)


def _check(seq):
    return TestStep(seq=seq, action="check", target=TPL)


class TestGroundOrdinal:
    def test_이름_있는_틀은_n번째를_고른다(self, page):
        page.set_content(NAMED)
        loc = ground(page, TPL, CHECK, ordinal=1)
        resolve_locator(page, loc, CHECK).check()
        assert page.locator("#b").is_checked()
        assert not page.locator("#a").is_checked()

    def test_순번이_항목_수를_넘으면_못_찾는다(self, page):
        page.set_content(NAMED)
        with pytest.raises(GroundingError):
            ground(page, TPL, CHECK, ordinal=2)

    def test_순번이_없으면_여럿일_때_고르지_않는다(self, page):
        page.set_content(NAMED)
        with pytest.raises(GroundingError):
            ground(page, TPL, CHECK)

    def test_틀이_아닌_라벨은_순번을_무시한다(self, page):
        hint = UIElement(element_id="f", type="button", label="Like / Liked")
        page.set_content("<button>Like</button><button>Like</button>")
        with pytest.raises(GroundingError):
            ground(page, hint.label, hint, ordinal=0)


class _Recorder:
    name = "rec"

    def __init__(self):
        self.calls = []

    def locate(self, *, image_png, target, hint=""):
        self.calls.append((target, hint))
        return Located(bbox=(0.0, 0.0, 0.02, 0.03), confidence=0.9)


class TestVLMOrdinal:
    def test_몇_번째_항목인지_VLM_에_말한다(self, page):
        page.set_content(UNNAMED)
        rec = _Recorder()
        loc = heal_with_vlm(page, TPL, rec, CHECK, ordinal=1)
        target, hint = rec.calls[0]
        assert target == TPL
        assert "2번째" in hint and "항목" in hint
        assert loc.nth == 1

    def test_틀이_아니면_순번을_말하지_않는다(self, page):
        page.set_content(UNNAMED)
        rec = _Recorder()
        heal_with_vlm(page, "Compare", rec, UIElement(element_id="c", type="button",
                                                     label="Compare"), ordinal=0)
        assert "번째" not in rec.calls[0][1]


def _center(page, nth):
    box = page.locator("[role=checkbox]").nth(nth).bounding_box()
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


class TestOrdinalGuard:
    def _loc(self, nth):
        from prova.s3_grounder.dom_locator import ElementLocation
        return ElementLocation(target=TPL, method="vlm", selector=None, bbox=[0, 0, 10, 10],
                               confidence=0.9, healed=True, strategy="vlm", nth=nth)

    def test_다른_번째_항목이면_누르지_않는다(self, page, tmp_path):
        page.set_content(UNNAMED)
        x, y = _center(page, 0)
        with pytest.raises(GroundingError) as exc:
            _require_actionable(_ctx(page, tmp_path), self._loc(1), _check(1), x, y)
        assert "1번째" in exc.value.reason and "2번째" in exc.value.reason

    def test_맞는_번째_항목이면_통과한다(self, page, tmp_path):
        page.set_content(UNNAMED)
        x, y = _center(page, 1)
        _require_actionable(_ctx(page, tmp_path), self._loc(1), _check(1), x, y)

    def test_반복되지_않는_요소는_첫째만_받는다(self, page, tmp_path):
        page.set_content('<div><button role="checkbox" style="width:20px;height:20px">'
                         '</button></div>')
        x, y = _center(page, 0)
        _require_actionable(_ctx(page, tmp_path), self._loc(0), _check(1), x, y)
        with pytest.raises(GroundingError):
            _require_actionable(_ctx(page, tmp_path), self._loc(1), _check(1), x, y)


class _Unsure(_Recorder):
    """상자는 맞게 주면서 신뢰도는 0 이라고 하는 모델(실측: Qwen3.5-4B, 같은 화면에서 0↔0.95)."""

    def __init__(self, page, selector):
        super().__init__()
        self.page, self.selector = page, selector

    def locate(self, *, image_png, target, hint=""):
        self.calls.append((target, hint))
        box = self.page.locator(self.selector).bounding_box()
        w, h = 1280, 800
        return Located(bbox=(box["x"] / w, box["y"] / h, (box["x"] + box["width"]) / w,
                             (box["y"] + box["height"]) / h), confidence=0.0)


class TestLowConfidenceTemplate:
    """틀 라벨은 모델의 자기 신고 대신 DOM 확인(반복 항목 안의 n번째)을 관문으로 쓴다."""

    def test_틀_라벨은_신뢰도가_낮아도_상자를_받는다(self, page):
        page.set_content(UNNAMED)
        loc = heal_with_vlm(page, TPL, _Unsure(page, ".card:nth-child(1) [role=checkbox]"),
                            CHECK, ordinal=0)
        assert loc.nth == 0 and loc.confidence == 0.0

    def test_틀이_아니면_신뢰도_관문_그대로다(self, page):
        page.set_content(UNNAMED)
        hint = UIElement(element_id="c", type="checkbox", label="Compare")
        with pytest.raises(GroundingError):
            heal_with_vlm(page, "Compare", _Unsure(page, ".card:nth-child(1) [role=checkbox]"),
                          hint, ordinal=0)

    def test_신뢰도가_낮으면_반복_항목_밖의_요소는_누르지_않는다(self, page, tmp_path):
        page.set_content('<div><button role="checkbox" style="width:20px;height:20px">'
                         '</button></div>')
        from prova.s3_grounder.dom_locator import ElementLocation
        loc = ElementLocation(target=TPL, method="vlm", bbox=[0, 0, 10, 10], confidence=0.0,
                              healed=True, strategy="vlm", nth=0)
        x, y = _center(page, 0)
        with pytest.raises(GroundingError):
            _require_actionable(_ctx(page, tmp_path), loc, _check(1), x, y)

    def test_신뢰도가_낮아도_맞는_항목이면_누른다(self, page, tmp_path):
        page.set_content(UNNAMED)
        vlm = _Unsure(page, ".card:nth-child(1) [role=checkbox]")
        results = execute_case_steps(_ctx(page, tmp_path, vlm), [_check(1)])
        assert results[0].status == "ok"
        assert page.locator("[role=checkbox]").nth(0).get_attribute("aria-checked") == "true"


def test_조작할_요소가_없어_막은_사유가_리포트_문장에_나온다(page, tmp_path):
    # 실측: 모델이 화면 전체를 상자로 줬고 그 가운데는 카드 글자였다. 리포트에는
    # '일치하는 요소가 없음' 만 남아 왜 보정하지 않았는지 읽히지 않았다.
    page.set_content(UNNAMED)
    from prova.s3_grounder.dom_locator import ElementLocation
    loc = ElementLocation(target=TPL, method="vlm", bbox=[0, 0, 10, 10], confidence=0.0,
                          healed=True, strategy="vlm", nth=0)
    box = page.locator("h3").first.bounding_box()
    with pytest.raises(GroundingError) as exc:
        _require_actionable(_ctx(page, tmp_path), loc, _check(1), box["x"] + 5, box["y"] + 5)
    assert "조작 가능한 요소" in exc.value.reason


class TestCaseSteps:
    def test_같은_틀을_두_번_조작하면_다른_항목이다(self, page, tmp_path):
        page.set_content(NAMED)
        results = execute_case_steps(_ctx(page, tmp_path), [_check(1), _check(2)])
        assert [r.status for r in results] == ["ok", "ok"]
        assert page.locator("#a").is_checked() and page.locator("#b").is_checked()

    def test_VLM_이_같은_자리를_또_주면_두_번째는_누르지_않는다(self, page, tmp_path):
        # 모델이 순서를 무시하고 첫 카드만 가리키는 경우. 눌렀다면 첫 체크가 꺼진다.
        page.set_content(UNNAMED)
        vlm = MockVLM(page)
        vlm.register_selector(TPL, ".card:nth-child(1) [role=checkbox]")
        results = execute_case_steps(_ctx(page, tmp_path, vlm), [_check(1), _check(2)])
        assert results[0].status == "ok"
        assert results[1].error_code == "element_not_found"
        first = page.locator("[role=checkbox]").nth(0)
        assert first.get_attribute("aria-checked") == "true"
