"""기준선이 실제 브라우저에서 잡히고 판정까지 가는가 — PTA 모양을 네트워크 없이 재현.

화면은 누르기 전부터 숨은 오류 칸에 'Your username is invalid!' 를 담고 있고,
Submit 을 눌러도 아무 일도 하지 않는다(로그인이 망가진 구현). 예전에는 이 화면에서
'오류 문구가 나오는가' 케이스가 통과했다.
"""

from __future__ import annotations

import pytest

from prova.models import Expectation, TestStep
from prova.nodes import _steps_with_baseline
from prova.s4_executor.playwright_driver import ExecutionContext
from prova.s5_verifier.assertion_engine import capture_page_state, verify

PAGE = """<html><body>
<p>Use next credentials to execute Login</p>
<label for="u">Username</label><input id="u">
<button id="s">Submit</button>
<div id="error" style="opacity:0">Your username is invalid!</div>
</body></html>"""


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.route("http://ext.test/**", lambda route: route.fulfill(
            status=200, content_type="text/html", body=PAGE))
        yield pg
        browser.close()


def test_망가진_로그인은_숨은_문구로_통과하지_못한다(page, tmp_path):
    from prova.models import TestCase

    steps = [TestStep(seq=1, action="navigate", target="/login"),
             TestStep(seq=2, action="fill", target="Username", value="incorrectUser"),
             TestStep(seq=3, action="click", target="Submit")]
    ctx = ExecutionContext(page=page, base_url="http://ext.test", specs=[],
                           run_dir=tmp_path, case_id="c", screenshot_every_step=False)
    results, baseline = _steps_with_baseline(ctx, steps)
    assert all(r.status == "ok" for r in results)
    assert baseline is not None and "Your username is invalid!" in baseline[1]

    state = capture_page_state(page)
    state.baseline_url, state.baseline_text = baseline
    case = TestCase(case_id="c", screen_id="login", title="잘못된 사용자", type="negative",
                    steps=steps,
                    expected=Expectation(type="error_message", value="Your username is invalid!"))
    v = verify(case, results, state)
    assert v.verdict == "FAIL"
    assert v.failure_category == "unverifiable"
