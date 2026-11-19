"""페이지를 연 뒤 인트로(덮개) 화면이 걷히기를 기다린다 (2026-11-19, 실물 기획서의 사이트).

실물 사이트는 처음 열면 남색 바탕에 로고만 있는 `#intro` 를 화면 전체에 덮는다. 페이지를
연 지 0.7~1.3초 만에 스크린샷을 찍어서, 기획자용 보고서의 '판정 시점 화면' 6장 중 3장이
로딩 화면이었다. 덮개가 남아 있는 0.1초 뒤에 '닫기' 를 누르려다 멈춘 케이스도 있었다.

- 화면 전체를 덮고 누를 것이 하나도 없는 덮개는 걷힐 때까지 기다린다(상한 있음).
- 누를 것이 있는 덮개(팝업·동의창)는 사이트가 보여 주려는 화면이다 — 기다리지 않는다.
- 덮개가 없으면 기다리지 않는다.
"""

from __future__ import annotations

import pytest

from prova.models import ScreenSpec, TestStep
from prova.s4_executor.playwright_driver import (_SPLASH_WAIT_MS, ExecutionContext,
                                                 execute_step)

_BODY = "<h1>회사소개</h1><a href='/about'>자세히 보기</a>"
_COVER = ("<div id='intro' style='position:fixed;inset:0;background:#123;z-index:99'>"
          "<div class='introLogo'>LOGO</div></div>")
SPLASH = f"""<!doctype html><html><body>{_BODY}{_COVER}
<script>setTimeout(() => document.getElementById('intro').style.display = 'none', 800);</script>
</body></html>"""
STUCK_SPLASH = f"<!doctype html><html><body>{_BODY}{_COVER}</body></html>"
MODAL = f"""<!doctype html><html><body>{_BODY}
<div style='position:fixed;inset:0;background:#0008'><button>동의</button></div></body></html>"""
PLAIN = f"<!doctype html><html><body>{_BODY}</body></html>"


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _open(browser, tmp_path, body):
    page = browser.new_page()
    page.route("**/*", lambda route: route.fulfill(status=200, content_type="text/html", body=body))
    ctx = ExecutionContext(page=page, base_url="http://site.test",
                           specs=[ScreenSpec(screen_id="s", screen_name="s", url_path="/")],
                           run_dir=tmp_path, case_id="c", screenshot_every_step=False)
    r = execute_step(ctx, TestStep(seq=1, action="navigate", target="/"))
    return page, r


def test_인트로가_걷힌_뒤에_끝난다(browser, tmp_path):
    page, r = _open(browser, tmp_path, SPLASH)
    try:
        assert r.status == "ok"
        assert not page.is_visible("#intro")
        assert r.elapsed_ms >= 700
    finally:
        page.close()


def test_걷히지_않는_인트로는_상한까지만_기다린다(browser, tmp_path):
    page, r = _open(browser, tmp_path, STUCK_SPLASH)
    try:
        assert r.status == "ok"  # 덮개는 판정 근거가 아니다 — 이동 자체는 성공이다
        assert r.elapsed_ms < _SPLASH_WAIT_MS + 2000
    finally:
        page.close()


@pytest.mark.parametrize("body", [MODAL, PLAIN], ids=["누를_것이_있는_덮개", "덮개_없음"])
def test_기다리지_않는다(browser, tmp_path, body):
    page, r = _open(browser, tmp_path, body)
    try:
        assert r.status == "ok"
        assert r.elapsed_ms < 1500  # 화면이 멈췄는지 잠깐 지켜보는 시간만 든다
    finally:
        page.close()


def test_그림이_다_받아진_뒤에_끝난다(browser, tmp_path):
    """덮개가 걷혀도 큰 그림을 받는 중이면 반쯤 그려진 화면이 찍힌다 (2026-11-19, 실물 메인화면)."""
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    png = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                        "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/hero.png":
                time.sleep(1.0)
                body, ctype = png, "image/png"
            else:
                body, ctype = (PLAIN.replace("</body>", "<img id=hero src='/hero.png'></body>")
                               .encode()), "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    page = browser.new_page()
    try:
        ctx = ExecutionContext(page=page, base_url=f"http://127.0.0.1:{srv.server_port}",
                               specs=[ScreenSpec(screen_id="s", screen_name="s", url_path="/")],
                               run_dir=tmp_path, case_id="c", screenshot_every_step=False)
        r = execute_step(ctx, TestStep(seq=1, action="navigate", target="/"))
        assert r.status == "ok"
        assert page.evaluate("document.getElementById('hero').complete")
    finally:
        page.close()
        srv.shutdown()


def test_등장_연출이_멈춘_뒤에_끝난다(browser, tmp_path):
    """덮개도 없고 다 받아졌는데 그림이 커지다가 스스로 스크롤하는 화면 (2026-11-19, 실물 CONTACT)."""
    grow = f"""<!doctype html><html><body style='margin:0'>{_BODY}
<div id=hero style='height:40px;background:#345;transition:height 1s linear'></div>
<div style='height:2000px'></div>
<script>requestAnimationFrame(() => requestAnimationFrame(() =>
  document.getElementById('hero').style.height = '600px'));</script></body></html>"""
    page, r = _open(browser, tmp_path, grow)
    try:
        assert r.status == "ok"
        assert page.evaluate("document.getElementById('hero').getBoundingClientRect().height") > 590
    finally:
        page.close()


def test_계속_도는_작은_장식은_기다리지_않는다(browser, tmp_path):
    spin = f"""<!doctype html><html><head><style>@keyframes s {{ to {{ transform: rotate(360deg) }} }}
#d {{ width:20px; height:20px; background:red; animation: s 1s linear infinite }}</style></head>
<body>{_BODY}<div id=d></div></body></html>"""
    page, r = _open(browser, tmp_path, spin)
    try:
        assert r.elapsed_ms < 1500
    finally:
        page.close()
