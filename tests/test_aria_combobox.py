"""커스텀 ARIA 콤보박스(Radix/shadcn Select)를 고르고, 그 선택 항목을 읽는다.

## 2026-11-03 WebTestBench 시범에서 잡은 구멍

요즘 React 앱의 드롭다운은 네이티브 `<select>` 가 아니라 `button role=combobox` 를
누르면 body 끝에 `role=listbox` 가 붙는 모양이다(Radix Select). 시범 앱 세 개 모두
그랬고 네이티브 select 는 0개였다. 그래서

- select 스텝이 `Element is not a <select> element` 로 멈췄고(0094 B 11케이스),
- 선택 항목 확인은 '읽지 못했다' 를 **기획서와 다름**으로 보고했다(7건, 오탐 위험).

아래 마크업은 Radix 의 모양을 따른다: 트리거는 pointerdown 으로 열리고, 목록은 트리거
밖(body 끝)에 붙고, 폼 안에서는 aria-hidden 네이티브 select 를 함께 둔다.
"""

from __future__ import annotations

import pytest

from prova.models import (
    Expectation,
    StepResult,
    TestCase,
    TestStep,
    UIElement,
)
from prova.s3_grounder.dom_locator import read_options
from prova.s4_executor.playwright_driver import ExecutionContext, execute_step
from prova.s5_verifier.assertion_engine import PageState, verify

RADIX = """
<form>
  <label for="t">Pet type</label>
  <button type="button" id="t" role="combobox" aria-controls="lb" aria-expanded="false"
          aria-autocomplete="none" data-state="closed"><span>All Types</span></button>
  <select aria-hidden="true" tabindex="-1" style="position:absolute;opacity:0">
    <option value=""></option><option>Dog</option><option>Cat</option>
  </select>
</form>
<script>(() => {
  const OPTIONS = %s;
  const t = document.getElementById('t');
  // Radix 는 목록이 열린 동안 목록 밖의 모든 것에 aria-hidden 을 건다(hideOthers).
  // 트리거도 접근성 트리에서 빠지므로, 열린 뒤 role 로 트리거를 다시 찾으면 못 찾는다.
  const form = document.querySelector('form');
  function close() {
    document.getElementById('lb')?.remove();
    t.setAttribute('aria-expanded', 'false');
    form.removeAttribute('aria-hidden');
  }
  t.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    if (document.getElementById('lb')) return close();
    const lb = document.createElement('div');
    lb.id = 'lb'; lb.setAttribute('role', 'listbox');
    for (const name of OPTIONS) {
      const o = document.createElement('div');
      o.setAttribute('role', 'option');
      o.innerHTML = '<span>' + name + '</span>';
      o.addEventListener('pointerup', () => { t.firstElementChild.textContent = name; close(); });
      lb.appendChild(o);
    }
    document.body.appendChild(lb);
    t.setAttribute('aria-expanded', 'true');
    form.setAttribute('aria-hidden', 'true');
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });
})();</script>
"""

HINT = UIElement(element_id="pet_type", type="select", label="Pet type")


def _radix(options=("All Types", "Dog", "Cat")):
    import json

    return RADIX % json.dumps(list(options))


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1280, "height": 800})
        yield pg
        browser.close()


class TestReadOptions:
    def test_목록을_열어_항목을_읽는다(self, page):
        page.set_content(_radix())
        assert read_options(page, "Pet type", HINT) == ["All Types", "Dog", "Cat"]

    def test_읽은_뒤_목록을_닫아_둔다(self, page):
        # 열린 목록이 남으면 다음 스텝의 클릭을 가린다.
        page.set_content(_radix())
        read_options(page, "Pet type", HINT)
        assert page.locator("#t").get_attribute("aria-expanded") == "false"
        assert page.locator("[role=listbox]").count() == 0

    def test_숨은_네이티브_select_를_읽지_않는다(self, page):
        # Radix 가 폼 제출용으로 두는 aria-hidden select 의 항목(Dog, Cat)은 화면의
        # 목록과 다를 수 있다. 사용자가 보는 것은 listbox 다.
        page.set_content(_radix(("All Types", "Dog")))
        assert read_options(page, "Pet type", HINT) == ["All Types", "Dog"]

    def test_라벨_없이_글자로_찾은_트리거도_읽는다(self, page):
        # 0094 의 필터처럼 라벨이 없으면 트리거는 자기 글자('All Types')를 이름으로
        # role=combobox 로 찾힌다. 열린 뒤에는 aria-hidden 때문에 그 조회가 아무것도
        # 가리키지 않는다 — 트리거를 다시 조회하면 30초를 기다리고 실패한다.
        page.set_content(_radix().replace('<label for="t">Pet type</label>', ''))
        assert read_options(page, "All Types", None) == ["All Types", "Dog", "Cat"]
        assert page.locator("[role=listbox]").count() == 0

    def test_눌러도_목록이_안_뜨면_None_이다(self, page):
        page.set_content('<button role="combobox" aria-label="Pet type">All</button>')
        assert read_options(page, "Pet type", HINT) is None


class TestSelectStep:
    def _ctx(self, page, tmp_path):
        return ExecutionContext(page=page, base_url="http://x", specs=[], run_dir=tmp_path,
                                case_id="c", screenshot_every_step=False)

    def test_목록에서_항목을_고른다(self, page, tmp_path):
        page.set_content(_radix())
        step = TestStep(seq=1, action="select", target="Pet type", value="Cat")
        result = execute_step(self._ctx(page, tmp_path), step)
        assert result.status == "ok", result.error_detail
        assert page.locator("#t").inner_text() == "Cat"

    def test_없는_항목이면_실패하고_결함으로_말하지_않는다(self, page, tmp_path):
        page.set_content(_radix())
        step = TestStep(seq=1, action="select", target="Pet type", value="Bird")
        result = execute_step(self._ctx(page, tmp_path), step)
        assert result.status == "error"
        assert result.error_code != "assertion_mismatch"
        assert "Bird" in (result.error_detail or "")
        assert page.locator("[role=listbox]").count() == 0

    def test_라벨_없이_글자로_찾은_트리거에서_고른다(self, page, tmp_path):
        page.set_content(_radix().replace('<label for="t">Pet type</label>', ''))
        step = TestStep(seq=1, action="select", target="All Types", value="Dog")
        ctx = self._ctx(page, tmp_path)
        ctx.step_timeout_ms = 3000
        result = execute_step(ctx, step)
        assert result.status == "ok", result.error_detail
        assert page.locator("#t").inner_text() == "Dog"

    def test_네이티브_select_는_그대로_고른다(self, page, tmp_path):
        page.set_content('<label for="s">Pet type</label><select id="s"><option>Dog</option>'
                         '<option>Cat</option></select>')
        step = TestStep(seq=1, action="select", target="Pet type", value="Cat")
        result = execute_step(self._ctx(page, tmp_path), step)
        assert result.status == "ok", result.error_detail
        assert page.locator("#s").input_value() == "Cat"


class TestUnreadOptionsVerdict:
    def test_못_읽은_선택_항목은_기획서와_다름이_아니다(self):
        case = TestCase(case_id="c", screen_id="s", title="t", type="positive",
                        steps=[TestStep(seq=1, action="navigate", target="/")],
                        expected=Expectation(type="options_present", options=["Dog"],
                                             option_target="Pet type"))
        steps = [StepResult(seq=1, action="navigate", target="/", status="ok")]
        v = verify(case, steps, PageState(url="http://x/", text="", options=None))
        assert v.verdict == "FAIL"
        assert v.failure_category == "unverifiable"
        assert "읽지 못했습니다" in v.failure_detail


class TestNotADropdown:
    """기획서는 선택 목록인데 화면은 다른 형태(체크박스 묶음 등)일 때, 사유가 그 사실을 말한다.

    2026-11-03 0037 A: 'Species' 는 체크박스 묶음의 제목 <label> 이었다. Playwright 의 원문
    `Element is not a <select> element` 만 남아, 읽는 사람이 무엇이 다른지 알 수 없었다.
    """

    def test_선택_목록이_아니라는_사실과_실제_모양을_말한다(self, page, tmp_path):
        page.set_content('<label>Species</label>'
                         '<button role="checkbox" aria-label="Dogs"></button>')
        ctx = ExecutionContext(page=page, base_url="http://x", specs=[], run_dir=tmp_path,
                               case_id="c", screenshot_every_step=False)
        result = execute_step(ctx, TestStep(seq=1, action="select", target="Species",
                                            value="Dogs"))
        assert result.status == "error"
        assert result.error_code == "input_error"
        assert "선택 목록이 아닙니다" in (result.error_detail or "")
        assert "<label>" in (result.error_detail or "")

    def test_라벨_글자로_찾혀도_연결된_select_는_고른다(self, page, tmp_path):
        # Playwright 는 <label> 에서 연결된 <select> 로 옮겨 고른다. 그 경로를 막지 않는다.
        page.set_content('<label for="s">Species</label>'
                         '<select id="s"><option>Dogs</option><option>Cats</option></select>')
        ctx = ExecutionContext(page=page, base_url="http://x", specs=[], run_dir=tmp_path,
                               case_id="c", screenshot_every_step=False)
        from prova.models import ElementLocation
        from prova.s4_executor.playwright_driver import _act_by_locator
        loc = ElementLocation(target="Species", strategy="text", selector="text='Species'")
        _act_by_locator(ctx, loc, None, TestStep(seq=1, action="select", target="Species",
                                                 value="Cats"))
        assert page.locator("#s").input_value() == "Cats"
