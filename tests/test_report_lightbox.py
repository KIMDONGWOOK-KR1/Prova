"""리포트의 스크린샷을 누르면 새 탭이 아니라 화면 위에 크게 뜬다.

실패 카드를 읽다가 캡처를 보려고 탭을 오가면 어느 케이스를 보던 중인지 놓친다. 그래서
같은 화면 위에 겹쳐 띄우고 Esc · × · 바깥 누르기로 닫는다.

웹 UI 는 리포트를 iframe 안에 넣는데, 그 안에서만 띄우면 리포트 칸 크기에 갇힌다. 같은
출처의 바깥 문서에 띄워 브라우저 창 전체를 쓰는지를 실제 브라우저로 확인한다.
"""

from __future__ import annotations

import http.server
import threading

import pytest
from playwright.sync_api import sync_playwright

from prova.models import StepResult, Verdict
from prova.s6_report.report_builder import _LIGHTBOX_JS, _shots_html

# 1x1 PNG — 화면에 뜨는지만 보면 되므로 내용은 상관없다.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360606060000000050001a5f645400000000049454e44ae426082"
)


def _verdict(step_results: list[StepResult]) -> Verdict:
    return Verdict(
        case_id="login-001", title="로그인", type="positive",
        screen_id="login", verdict="FAIL", step_results=step_results,
    )


THREE = _shots_html(_verdict([
    StepResult(seq=1, action="navigate", target="/login", phase="setup", screenshot="a1.png"),
    StepResult(seq=1, action="navigate", target="/x", screenshot="b1.png"),
    StepResult(seq=2, action="click", target="저장", screenshot="b2.png"),
]))
ONE = _shots_html(_verdict([
    StepResult(seq=1, action="navigate", target="/y", screenshot="c1.png"),
]))
REPORT = (
    "<!doctype html><meta charset='utf-8'><title>r</title><body>"
    f"<div id='first'>{THREE}</div><div id='second'>{ONE}</div>"
    f"<script>{_LIGHTBOX_JS}</script></body>"
)
# 웹 UI 처럼 리포트를 창보다 작은 칸에 넣는다.
OUTER = (
    "<!doctype html><meta charset='utf-8'><title>ui</title><body>"
    "<h1>웹 UI</h1><iframe src='/report.html' style='width:400px;height:300px'></iframe></body>"
)


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.endswith(".png"):
            body, kind = PNG, "image/png"
        elif self.path == "/outer.html":
            body, kind = OUTER.encode(), "text/html; charset=utf-8"
        else:
            body, kind = REPORT.encode(), "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("content-type", kind)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def base():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1000, "height": 700})
    yield context.new_page()
    context.close()


BOX = "#prova-lightbox"


class TestStandalone:
    """리포트 파일을 그대로 열었을 때."""

    def test_누르면_새_탭이_아니라_같은_화면_위에_뜬다(self, page, base):
        page.goto(f"{base}/report.html")
        page.click("#first .shots a >> nth=1")
        assert page.locator(BOX).is_visible()
        assert page.locator(f"{BOX} img").get_attribute("src") == f"{base}/b1.png"
        assert len(page.context.pages) == 1
        assert page.url == f"{base}/report.html"

    def test_몇_번째_스텝인지_적힌다(self, page, base):
        page.goto(f"{base}/report.html")
        page.click("#first .shots a >> nth=0")
        assert "준비 step 1" in page.locator(BOX).inner_text()
        assert "1 / 3" in page.locator(BOX).inner_text()

    def test_Esc_로_닫힌다(self, page, base):
        page.goto(f"{base}/report.html")
        page.click("#first .shots a >> nth=0")
        page.keyboard.press("Escape")
        assert page.locator(BOX).count() == 0

    def test_닫기_버튼으로_닫힌다(self, page, base):
        page.goto(f"{base}/report.html")
        page.click("#first .shots a >> nth=0")
        page.click(f"{BOX} button[aria-label='닫기']")
        assert page.locator(BOX).count() == 0

    def test_바깥을_누르면_닫히고_그림을_누르면_안_닫힌다(self, page, base):
        page.goto(f"{base}/report.html")
        page.click("#first .shots a >> nth=0")
        page.click(f"{BOX} img")
        assert page.locator(BOX).count() == 1
        page.mouse.click(5, 350)
        assert page.locator(BOX).count() == 0

    def test_좌우_화살표로_같은_케이스의_스텝을_넘긴다(self, page, base):
        page.goto(f"{base}/report.html")
        page.click("#first .shots a >> nth=0")
        img = page.locator(f"{BOX} img")
        page.keyboard.press("ArrowRight")
        assert img.get_attribute("src") == f"{base}/b1.png"
        page.keyboard.press("ArrowRight")
        assert img.get_attribute("src") == f"{base}/b2.png"
        # 끝에서 한 번 더 넘기면 처음으로 — 다른 케이스의 캡처(c1)로 넘어가지 않는다.
        page.keyboard.press("ArrowRight")
        assert img.get_attribute("src") == f"{base}/a1.png"
        page.keyboard.press("ArrowLeft")
        assert img.get_attribute("src") == f"{base}/b2.png"
        page.click(f"{BOX} button[aria-label='이전 스크린샷']")
        assert img.get_attribute("src") == f"{base}/b1.png"

    def test_한_장뿐이면_넘기는_버튼이_없다(self, page, base):
        page.goto(f"{base}/report.html")
        page.click("#second .shots a")
        assert page.locator(f"{BOX} button").count() == 1
        assert "/" not in page.locator(f"{BOX} div").inner_text()

    def test_닫으면_누른_자리로_초점이_돌아온다(self, page, base):
        page.goto(f"{base}/report.html")
        page.click("#first .shots a >> nth=2")
        page.keyboard.press("Escape")
        assert page.evaluate("document.activeElement.getAttribute('href')") == "b2.png"

    def test_Ctrl_을_누른_채로는_예전처럼_새_탭이다(self, page, base):
        page.goto(f"{base}/report.html")
        with page.context.expect_page():
            page.click("#first .shots a >> nth=0", modifiers=["Control"])
        assert page.locator(BOX).count() == 0


class TestInsideWebUI:
    """웹 UI 처럼 iframe 안에 들어 있을 때 — 리포트 칸이 아니라 창 전체에 뜬다."""

    def test_바깥_문서에_창_전체_크기로_뜬다(self, page, base):
        page.goto(f"{base}/outer.html")
        frame = page.frame_locator("iframe")
        frame.locator("#first .shots a >> nth=1").click()
        assert frame.locator(BOX).count() == 0
        box = page.locator(BOX)
        assert box.is_visible()
        size = box.bounding_box()
        assert (size["width"], size["height"]) == (1000, 700)
        assert page.locator(f"{BOX} img").get_attribute("src") == f"{base}/b1.png"

    def test_바깥_문서에서_Esc_를_눌러도_닫힌다(self, page, base):
        page.goto(f"{base}/outer.html")
        page.frame_locator("iframe").locator("#first .shots a >> nth=0").click()
        page.keyboard.press("ArrowRight")
        assert page.locator(f"{BOX} img").get_attribute("src") == f"{base}/b1.png"
        page.keyboard.press("Escape")
        assert page.locator(BOX).count() == 0

    def test_리포트가_바뀌면_띄워_둔_것도_치운다(self, page, base):
        page.goto(f"{base}/outer.html")
        page.frame_locator("iframe").locator("#first .shots a >> nth=0").click()
        assert page.locator(BOX).count() == 1
        page.evaluate("document.querySelector('iframe').src = '/report.html?again'")
        page.wait_for_function("!document.querySelector('#prova-lightbox')")

    def test_닫고_나면_바깥_화면이_다시_스크롤된다(self, page, base):
        page.goto(f"{base}/outer.html")
        page.frame_locator("iframe").locator("#first .shots a >> nth=0").click()
        assert page.evaluate("document.documentElement.style.overflow") == "hidden"
        page.keyboard.press("Escape")
        assert page.evaluate("document.documentElement.style.overflow") == ""


class TestFallback:
    def test_링크는_그대로_남아_스크립트_없이도_열린다(self):
        assert "<a href='b1.png' target='_blank'>" in THREE

    def test_스크립트는_바깥_자원을_부르지_않는다(self):
        """리포트는 폴더째 옮겨도 열려야 한다 — 내려받는 것이 있으면 안 된다."""
        assert "http://" not in _LIGHTBOX_JS and "https://" not in _LIGHTBOX_JS
        assert "</script" not in _LIGHTBOX_JS
