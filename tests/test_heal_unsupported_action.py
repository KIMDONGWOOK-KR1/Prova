"""2차 경로가 못 하는 동작(select·uncheck)은 '지원하지 않음' 이라고 말해야 한다.

## 2026-08-22 에 잡은 구멍

`_act_by_coords` 는 select/uncheck 에 `GroundingError(Attempt("vlm-unsupported",
count=1))` 을 던졌다. `GroundingError.reason` 은 `count == 1 and not visible` 을
"요소를 찾았으나 화면에 보이지 않음" 으로 읽는다 — 개발자가 존재하지 않는 가시성
버그를 찾게 된다. 실제 사실은 '좌표로는 이 동작을 할 수 없다' 이고, 그건 탐지
실패도 구현 결함도 아닌 **도구의 한계**다.
"""

from __future__ import annotations

import pytest

from prova.models import ElementLocation, TestStep, UIElement
from prova.s4_executor.playwright_driver import (
    ExecutionContext,
    UnsupportedHealAction,
    _act_by_coords,
    execute_step,
)


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1280, "height": 800})
        yield pg
        browser.close()


VLM_LOC = ElementLocation(target="가입 경로", method="vlm", selector=None,
                          bbox=[10, 10, 100, 30], confidence=0.9, healed=True,
                          strategy="vlm")


class TestUnsupported:
    def test_select_는_전용_예외다(self, page, tmp_path):
        ctx = ExecutionContext(page=page, base_url="http://x", specs=[], run_dir=tmp_path,
                               case_id="c")
        step = TestStep(seq=1, action="select", target="가입 경로", value="검색")
        with pytest.raises(UnsupportedHealAction) as info:
            _act_by_coords(ctx, VLM_LOC, step)
        assert "select" in str(info.value)

    def test_스텝_결과는_input_error_이고_사유가_지원하지_않음이다(self, page, tmp_path, monkeypatch):
        import prova.s4_executor.playwright_driver as drv

        monkeypatch.setattr(drv, "_locate", lambda ctx, target, hint: VLM_LOC)
        page.set_content("<div>x</div>")
        ctx = ExecutionContext(page=page, base_url="http://x", specs=[], run_dir=tmp_path,
                               case_id="c", screenshot_every_step=False)
        step = TestStep(seq=1, action="uncheck", target="약관 동의")
        result = execute_step(ctx, step)
        assert result.status == "error"
        assert result.error_code == "input_error"
        assert "지원하지 않" in (result.error_detail or "")
        assert "보이지 않음" not in (result.error_detail or "")
