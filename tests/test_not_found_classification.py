"""못 찾은 것을 '기획서와 다름' 으로 보고하지 않는다 — 근거가 있을 때만.

## 왜 (2026-09-27 스파이크 3, 표를 보여 주는 화면)

the-internet `/tables`·demoqa `/webtables` 는 이름 없는 `<table>` 로 목록을 보여 준다.
기획서의 목록 이름('사용자 목록')으로 찾지 못하자 "4건이 나와야 하는데 찾지 못했다" 가
**구현 결함**으로 분류됐다. demoqa 의 안내 문구 케이스도 "요소를 찾지 못함" 만으로 같았다.

모두 도구로 옮기면 진짜 결함이 숨는다 — SUT 검색 bad 처럼 결과가 0건이라 목록을 그리지
않는 구현이 '실행 문제' 가 된다. 그래서 가르는 근거를 둔다: **이름 없는 표·목록이 화면에
있으면** 도구가 이름으로 못 찾은 것이다. 목록 비슷한 것이 아예 없으면 예전처럼 결함이다.
"""

from __future__ import annotations

import pytest

from prova.models import Expectation, StepResult, TestCase, TestStep, UIElement
from prova.s3_grounder.dom_locator import CollectionCount, count_items
from prova.s5_verifier.assertion_engine import PageState, verify


def _steps():
    return [StepResult(seq=1, action="navigate", target="/t", status="ok", elapsed_ms=1)]


def _case(expected: Expectation) -> TestCase:
    return TestCase(case_id="c", screen_id="s", title="t", type="positive",
                    steps=[TestStep(seq=1, action="navigate", target="/t")],
                    expected=expected)


def _count_verdict(status: str, lookalikes: int = 0, want: int = 4):
    counted = CollectionCount(target="사용자 목록", status=status, lookalikes=lookalikes,
                              detail="테스트")
    return verify(_case(Expectation(type="result_count", count=want,
                                    count_target="사용자 목록")),
                  _steps(), PageState(url="http://h/t", text="", collection=counted))


class TestCountClassification:
    def test_이름_없는_표가_있으면_탐지_실패다(self):
        v = _count_verdict("absent", lookalikes=2)
        assert v.verdict == "FAIL"
        assert v.failure_category == "element_not_found"

    def test_목록_비슷한_것이_없으면_여전히_결함이다(self):
        """결과 0건이라 목록을 안 그린 구현 — SUT 검색 bad 의 모양. 숨기면 미탐이다."""
        v = _count_verdict("absent", lookalikes=0)
        assert v.failure_category == "assertion_mismatch"

    def test_0건_기대의_부재는_여전히_통과다(self):
        assert _count_verdict("absent", lookalikes=2, want=0).verdict == "PASS"

    def test_목록을_특정하지_못하면_탐지_실패다(self):
        assert _count_verdict("ambiguous").failure_category == "element_not_found"

    def test_도구_오류는_기획서와_다름이_아니다(self):
        """사유가 '구현 결함이 아닙니다' 라고 말하면서 분류는 결함이던 자기모순."""
        assert _count_verdict("error").failure_category == "unknown"


class TestPlaceholderClassification:
    def _verdict(self, got):
        case = _case(Expectation(type="placeholders_match",
                                 placeholders={"검색어": "Type to search", "이름": "홍길동"}))
        return verify(case, _steps(), PageState(url="http://h/t", text="", placeholders=got))

    def test_못_찾은_것뿐이면_탐지_실패다(self):
        v = self._verdict({"이름": "홍길동"})
        assert v.verdict == "FAIL" and v.failure_category == "element_not_found"

    def test_문구가_다른_요소가_있으면_결함이다(self):
        v = self._verdict({"이름": "김철수"})
        assert v.failure_category == "assertion_mismatch"


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser.new_page()
        browser.close()


LIST = UIElement(element_id="user_list", type="list", label="사용자 목록")


class TestLookalikes:
    def test_이름_없는_표를_센다(self, page):
        page.set_content("""
          <h4>Example 1</h4>
          <table><thead><tr><th>Last Name</th></tr></thead>
                 <tbody><tr><td>Smith</td></tr><tr><td>Bach</td></tr></tbody></table>
          <h4>Example 2</h4>
          <table><tbody><tr><td>Doe</td></tr></tbody></table>""")
        r = count_items(page, "사용자 목록", LIST)
        assert r.status == "absent"
        assert r.lookalikes == 2
        assert "이름 없는 표·목록 2개" in r.detail

    def test_목록이_없는_화면은_0이다(self, page):
        page.set_content("<p>검색 결과가 없습니다.</p><nav><ul><li>홈</li></ul></nav>")
        r = count_items(page, "사용자 목록", LIST)
        assert r.status == "absent" and r.lookalikes == 0

    def test_숨은_표는_세지_않는다(self, page):
        page.set_content('<table hidden><tr><td>x</td></tr></table>')
        assert count_items(page, "사용자 목록", LIST).lookalikes == 0
