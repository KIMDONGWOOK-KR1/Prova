"""실행 중 화면 — 항목 표의 줄이 집계 줄을 따라 '끝남' 으로 바뀌는가 (웹 UI app.js, 실제 브라우저).

2026-11-25: 실행을 시작할 때 0 집계 줄이 오지 않으면 첫 집계 줄에서 첫 항목을 판정하지 못해
첫 줄이 끝까지 '진행 중' 으로 남았다(prog.last 가 null 이라 settleRow 가 그냥 돌아갔다).
"""

from __future__ import annotations

import http.server
import threading
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

STATIC = Path(__file__).resolve().parents[1] / "src" / "prova" / "server" / "static"


class _Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(STATIC), **k)

    def translate_path(self, path):
        # 웹 UI 는 /static/… 으로 읽는다. 서버 API 는 이 테스트에서 비워 둔다(빈 목록).
        if path.startswith("/static/"):
            path = path[len("/static"):]
        return super().translate_path(path)

    def do_GET(self):
        if self.path.startswith("/api/") or self.path.startswith("/runs"):
            body = b'{"runs": [], "specs": [], "variants": []}'
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def base():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="module")
def page(base):
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        pg.goto(base + "/")
        pg.wait_for_function("typeof showProgress === 'function'")
        yield pg
        b.close()


def _rows(page):
    return page.eval_on_selector_all(
        "#pCases tr", "rs => rs.map(r => [...r.classList].filter(c => c !== 'alt').join(' '))")


def test_첫_집계_줄만으로_첫_항목이_끝난다(page):
    page.evaluate("""() => {
      state.plan = { cases: [1, 2, 3].map(i => ({ case_id: 'c' + i, title: '항목 ' + i, selected: true })) };
      showProgress('실행 중', []);
      pushProgress(['  케이스 1/3 · 항목 1']);
      pushProgress(['집계 통과 1 · 기획서와 다름 0 · 실행 문제 0']);
    }""")
    assert _rows(page)[0] == "case done"


def test_두_번째_항목은_바뀐_칸의_판정을_받는다(page):
    page.evaluate("""() => {
      pushProgress(['  케이스 2/3 · 항목 2']);
      pushProgress(['집계 통과 1 · 기획서와 다름 1 · 실행 문제 0']);
    }""")
    rows = _rows(page)
    assert rows[:2] == ["case done", "case done"]
    assert page.eval_on_selector("#pCases tr:nth-child(2) td:first-child svg", "e => e.getAttribute('class')") == "vm fail"
    assert rows[2] == "case wait"
