"""리포트 글꼴 — 리포트 폴더에 Pretendard 를 함께 둔다 (2026-11-25).

받는 사람이 윈도여도, 서버가 찍은 PDF 여도 같은 글꼴로 보이게 한다. 인터넷에서 내려받지 않는다
(디자인 기준 4번) — 스크린샷처럼 폴더째 따라간다. OFL 이라 라이선스 파일도 함께 둔다.
"""

from __future__ import annotations

import re

from prova.models import TestReport
from prova.s6_report.report_builder import FONT_DIR, render_html, save_html


def _report() -> TestReport:
    return TestReport(run_id="r", target_url="http://x", summary={
        "total": 0, "pass": 0, "fail": 0, "pass_rate": 0.0})


def test_저장하면_글꼴과_라이선스가_리포트_폴더에_함께_놓인다(tmp_path):
    save_html(_report(), tmp_path)
    font = tmp_path / "fonts" / "PretendardVariable.woff2"
    assert font.exists() and font.stat().st_size == (FONT_DIR / font.name).stat().st_size
    assert "Open Font License" in (tmp_path / "fonts" / "Pretendard-OFL.txt").read_text(encoding="utf-8")


def test_리포트는_옆_폴더의_글꼴을_쓰고_바깥에서_받지_않는다():
    html = render_html(_report())
    assert "url(\"fonts/PretendardVariable.woff2\")" in html
    assert "font-family:var(--font-doc)" in html
    assert not re.search(r"@font-face[^}]*https?://", html)
