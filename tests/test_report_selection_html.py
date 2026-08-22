"""요청 없이 승인만으로 좁힌 실행도 '무엇을 안 봤는지' 를 리포트에 남긴다.

## 2026-08-22 에 잡은 구멍

웹 UI 는 요청란을 비운 채 계획 화면에서 체크박스만 꺼서 실행할 수 있다. 그러면
`select_by_ids(request="")` 가 돌아 `CaseSelection.request == ""` 이 되고,
리포트는 `if sel.request:` 로 그 절을 통째로 건너뛰었다 — 제외 목록도 화면별 확인
범위도 없는, 통과율 100% 짜리 반쪽 리포트. `--only` 의 부분 실행 경고도 안 붙는다
(그건 `filtered_by` 에만 붙는다). 요청이 있든 없든 **제외가 있으면** 보여야 한다.
"""

from __future__ import annotations

from prova.models import CaseSelection, TestReport
from prova.s6_report.report_builder import render_html


def _report(selection: CaseSelection) -> TestReport:
    return TestReport(run_id="r", target_url="http://x/bad", summary={
        "total": 1, "pass": 1, "fail": 0, "healed": 0, "settled": 0, "pass_rate": 100.0,
    }, cases=[], selection=selection)


class TestExcludedWithoutRequest:
    def test_요청이_없어도_제외가_있으면_제외_목록을_싣는다(self):
        sel = CaseSelection(request="", selected=["login-a"], excluded=["login-b", "login-c"],
                            approved=True)
        html = render_html(_report(sel))
        assert "제외한 케이스" in html
        assert "login-b" in html and "login-c" in html

    def test_제외가_없고_요청도_없으면_절이_생기지_않는다(self):
        """기존 CLI 전체 실행 경로는 그대로 — 없던 절이 나타나면 안 된다."""
        sel = CaseSelection(request="", selected=["login-a"], excluded=[])
        html = render_html(_report(sel))
        assert "제외한 케이스" not in html
        assert "요청:" not in html

    def test_요청_없는_부분_실행은_요청_줄_대신_승인_줄을_쓴다(self):
        sel = CaseSelection(request="", selected=["login-a"], excluded=["login-b"],
                            approved=True)
        html = render_html(_report(sel))
        assert "요청: <code></code>" not in html
        assert "승인" in html


class TestWidened:
    def test_코드가_더한_케이스가_모델_선택과_구분되어_실린다(self):
        """모델이 고른 것과 코드가 넓힌 것을 리포트에서 구분할 수 있어야
        '해석이 맞았는가' 를 되짚을 수 있다 (selector.widen_selection)."""
        sel = CaseSelection(request="개수가 맞는지", selected=["search-count-005", "search-count-006"],
                            excluded=[], reason="건수 케이스", widened=["search-count-006 (R1)"])
        html = render_html(_report(sel))
        assert "도구가 넓힌 케이스 1건" in html
        assert "search-count-006 (R1)" in html

    def test_더한_것이_없으면_줄이_없다(self):
        sel = CaseSelection(request="개수가 맞는지", selected=["search-count-005"], excluded=["x"])
        html = render_html(_report(sel))
        assert "도구가 넓힌" not in html
