"""리포트 HTML 이 두 단계 실행(계획 저장 → 재개) 사실을 보여주는가.

summary["plan"] 은 test_two_stage_e2e 가 지키지만, JSON 에만 있고 HTML 에
없으면 사람이 여는 쪽 리포트가 그 사실을 숨기는 셈이다 — 세션 상자·figma
상자와 같은 이유로 HTML 도 말해야 한다.
"""

from __future__ import annotations

from prova.models import TestReport
from prova.s6_report.report_builder import render_html


def _report(summary_extra: dict) -> TestReport:
    summary = TestReport.summarize([])
    summary["llm_backend"] = "vllm"
    summary.update(summary_extra)
    return TestReport(
        run_id="two-stage", target_url="http://localhost:8100/good",
        spec_source="fixtures/specs/login_spec.pdf", summary=summary,
        cases=[], created_at="2026-08-26T10:00:00+09:00",
    )


class TestPlanBox:
    def test_재개_실행이면_상자가_보인다(self):
        html = render_html(_report({"plan": {
            "backend": "vllm", "created_at": "2026-08-26T09:00:00+09:00",
            "warnings": [],
        }}))
        assert "두 단계 실행" in html
        assert "vllm" in html
        assert "2026-08-26T09:00:00+09:00" in html

    def test_계획_경고도_상자에_담긴다(self):
        html = render_html(_report({"plan": {
            "backend": "vllm", "created_at": "2026-08-26T09:00:00+09:00",
            "warnings": ["설계 문서가 계획 이후 바뀌었습니다: a.pdf"],
        }}))
        assert "설계 문서가 계획 이후 바뀌었습니다" in html

    def test_직접_실행이면_상자가_없다(self):
        html = render_html(_report({}))
        assert "두 단계 실행" not in html
