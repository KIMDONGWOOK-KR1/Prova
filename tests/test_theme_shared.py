"""디자인 토큰이 한 벌인지 고정한다.

## 왜 테스트로 묶는가

리포트는 iframe 으로 웹 UI 안에 뜬다. 색이 두 벌로 갈라지면 같은 화면에 파란색이
두 가지가 되고, 리포트만 다크모드가 아니어서 혼자 하얗게 빛난다. 실제로 그랬다 —
UI 의 accent 는 #2c4b8a, 리포트는 #2f6fed 였다.

색을 두 곳에서 '만들 수 있는' 한 언젠가 다시 갈라진다. 그래서 만드는 곳이 하나임을
테스트가 지킨다.
"""

import re
from pathlib import Path

from prova.models import TestReport
from prova.s6_report.report_builder import render_html
from prova.theme import TOKENS_CSS

STATIC = Path("src/prova/server/static")


def report_html() -> str:
    return render_html(TestReport(run_id="t", target_url="http://x", summary={
        "total": 0, "pass": 0, "fail": 0, "pass_rate": 0.0}))


def _dark_block() -> str:
    """@media (prefers-color-scheme: dark) { ... } 안쪽을 중괄호로 정확히 잘라낸다."""
    start = TOKENS_CSS.index("@media (prefers-color-scheme: dark)")
    open_at = TOKENS_CSS.index("{", start)
    depth = 0
    for i in range(open_at, len(TOKENS_CSS)):
        if TOKENS_CSS[i] == "{":
            depth += 1
        elif TOKENS_CSS[i] == "}":
            depth -= 1
            if depth == 0:
                return TOKENS_CSS[open_at + 1:i]
    raise AssertionError("다크모드 블록이 닫히지 않았다")


class TestSingleSource:
    def test_리포트가_공유_토큰을_담는다(self):
        html = report_html()
        for token in ("--bg-canvas", "--fg-default", "--accent-solid", "--pass-fg"):
            assert token in html, f"리포트에 {token} 이 없다 — 토큰이 갈라졌다"

    def test_리포트에_하드코딩된_색이_없다(self):
        """theme.py 밖에서 색을 만들면 두 벌이 되는 첫걸음이다."""
        src = Path("src/prova/s6_report/report_builder.py").read_text(encoding="utf-8")
        found = re.findall(r"#[0-9a-fA-F]{3,8}\b", src)
        assert not found, f"report_builder 에 색 리터럴이 있다: {found}"

    def test_UI_스타일에도_하드코딩된_색이_없다(self):
        css = (STATIC / "app.css").read_text(encoding="utf-8")
        found = re.findall(r"#[0-9a-fA-F]{3,8}\b", css)
        assert not found, f"app.css 에 색 리터럴이 있다: {found}"


class TestDarkMode:
    def test_다크모드_정의가_토큰에_있다(self):
        assert "prefers-color-scheme: dark" in TOKENS_CSS

    def test_리포트도_다크모드를_따라간다(self):
        """리포트가 UI 안에 떴을 때 혼자 밝으면 두 제품처럼 보인다."""
        assert "prefers-color-scheme: dark" in report_html()

    def test_컴포넌트_규칙은_한_벌이다(self):
        """다크모드 블록이 semantic 층에만 있어야 한다. 컴포넌트 규칙을 두 벌
        쓰기 시작하면 한쪽이 반드시 뒤처진다."""
        assert not re.search(r"^\s*\.[a-z]", _dark_block(), re.M), \
            "다크 블록에 컴포넌트 규칙이 있다"
