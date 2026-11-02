"""리포트 원형차트 — 기획자가 결과의 구성을 한눈에 본다 (2026-10-16 멘토링 요구).

차트가 숫자를 부풀리면 안 된다. 네 조각의 합은 전체 케이스 수와 같아야 하고, '기획서와
다름' 과 '실행 문제' 는 색과 이름 모두 갈린다. 실행하지 않은 것은 조각이 아니라 말로 남긴다.
"""

from __future__ import annotations

from prova.models import TestReport, Verdict
from prova.s5_verifier.assertion_engine import WEAK_PASS_REASON
from prova.s6_report.report_builder import chart_segments, render_html


def _v(case_id: str, verdict: str = "PASS", category=None, actual: str = "ok") -> Verdict:
    return Verdict(case_id=case_id, title=case_id, type="positive", verdict=verdict,
                   failure_category=category, evidence={"actual": actual})


def _report(verdicts: list[Verdict], **summary) -> TestReport:
    s = TestReport.summarize(verdicts)
    s.update(summary)
    return TestReport(run_id="r", target_url="http://x", spec_source="s.pdf", summary=s,
                      cases=verdicts, created_at="2026-11-02T00:00:00+09:00")


MIXED = [_v("a"), _v("b"), _v("c", actual=WEAK_PASS_REASON),
         _v("d", "FAIL", "assertion_mismatch"), _v("e", "FAIL", "assertion_mismatch"),
         _v("f", "FAIL", "element_not_found"), _v("g", "FAIL", "precondition_failed")]


def test_네_조각으로_나누고_합이_전체와_같다():
    got = {s.key: s.count for s in chart_segments(MIXED)}
    assert got == {"pass": 2, "weak": 1, "defect": 2, "infra": 2}
    assert sum(got.values()) == len(MIXED)


def test_없는_조각은_그리지_않는다():
    assert [s.key for s in chart_segments([_v("a")])] == ["pass"]


def test_리포트에_도넛과_이름표가_함께_있다():
    html = render_html(_report(MIXED))
    assert "<svg" in html and "role='img'" in html
    for label in ("통과", "약한 확인", "기획서와 다름", "실행 문제"):
        assert label in html


def test_케이스가_없으면_차트를_그리지_않는다():
    assert "<svg" not in render_html(_report([]))


def test_확인하지_않은_것이_있으면_차트_옆에_말한다():
    html = render_html(_report(MIXED, coverage_gaps=["x", "y"]))
    assert "차트에 없는 것" in html and "2건" in html
