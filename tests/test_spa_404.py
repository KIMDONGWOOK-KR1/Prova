"""정상 화면에도 HTTP 404 를 돌려주는 SPA (2026-09-28, 스파이크 3 발견 5).

saucedemo 는 앱의 경로(`/inventory.html`)를 서버가 모른다 — 모든 경로에 404 와 같은
index.html 을 주고, 앱이 브라우저에서 화면을 그린다. 로그인했으면 상품 목록이, 안 했으면
'로그인해야 볼 수 있다' 가 뜬다. **없는 경로도 똑같이 404 인데 본문이 비어 있다.**

404 를 받자마자 page_error 로 끊어서 그 화면의 케이스 5개가 실행조차 안 됐다. 응답
코드로는 가를 수 없으니 화면으로 가른다:

- 404 인데 본문에 글자가 생기면 계속한다. 404 는 근거로 남긴다(StepResult.http_status).
- 본문이 비어 있으면 예전처럼 page_error.
- 계속한 케이스가 요소를 못 찾아 실패하면 요소 미탐지가 아니라 page_error 다 — 글자는
  있지만 앱이 아닌 서버 404 페이지가 여기 걸린다.
- 계속한 케이스가 '에러 없음'·'문구 없음' 만 확인했으면 통과로 두지 않는다 — 망가진
  경로가 빈 통과가 되는 것을 막는다.
- 404 만 이렇게 본다. 다른 4xx·5xx 는 예전처럼 바로 page_error.
"""

from __future__ import annotations

import pytest

from prova.models import Expectation, ScreenSpec, StepResult, TestCase, TestStep
from prova.s4_executor.playwright_driver import ExecutionContext, execute_step
from prova.s5_verifier.assertion_engine import WEAK_PASS_REASON, PageState, verify

SPA = """<!doctype html><html><body><div id=root></div>
<script>setTimeout(() => { document.getElementById('root').innerHTML =
  '<h1>Products</h1>'; }, 300);</script></body></html>"""
EMPTY_SPA = """<!doctype html><html><body><div id=root></div></body></html>"""


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _navigate(browser, tmp_path, status: int, body: str) -> StepResult:
    page = browser.new_page()
    page.route("**/*", lambda route: route.fulfill(
        status=status, content_type="text/html", body=body))
    ctx = ExecutionContext(page=page, base_url="http://spa.test",
                           specs=[ScreenSpec(screen_id="s", screen_name="s", url_path="/s")],
                           run_dir=tmp_path, case_id="c", screenshot_every_step=False)
    try:
        return execute_step(ctx, TestStep(seq=1, action="navigate", target="/inventory.html"))
    finally:
        page.close()


class TestNavigate:
    def test_404_인데_앱이_화면을_그리면_계속한다(self, browser, tmp_path):
        r = _navigate(browser, tmp_path, 404, SPA)
        assert r.status == "ok"
        assert r.http_status == 404

    def test_404_에_본문이_비어_있으면_페이지_오류다(self, browser, tmp_path):
        r = _navigate(browser, tmp_path, 404, EMPTY_SPA)
        assert (r.status, r.error_code) == ("error", "page_error")
        assert "404" in r.error_detail

    def test_JSON_404_는_앱_화면이_아니다(self, browser, tmp_path):
        """우리 SUT(FastAPI)는 없는 화면에 {"detail":"Not Found"} 를 준다. 글자가 있다고
        계속하자 SUT 판정 134건이 page_error 에서 '기획서와 다름' 으로 바뀌었다."""
        page = browser.new_page()
        page.route("**/*", lambda route: route.fulfill(
            status=404, content_type="application/json", body='{"detail":"Not Found"}'))
        ctx = ExecutionContext(page=page, base_url="http://spa.test",
                               specs=[ScreenSpec(screen_id="s", screen_name="s", url_path="/s")],
                               run_dir=tmp_path, case_id="c", screenshot_every_step=False)
        try:
            r = execute_step(ctx, TestStep(seq=1, action="navigate", target="/x"))
        finally:
            page.close()
        assert (r.status, r.error_code) == ("error", "page_error")

    def test_404_가_아닌_오류는_예전처럼_바로_끊는다(self, browser, tmp_path):
        r = _navigate(browser, tmp_path, 500, SPA)
        assert (r.status, r.error_code) == ("error", "page_error")
        assert r.http_status == 500

    def test_정상_응답도_상태를_남긴다(self, browser, tmp_path):
        r = _navigate(browser, tmp_path, 200, SPA)
        assert (r.status, r.http_status) == ("ok", 200)


def _case(expected: Expectation, type_="positive") -> TestCase:
    return TestCase(case_id="c", screen_id="s", title="t", type=type_,
                    steps=[TestStep(seq=1, action="navigate", target="/inventory.html")],
                    expected=expected)


def _soft404(*more: StepResult) -> list[StepResult]:
    return [StepResult(seq=1, action="navigate", target="/inventory.html",
                       status="ok", http_status=404), *more]


STATE = PageState(url="http://spa.test/inventory.html", text="Products")


class TestVerify:
    def test_계속한_뒤_요소를_못_찾으면_페이지_오류다(self):
        steps = _soft404(StepResult(seq=2, action="click", target="정렬", status="error",
                                    error_code="element_not_found", error_detail="없음"))
        v = verify(_case(Expectation(type="text_visible", value="Products")), steps, STATE)
        assert (v.verdict, v.failure_category) == ("FAIL", "page_error")
        assert "404" in v.failure_detail

    def test_에러_없음만_확인했으면_통과가_아니다(self):
        v = verify(_case(Expectation(type="toast_or_redirect")), _soft404(), STATE)
        assert (v.verdict, v.failure_category) == ("FAIL", "page_error")

    def test_문구_없음만_확인했으면_통과가_아니다(self):
        v = verify(_case(Expectation(type="text_absent", value="Error")), _soft404(), STATE)
        assert (v.verdict, v.failure_category) == ("FAIL", "page_error")

    def test_기대_문구를_확인했으면_통과하고_404_를_근거로_남긴다(self):
        v = verify(_case(Expectation(type="text_visible", value="Products")), _soft404(), STATE)
        assert v.verdict == "PASS"
        assert v.evidence.get("http_status") == 404

    def test_기대와_달라도_구현_결함이_아니라_페이지_오류다(self):
        """서버의 HTML 404 페이지도 글자가 있어 계속하게 된다. 그 화면의 불일치를 구현
        결함으로 보고하면 오탐이다 — 사유(판정 내용)는 그대로 싣는다."""
        v = verify(_case(Expectation(type="text_visible", value="Checkout")), _soft404(), STATE)
        assert (v.verdict, v.failure_category) == ("FAIL", "page_error")
        assert "404" in v.failure_detail and "Checkout" in v.failure_detail

    def test_404_가_없으면_에러_없음_통과는_예전과_같다(self):
        steps = [StepResult(seq=1, action="navigate", target="/s", status="ok", http_status=200)]
        v = verify(_case(Expectation(type="toast_or_redirect")), steps, STATE)
        assert v.verdict == "PASS"
        assert v.evidence["actual"] == WEAK_PASS_REASON
