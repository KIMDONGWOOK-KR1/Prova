"""앱이 200 으로 '페이지 없음' 화면을 그린 경우.

## 2026-11-04 WebTestBench 0051 B 에서 잡은 구멍

기획서가 적은 경로(`/reviews/new`)가 앱에 없었다. 개발 서버는 모든 경로에 200 과 같은
index.html 을 주고, 앱이 "404 Oops! Page not found" 를 그렸다. 도구는 그 화면에서 입력란을
찾다가 22건을 '요소 못 찾음'·'기획서와 다름' 으로 냈다 — 원인은 화면이 없다는 것 하나다.

서버가 404 를 준 경우(soft404)와 같은 길로 보낸다: 화면은 계속 쓰고, 그 뒤의 실패는
'페이지 오류' 로 분류한다. '없는 ID 로 열면 안내 문구' 를 확인하는 케이스는 통과로 남는다.
"""

from __future__ import annotations

import pytest

from prova.models import Expectation, StepResult, TestCase, TestStep
from prova.s4_executor.playwright_driver import looks_not_found
from prova.s5_verifier.assertion_engine import PageState, verify


class TestLooksNotFound:
    @pytest.mark.parametrize("text", ["404 Oops! Page not found Return to Home",
                                      "404\n페이지를 찾을 수 없습니다", "Error 404 - Not Found"])
    def test_페이지_없음_화면(self, text):
        assert looks_not_found(text)

    @pytest.mark.parametrize("text", [
        "Page not found",                       # 숫자 없이는 상품명·안내문일 수 있다
        "Order #404 shipped",                   # 404 만 있는 보통 화면
        "404 Not Found " + "상품 목록 " * 200,   # 긴 화면 — 본문 중 일부일 뿐
    ])
    def test_보통_화면(self, text):
        assert not looks_not_found(text)


def _case(expected):
    return TestCase(case_id="c", screen_id="s", title="t", type="positive",
                    steps=[TestStep(seq=1, action="navigate", target="/reviews/new"),
                           TestStep(seq=2, action="fill", target="Review", value="x")],
                    expected=expected)


def _nav(**kw):
    return StepResult(seq=1, action="navigate", target="/reviews/new", status="ok",
                      http_status=200, not_found_page=True, **kw)


class TestVerdict:
    def test_뒤의_요소_못_찾음은_페이지_오류다(self):
        steps = [_nav(), StepResult(seq=2, action="fill", target="Review", status="error",
                                    error_code="element_not_found", error_detail="없음")]
        v = verify(_case(Expectation(type="text_visible", value="Saved")), steps,
                   PageState(url="http://x/reviews/new", text="404 Oops! Page not found"))
        assert v.failure_category == "page_error"
        assert "페이지 없음" in v.failure_detail

    def test_안내_문구를_확인하는_케이스는_통과다(self):
        case = TestCase(case_id="c", screen_id="s", title="t", type="negative",
                        steps=[TestStep(seq=1, action="navigate", target="/pets/nope")],
                        expected=Expectation(type="text_visible", value="Page not found"))
        v = verify(case, [_nav()], PageState(url="http://x/pets/nope",
                                             text="404 Oops! Page not found"))
        assert v.verdict == "PASS"


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        bodies = {"/reviews/new": "<h1>404</h1><p>Oops! Page not found</p>",
                  "/reviews": "<h1>Reviews</h1><p>Order 404 shipped</p>"}
        pg.route("http://app.test/**", lambda r: r.fulfill(
            status=200, content_type="text/html",
            body=bodies.get(r.request.url.replace("http://app.test", ""), "<p>x</p>")))
        yield pg
        browser.close()


class TestNavigate:
    def _run(self, page, tmp_path, path):
        from prova.s4_executor.playwright_driver import ExecutionContext, execute_step
        ctx = ExecutionContext(page=page, base_url="http://app.test", specs=[], run_dir=tmp_path,
                               case_id="c", screenshot_every_step=False)
        return execute_step(ctx, TestStep(seq=1, action="navigate", target=path))

    def test_페이지_없음_화면을_표시한다(self, page, tmp_path):
        r = self._run(page, tmp_path, "/reviews/new")
        assert r.status == "ok" and r.not_found_page

    def test_보통_화면은_표시하지_않는다(self, page, tmp_path):
        r = self._run(page, tmp_path, "/reviews")
        assert r.status == "ok" and not r.not_found_page
