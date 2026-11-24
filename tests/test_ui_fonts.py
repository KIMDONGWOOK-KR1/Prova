"""웹 UI 글꼴 — 윈도 등 Apple 글꼴이 없는 곳에서는 함께 내주는 Pretendard 를 쓴다(2026-11-25 hh).

글꼴 파일은 보고서 것(s6_report/fonts) 하나를 서버가 /fonts 로 내준다. 바깥 글꼴 서버는 쓰지 않는다 —
폐쇄망에서도 같은 글꼴로 보여야 한다.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from prova.server import app as server_app
from prova.theme import TOKENS_CSS

STATIC = Path(server_app.__file__).parent / "static"


def test_글꼴_파일을_내준다():
    c = TestClient(server_app.app)
    r = c.get("/fonts/PretendardVariable.woff2")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("font/woff2")
    assert "immutable" in r.headers["cache-control"]
    assert r.content[:4] == b"wOF2"


def test_이름이_정해진_파일만_내준다():
    c = TestClient(server_app.app)
    assert c.get("/fonts/../app.py").status_code == 404
    assert c.get("/fonts/nothing.woff2").status_code == 404


def test_바깥_글꼴_서버를_쓰지_않는다():
    texts = [(STATIC / "index.html").read_text(encoding="utf-8"),
             (STATIC / "app.css").read_text(encoding="utf-8"), TOKENS_CSS]
    for t in texts:
        assert not re.search(r"https?://[^\"')\s]*(font|typekit|googleapis|gstatic|jsdelivr|unpkg)", t, re.I)


def test_시스템_글꼴_다음에_Pretendard():
    m = re.search(r"--font-sans:\s*([^;]+);", TOKENS_CSS)
    stack = [x.strip().strip('"') for x in m.group(1).split(",")]
    assert stack.index("Pretendard Variable") > stack.index("Apple SD Gothic Neo") > stack.index("-apple-system")
    # 맥이 아닐 때만 <head> 에서 붙인다(맥에서 받지 않게)
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "/fonts/PretendardVariable.woff2" in html and "if (!apple)" in html
