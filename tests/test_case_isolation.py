"""케이스 격리 — 앞 케이스가 남긴 브라우저 상태가 다음 판정을 오염시키지 않는다.

쿠키만 지우던 시절에는 토큰을 localStorage 에 두는 SPA 에서 다음 케이스가 로그인된 채
시작했다. 비로그인 가드가 오탐이 나고, 로그인 전제가 없는 케이스도 앞 케이스의 세션으로
통과한다. 케이스마다 새 컨텍스트를 열어 저장소 종류를 일일이 세지 않아도 되게 했다.

`--session` 은 반대다 — 세션이 곧 기준 상태라 메인 컨텍스트를 유지하고, 가드 케이스만
세션 없는 새 컨텍스트에서 돈다.
"""

from __future__ import annotations

import http.server
import json
import threading

import pytest
from playwright.sync_api import sync_playwright

from prova.models import Expectation, ScreenSpec, SpecDocument, TestCase, TestStep
from prova.nodes import AgentState, page_opener, run_cases

PAGE = b"""<!doctype html><title>t</title><body><script>
if (location.pathname === '/login') {
  localStorage.setItem('token', 'jwt');
  sessionStorage.setItem('tab', '1');
}
document.body.innerText = [
  localStorage.getItem('token') ? 'LOCAL-LOGGED-IN' : 'LOCAL-ANON',
  sessionStorage.getItem('tab') ? 'TAB-LOGGED-IN' : 'TAB-ANON',
].join(' ');
</script></body>"""


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *_):
        pass


@pytest.fixture(scope="module")
def spa():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _case(case_id: str, path: str, text: str) -> TestCase:
    return TestCase(case_id=case_id, screen_id="s", title=case_id, type="positive",
                    steps=[TestStep(seq=1, action="navigate", target=path)],
                    expected=Expectation(type="text_visible", value=text))


def _state(base: str, tmp_path, cases: list[TestCase], **kw) -> AgentState:
    doc = SpecDocument(source="x", screens=[ScreenSpec(screen_id="s", screen_name="화면",
                                                       url_path="/")])
    return AgentState(pdf_path="", base_url=base, run_id="t", run_dir=tmp_path, doc=doc,
                      cases=cases, settle_timeout_ms=0, **kw)


def test_앞_케이스의_localStorage_가_다음_케이스에_남지_않는다(spa, browser, tmp_path):
    state = _state(spa, tmp_path, [_case("a", "/login", "LOCAL-LOGGED-IN"),
                                   _case("b", "/home", "LOCAL-ANON")],
                   open_page=page_opener(browser))
    run_cases(state)
    assert [v.verdict for v in state.verdicts] == ["PASS", "PASS"], state.verdicts[1].evidence


def test_앞_케이스의_sessionStorage_가_다음_케이스에_남지_않는다(spa, browser, tmp_path):
    state = _state(spa, tmp_path, [_case("a", "/login", "TAB-LOGGED-IN"),
                                   _case("b", "/home", "TAB-ANON")],
                   open_page=page_opener(browser))
    run_cases(state)
    assert [v.verdict for v in state.verdicts] == ["PASS", "PASS"], state.verdicts[1].evidence


def test_앞_케이스의_컨텍스트는_닫히고_마지막_것만_남는다(spa, browser, tmp_path):
    """다 쌓아 두면 메모리가 늘고, 마지막 것까지 닫으면 --hold 가 볼 화면이 없다."""
    state = _state(spa, tmp_path, [_case(c, "/home", "LOCAL-ANON") for c in "abc"],
                   open_page=page_opener(browser))
    run_cases(state)
    assert len(browser.contexts) == 1
    assert state.page.context is browser.contexts[0]


def test_세션_모드는_메인_컨텍스트를_유지하고_가드만_깨끗하게_돈다(spa, browser, tmp_path):
    session = tmp_path / "session.json"
    session.write_text(json.dumps({"cookies": [], "origins": [
        {"origin": spa, "localStorage": [{"name": "token", "value": "jwt"}]}]}),
        encoding="utf-8")
    main = browser.new_context(storage_state=str(session))
    page = main.new_page()
    state = _state(spa, tmp_path, [
        _case("s-a", "/home", "LOCAL-LOGGED-IN"),
        _case("s-precondition-guard-001", "/home", "LOCAL-ANON"),
        _case("s-b", "/home", "LOCAL-LOGGED-IN"),
    ], page=page, storage_state=str(session), open_page=page_opener(browser))
    run_cases(state)
    assert [v.verdict for v in state.verdicts] == ["PASS"] * 3
    assert state.page is page


def test_페이지를_열_방법이_없으면_시작하지_않는다(tmp_path):
    """쿠키만 지우는 약한 격리로 조용히 돌아가지 않는다."""
    state = _state("http://x", tmp_path, [_case("a", "/home", "x")])
    with pytest.raises(ValueError, match="open_page"):
        run_cases(state)
