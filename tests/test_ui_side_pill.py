"""사이드바 고른 줄의 판 — 줄 상자와 딱 겹치는가 (2026-11-25 hh '사이드바가 이렇게 밀리는 것 같아').

넓은 창(1760px 이상)에서는 body 에 zoom 1.1(2080px 이상 1.2)이 걸린다. getBoundingClientRect 는 확대된 값이고
style 의 px 는 확대 전 값이라, 그대로 넣으면 판이 z 배로 커지고 아래 줄일수록 더 밀렸다.
"""

from __future__ import annotations

import http.server
import threading
import time

import pytest
from playwright.sync_api import sync_playwright

from test_ui_run_progress import _Handler

PILL = """() => { const p = document.querySelector('.side-pill').getBoundingClientRect();
  const r = document.querySelector('.sitem.pilled').getBoundingClientRect();
  return [p.left - r.left, p.top - r.top, p.width - r.width, p.height - r.height]; }"""


@pytest.fixture(scope="module")
def base():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.mark.parametrize("width", [1400, 1920, 2200])
def test_판이_고른_줄과_겹친다_접었다_펴도(base, width):
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": width, "height": 900})
        pg.goto(base + "/")
        pg.evaluate("localStorage.setItem('prova-side', 'open')")
        pg.reload()
        pg.wait_for_function("document.querySelector('.sitem.pilled')")
        time.sleep(0.3)
        assert all(abs(d) <= 0.5 for d in pg.evaluate(PILL))
        pg.evaluate("document.getElementById('sideToggle').click()")
        time.sleep(0.5)
        pg.evaluate("document.getElementById('sideToggle').click()")
        time.sleep(0.6)
        assert all(abs(d) <= 0.5 for d in pg.evaluate(PILL))
        b.close()
